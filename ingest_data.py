import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)
from pymongo import MongoClient, UpdateOne

import config
from utils.elasticsearch_client import (
    get_elasticsearch_client,
    recreate_transcript_index,
)
from utils.video_metadata import load_video_metadata

BULK_CHUNK_SIZE = 2000
logger = logging.getLogger(__name__)

# --- Ingestion Functions ---

def setup_milvus_collection(collection_name, schema, index_field, index_params):
    if utility.has_collection(collection_name):
        logger.warning(f"Collection '{collection_name}' already exists. Dropping.")
        utility.drop_collection(collection_name)

    collection = Collection(collection_name, schema)
    logger.info(f"Collection '{collection_name}' created.")

    logger.info(f"Creating index for field '{index_field}'...")
    collection.create_index(field_name=index_field, index_params=index_params)
    collection.flush()
    logger.info("Index created and data flushed.")
    return collection


def ingest_keyframe_data(collection: Collection, feature_dir: str):
    logger.info("Ingesting keyframe data into Milvus...")
    root = Path(feature_dir)

    if not root.exists():
        logger.error(f"Embeddings directory not found: {root}")
        return

    for video_path in list(root.iterdir()):
        if not video_path.is_dir():
            continue

        video_id = video_path.name
        vectors = []
        frame_indices = []

        for pt_file in list(video_path.glob("*.pt")):
            try:
                frame_idx = int(pt_file.stem.split("_")[-1])
                vec = (
                    torch.load(str(pt_file), map_location="cpu")
                    .numpy()
                    .astype(np.float32)
                )
                vec = vec.reshape(1, -1)
                vectors.append(vec)
                frame_indices.append(frame_idx)
            except Exception as e:
                logger.error(f"Error processing {pt_file}: {e}")
                continue

        if vectors:
            vectors = np.vstack(vectors)
            num_vectors = len(vectors)
            entities = [[video_id] * num_vectors, frame_indices, vectors]
            collection.insert(entities)

    collection.flush()
    logger.info("Keyframe data ingestion complete.")


def setup_mongodb_collection(
    mongo_client, db_name, collection_name, drop_existing=True
):
    db = mongo_client[db_name]

    if drop_existing and collection_name in db.list_collection_names():
        logger.warning(
            f"MongoDB collection '{collection_name}' already exists. Dropping."
        )
        db[collection_name].drop()

    collection = db[collection_name]

    collection.create_index([("video_id", 1), ("keyframe_index", 1)], unique=True)
    collection.create_index([("objects.label", 1)])
    collection.create_index([("objects.confidence", 1)])

    logger.info(f"MongoDB collection '{collection_name}' created with indexes.")
    return collection


def ingest_object_detection_data(mongo_collection, folder_path):
    logger.info("Ingesting object detection data into MongoDB...")

    if not os.path.isdir(folder_path):
        logger.error(f"Object detection directory not found: {folder_path}")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith("_rfdetr_results.csv"):
            full_path = os.path.join(folder_path, filename)
            video_id = filename.replace("_rfdetr_results.csv", "")

            logger.info(f"--- Processing file: {os.path.basename(full_path)} ---")

            try:
                df = pd.read_csv(full_path)
                df.columns = df.columns.str.strip()
                grouped = df.groupby("frame")

                bulk_operations = []
                for frame_index, group in grouped:
                    frame_idx_str = (
                        str(frame_index).replace("keyframe_", "").replace(".webp", "")
                    )
                    try:
                        frame_idx_int = int(frame_idx_str)
                    except ValueError:
                        continue

                    objects_list = group.apply(
                        lambda row: {
                            "class": row["class"],
                            "confidence": float(row["confidence"]),
                            "bounding_box": {
                                "x": int(row["x"]),
                                "y": int(row["y"]),
                                "width": int(row["width"]),
                                "height": int(row["height"]),
                            },
                        },
                        axis=1,
                    ).tolist()

                    bulk_operations.append(
                        UpdateOne(
                            {"video_id": video_id, "keyframe_index": frame_idx_int},
                            {"$set": {"objects": objects_list}},
                            upsert=True,
                        )
                    )

                if bulk_operations:
                    logger.info(
                        f"Executing bulk upsert for {len(bulk_operations)} frames for video_id '{video_id}'..."
                    )
                    result = mongo_collection.bulk_write(bulk_operations)
                    logger.info(
                        f"Insert/Update complete for '{video_id}'. Inserted: {result.upserted_count}, Updated: {result.modified_count}\n"
                    )

            except Exception as e:
                logger.error(f"An error occurred while processing {full_path}: {e}")

    logger.info(f"Object detection data ingestion complete.")


def ingest_transcript_data(
    es_client: Elasticsearch, transcript_path: str, keyframe_path: str, metadata_cache: dict
) -> None:
    """
    Ingest transcript data using FPS from metadata_cache and compute keyframe timestamps automatically.
    """
    logger.info("Ingesting transcript data into Elasticsearch...")
    transcripts_dir = Path(transcript_path)
    keyframes_dir = Path(keyframe_path)

    if not transcripts_dir.exists():
        logger.error(f"Transcript directory not found: {transcripts_dir}")
        return

    if not keyframes_dir.exists():
        logger.error(f"Keyframe directory not found: {keyframes_dir}")
        return

    csv_files = sorted(transcripts_dir.glob("*.csv"))
    if not csv_files:
        logger.warning("No transcript CSV files found.")
        return

    total_docs = 0

    for csv_path in csv_files:
        video_id = csv_path.stem

        # Get FPS from metadata cache, fallback to 25.0 if not found
        fps = metadata_cache.get(video_id, 25.0)

        # Get all keyframes for the video
        video_keyframe_dir = keyframes_dir / video_id
        if not video_keyframe_dir.exists():
            logger.warning(f"No keyframes found for video {video_id}; skipping")
            continue

        keyframe_indices = sorted(
            int(p.stem.split("_")[-1]) for p in video_keyframe_dir.glob("*.webp")
        )
        if not keyframe_indices:
            logger.warning(f"No valid keyframe files found for video {video_id}; skipping")
            continue

        # Compute timestamps for each keyframe based on FPS
        keyframe_timestamps = {idx: idx / fps for idx in keyframe_indices}

        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            logger.error(f"Failed to read {csv_path}: {exc}")
            continue

        df.columns = [col.strip().title() for col in df.columns]
        required_columns = {"Start", "End", "Text"}
        if not required_columns.issubset(df.columns):
            logger.warning(
                f"Transcript file {csv_path} missing required columns; skipping"
            )
            continue

        df = df.dropna(subset=["Text"])
        df["Text"] = df["Text"].astype(str).str.strip()
        df = df[df["Text"] != ""]
        if df.empty:
            continue

        start_secs = (
            pd.to_numeric(df["Start"], errors="coerce")
            .fillna(0.0)
            .to_numpy(dtype=np.float32)
        )
        end_secs = pd.to_numeric(df["End"], errors="coerce").to_numpy(dtype=np.float32)
        end_secs = np.where(np.isnan(end_secs), start_secs, end_secs)
        end_secs = np.maximum(end_secs, start_secs)

        # Resolve keyframes based on start times
        resolved_frames = []
        for start_sec, end_sec in zip(start_secs, end_secs):
            # Find the closest keyframe
            closest_frame = min(
                keyframe_timestamps.keys(),
                key=lambda frame_idx: abs(keyframe_timestamps[frame_idx] - start_sec),
            )

            # Check if the keyframe lies within the audio timestamp range
            keyframe_time = keyframe_timestamps[closest_frame]
            if start_sec <= keyframe_time <= end_sec:
                resolved_frames.append(closest_frame)
            else:
                # Skip this keyframe if it doesn't lie within the range
                resolved_frames.append(None)

        texts = df["Text"].tolist()
        row_ids = df.index.to_numpy()

        actions = []
        for idx in range(len(texts)):
            # Skip if no valid keyframe was resolved
            if resolved_frames[idx] is None:
                continue

            action = {
                "_index": config.TRANSCRIPT_INDEX,
                "_id": f"{video_id}_{resolved_frames[idx]}_{row_ids[idx]}",
                "_source": {
                    "video_id": video_id,
                    "keyframe_index": int(resolved_frames[idx]),
                    "start": float(round(start_secs[idx], 3)),
                    "end": float(round(end_secs[idx], 3)),
                    "text": texts[idx],
                },
            }
            actions.append(action)

            if len(actions) >= BULK_CHUNK_SIZE:
                success, _ = bulk(es_client, actions, refresh=False)
                total_docs += success
                actions.clear()

        if actions:
            success, _ = bulk(es_client, actions, refresh=False)
            total_docs += success

    es_client.indices.refresh(index=config.TRANSCRIPT_INDEX)
    logger.info(f"Transcript ingestion complete. Total documents: {total_docs}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # 1. Load metadata (FPS) from root json file first
    metadata_cache = load_video_metadata("video_metadata.json")

    # # --- Elasticsearch Ingestion ---
    es_client = get_elasticsearch_client()
    recreate_transcript_index(es_client)
    # Pass metadata to transcript ingestion
    ingest_transcript_data(es_client, config.TRANSCRIPTS_DIR, config.KEYFRAMES_DIR, metadata_cache)

    # --- Milvus Ingestion ---
    connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
    kf_fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="video_id", dtype=DataType.VARCHAR, max_length=20),
        FieldSchema(name="keyframe_index", dtype=DataType.INT64),
        FieldSchema(
            name="keyframe_vector",
            dtype=DataType.FLOAT_VECTOR,
            dim=config.VECTOR_DIMENSION,
        ),
    ]
    kf_schema = CollectionSchema(kf_fields, "Keyframe vectors")
    kf_index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }

    kf_collection = setup_milvus_collection(
        config.CLIP_COLLECTION_NAME, kf_schema, "keyframe_vector", kf_index_params
    )
    ingest_keyframe_data(kf_collection, config.CLIP_FEATURES_DIR)

    kf_collection = setup_milvus_collection(
        config.BEIT3_COLLECTION_NAME, kf_schema, "keyframe_vector", kf_index_params
    )
    ingest_keyframe_data(kf_collection, config.BEIT3_FEATURES_DIR)

    # --- MongoDB Ingestion ---
    mongo_client = MongoClient(config.MONGO_URI)
    object_collection = setup_mongodb_collection(
        mongo_client,
        config.MONGO_DB_NAME,
        config.MONGO_OBJECT_COLLECTION,
        drop_existing=True,
    )
    ingest_object_detection_data(
        object_collection, folder_path=config.OBJECT_DETECTION_DIR
    )

    logger.info("--- DATA INGESTION COMPLETE ---")
    mongo_client.close()


if __name__ == "__main__":
    main()
