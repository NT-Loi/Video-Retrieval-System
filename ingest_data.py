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

# --- Helper Functions ---


def _load_keyframe_map(video_id: str):
    maps_dir = Path(config.KEYFRAMES_DIR) / "maps"
    map_file = maps_dir / f"{video_id}_map.csv"
    if not map_file.exists():
        return None

    try:
        df = pd.read_csv(map_file, usecols=["FrameID", "Seconds"])
        df = df.dropna(subset=["FrameID", "Seconds"]).sort_values("Seconds")
        if df.empty:
            return None
        frame_ids = df["FrameID"].to_numpy(dtype=np.int32)
        seconds = df["Seconds"].to_numpy(dtype=np.float32)
        return seconds, frame_ids
    except Exception as exc:
        logger.warning(f"Failed to load keyframe map for {video_id}: {exc}")
        return None


def _resolve_frames_from_map(mapping, target_seconds: np.ndarray):
    if mapping is None or target_seconds.size == 0:
        return None, None

    seconds, frame_ids = mapping
    if seconds.size == 0:
        return None, None

    positions = np.searchsorted(seconds, target_seconds, side="left")
    right_idx = np.clip(positions, 0, len(seconds) - 1)
    left_idx = np.clip(positions - 1, 0, len(seconds) - 1)

    diff_left = np.abs(target_seconds - seconds[left_idx])
    diff_right = np.abs(target_seconds - seconds[right_idx])
    best_idx = np.where(diff_left <= diff_right, left_idx, right_idx)

    return frame_ids[best_idx].astype(int), seconds[best_idx].astype(float)


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


def ingest_keyframe_data(collection: Collection):
    logger.info("Ingesting keyframe data into Milvus...")
    root = Path(config.CLIP_FEATURES_DIR)

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
    es_client: Elasticsearch, folder_path: str, metadata_cache: dict
) -> None:
    """
    Ingest transcript data using FPS from metadata_cache.
    """
    logger.info("Ingesting transcript data into Elasticsearch...")

    transcripts_dir = Path(folder_path)
    if not transcripts_dir.exists():
        logger.error(f"Transcript directory not found: {transcripts_dir}")
        return

    csv_files = sorted(transcripts_dir.glob("*.csv"))
    if not csv_files:
        logger.warning("No transcript CSV files found.")
        return

    total_docs = 0
    map_cache: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}

    for csv_path in csv_files:
        video_id = csv_path.stem

        # --- Lấy FPS từ cache được truyền vào ---
        # Fallback 25.0 nếu không tìm thấy trong cache
        fps = metadata_cache.get(video_id, 25.0)
        # ----------------------------------------

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

        # Tính toán frame dựa trên FPS
        start_frames = np.maximum(0, np.rint(start_secs * fps).astype(np.int32))

        if video_id not in map_cache:
            map_cache[video_id] = _load_keyframe_map(video_id)
        frame_map = map_cache[video_id]

        resolved_frames = start_frames
        resolved_starts = start_secs

        if frame_map:
            resolved = _resolve_frames_from_map(frame_map, start_secs)
            if resolved[0] is not None:
                resolved_frames = resolved[0]
                resolved_starts = resolved[1]

        texts = df["Text"].tolist()
        row_ids = df.index.to_numpy()

        actions = []
        for idx in range(len(texts)):
            action = {
                "_index": config.TRANSCRIPT_INDEX,
                "_id": f"{video_id}_{resolved_frames[idx]}_{row_ids[idx]}",
                "_source": {
                    "video_id": video_id,
                    "keyframe_index": int(resolved_frames[idx]),
                    "start": float(round(resolved_starts[idx], 3)),
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

    # --- Elasticsearch Ingestion ---
    es_client = get_elasticsearch_client()
    recreate_transcript_index(es_client)
    # Pass metadata to transcript ingestion
    ingest_transcript_data(es_client, config.TRANSCRIPTS_DIR, metadata_cache)

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
    ingest_keyframe_data(kf_collection)

    kf_collection = setup_milvus_collection(
        config.BEIT3_COLLECTION_NAME, kf_schema, "keyframe_vector", kf_index_params
    )
    ingest_keyframe_data(kf_collection)

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
