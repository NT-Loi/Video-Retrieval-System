import json
import logging
import numpy as np
from bson import json_util
from elasticsearch import Elasticsearch
from pymilvus import Collection, connections
from pymongo import MongoClient
import config
from utils.elasticsearch_client import get_elasticsearch_client
from utils.text_encoder import CLIPTextEncoder, BEIT3TextEncoder

logger = logging.getLogger(__name__)


class VideoRetrievalSystem:
    def __init__(self, re_ingest=False):
        # ... (Phần init giữ nguyên) ...
        if re_ingest:
            from ingest_data import main

            main()

        logger.info("Initializing Video Retrieval System...")
        connections.connect("default", host=config.MILVUS_HOST, port=config.MILVUS_PORT)
        self.clip_collection = Collection(config.CLIP_COLLECTION_NAME)
        self.clip_collection.load()
        self.beit3_collection = Collection(config.BEIT3_COLLECTION_NAME)
        self.beit3_collection.load()

        mongo_client = MongoClient(config.MONGO_URI)
        mongo_db = mongo_client[config.MONGO_DB_NAME]
        self.object_collection = mongo_db[config.MONGO_OBJECT_COLLECTION]

        self.es_client: Elasticsearch = get_elasticsearch_client()
        self.device = "cpu"  # Hoặc cuda
        self.clip_encoder = CLIPTextEncoder(device=self.device)
        self.beit3_encoder = BEIT3TextEncoder(device=self.device)

    # ... (Các hàm clip_search, beit3_search, fused_search giữ nguyên) ...
    def clip_search(self, query: str = "", max_results: int = 200) -> list:
        # (Code cũ giữ nguyên)
        if not query:
            return []
        query_vector = self.clip_encoder.encode(query)
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        search_results = self.clip_collection.search(
            data=query_vector,
            anns_field="keyframe_vector",
            param=search_params,
            limit=max_results,
            output_fields=["video_id", "keyframe_index"],
        )
        # Normalization logic here (như code cũ)
        keyframe_scores = []
        if search_results and len(search_results[0]) > 0:
            max_d = max(hit.distance for hit in search_results[0])
            min_d = min(hit.distance for hit in search_results[0])
            denom = max_d - min_d if max_d != min_d else 1.0
            for hit in search_results[0]:
                keyframe_scores.append(
                    {
                        "video_id": hit.entity.get("video_id"),
                        "keyframe_index": hit.entity.get("keyframe_index"),
                        "clip_score": hit.distance,
                        "normalized_clip_score": float((hit.distance - min_d) / denom),
                    }
                )
        return keyframe_scores

    def beit3_search(self, query: str = "", max_results: int = 200) -> list:
        # (Code cũ giữ nguyên)
        if not query:
            return []
        query_vector = self.beit3_encoder.encode(query)
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        search_results = self.beit3_collection.search(
            data=query_vector,
            anns_field="keyframe_vector",
            param=search_params,
            limit=max_results,
            output_fields=["video_id", "keyframe_index"],
        )
        keyframe_scores = []
        if search_results and len(search_results[0]) > 0:
            max_d = max(hit.distance for hit in search_results[0])
            min_d = min(hit.distance for hit in search_results[0])
            denom = max_d - min_d if max_d != min_d else 1.0
            for hit in search_results[0]:
                keyframe_scores.append(
                    {
                        "video_id": hit.entity.get("video_id"),
                        "keyframe_index": hit.entity.get("keyframe_index"),
                        "beit3_score": hit.distance,
                        "normalized_beit3_score": float((hit.distance - min_d) / denom),
                    }
                )
        return keyframe_scores

    def fused_search(self, query: str = "", max_results: int = 200) -> list:
        # (Code cũ giữ nguyên)
        # Lưu ý: Nên tăng max_results lên cao (ví dụ 500-1000) bên trong hàm này khi gọi từ temporal_search
        # để tăng khả năng bắt được sequence
        if not query:
            return []
        clip_res = self.clip_search(query, max_results)
        beit_res = self.beit3_search(query, max_results)

        merged = {}
        for item in clip_res:
            key = (item["video_id"], item["keyframe_index"])
            merged.setdefault(key, {})
            merged[key].update(item)
        for item in beit_res:
            key = (item["video_id"], item["keyframe_index"])
            merged.setdefault(key, {})
            merged[key].update(item)

        results = []
        for _, item in merged.items():
            c_s = item.get("normalized_clip_score", 0)
            b_s = item.get("normalized_beit3_score", 0)
            item["fused_score"] = 0.5 * c_s + 0.5 * b_s
            results.append(item)

        results.sort(key=lambda x: x["fused_score"], reverse=True)
        return results[:max_results]

    def temporal_search(
        self, text_queries: list[str], anchor_index: int = 0, max_results: int = 200
    ) -> list[dict]:
        logger.info(f"--- Temporal Search: {text_queries}, Anchor: {anchor_index} ---")

        if len(text_queries) == 1:
            return self.fused_search(text_queries[0], max_results=max_results)

        if not text_queries:
            return []

        # 2. Search độc lập
        candidate_lists = []
        for q in text_queries:
            res = self.fused_search(q, max_results=1000)
            candidate_lists.append(res)

        # 3. Gom nhóm theo Video ID
        video_map = {}
        for q_idx, res_list in enumerate(candidate_lists):
            for item in res_list:
                vid = item["video_id"]
                if vid not in video_map:
                    video_map[vid] = {i: [] for i in range(len(text_queries))}
                video_map[vid][q_idx].append(item)

        final_results = []
        max_gap = config.MAX_FRAME_GAP

        for vid, q_data in video_map.items():
            if any(len(q_data[i]) == 0 for i in range(len(text_queries))):
                continue

            anchor_candidates = q_data[anchor_index]

            for anchor_item in anchor_candidates:
                current_frame = anchor_item["keyframe_index"]

                # Tạo list chứa chuỗi kết quả: [ {q_idx:0, ...}, {q_idx:1, ...} ]
                # Mặc định thêm anchor item vào trước
                sequence_chain = []
                # Thêm thông tin query index cho anchor
                anchor_w_idx = anchor_item.copy()
                anchor_w_idx["query_index"] = anchor_index
                sequence_chain.append(anchor_w_idx)

                is_valid_sequence = True

                # Check PREVIOUS queries
                last_frame = current_frame
                for i in range(anchor_index - 1, -1, -1):
                    possible_prevs = [
                        x
                        for x in q_data[i]
                        if 0 < (last_frame - x["keyframe_index"]) < max_gap
                    ]
                    if not possible_prevs:
                        is_valid_sequence = False
                        break
                    best_prev = max(
                        possible_prevs, key=lambda x: x.get("fused_score", 0)
                    )

                    # Lưu vào chuỗi
                    prev_w_idx = best_prev.copy()
                    prev_w_idx["query_index"] = i
                    sequence_chain.append(prev_w_idx)

                    last_frame = best_prev["keyframe_index"]

                if not is_valid_sequence:
                    continue

                # Check NEXT queries
                last_frame = current_frame
                for j in range(anchor_index + 1, len(text_queries)):
                    possible_nexts = [
                        x
                        for x in q_data[j]
                        if 0 < (x["keyframe_index"] - last_frame) < max_gap
                    ]
                    if not possible_nexts:
                        is_valid_sequence = False
                        break
                    best_next = max(
                        possible_nexts, key=lambda x: x.get("fused_score", 0)
                    )

                    # Lưu vào chuỗi
                    next_w_idx = best_next.copy()
                    next_w_idx["query_index"] = j
                    sequence_chain.append(next_w_idx)

                    last_frame = best_next["keyframe_index"]

                if is_valid_sequence:
                    # Sắp xếp chuỗi theo query index để hiển thị đúng thứ tự
                    sequence_chain.sort(key=lambda x: x["query_index"])

                    # Gán chuỗi tìm được vào item kết quả để Frontend dùng
                    anchor_item["temporal_sequence"] = sequence_chain
                    final_results.append(anchor_item)

        final_results.sort(key=lambda x: x.get("fused_score", 0), reverse=True)
        return final_results[:max_results]

    # --- Object Search & Transcript Search & Intersect giữ nguyên ---
    def object_search(self, queries: list[dict], projection: dict = None) -> list[dict]:
        # (Code cũ giữ nguyên)
        if not queries:
            return []
        # ... (Phần code aggregate mongodb cũ) ...
        # Copy lại logic trong file gốc của bạn
        try:
            labels = list(set(q["label"] for q in queries))
            pipeline = [{"$match": {"objects.class": {"$in": labels}}}]
            all_conditions = []
            for query in queries:
                label = query["label"]
                min_conf = query.get("confidence", 0.0)
                filter_expr = {
                    "$filter": {
                        "input": "$objects",
                        "as": "obj",
                        "cond": {
                            "$and": [
                                {"$eq": ["$$obj.class", label]},
                                {"$gte": ["$$obj.confidence", min_conf]},
                            ]
                        },
                    }
                }
                size_expr = {"$size": filter_expr}
                conds = []
                if query.get("min_instances") is not None:
                    conds.append({"$gte": [size_expr, query["min_instances"]]})
                if query.get("max_instances") is not None:
                    conds.append({"$lte": [size_expr, query["max_instances"]]})
                if len(conds) == 1:
                    all_conditions.append(conds[0])
                else:
                    all_conditions.append({"$and": conds})
            pipeline.append(
                {
                    "$match": {
                        "$expr": (
                            {"$and": all_conditions}
                            if len(all_conditions) > 1
                            else all_conditions[0]
                        )
                    }
                }
            )
            if projection:
                pipeline.append({"$project": projection})
            return json.loads(
                json_util.dumps(list(self.object_collection.aggregate(pipeline)))
            )
        except Exception as e:
            logger.error(f"Object search error: {e}")
            return []

    def transcript_search(self, query: str = "", max_results: int = 200) -> list[dict]:
        # (Code cũ giữ nguyên)
        if not query:
            return []
        try:
            response = self.es_client.search(
                index=config.TRANSCRIPT_INDEX,
                size=max_results,
                query={
                    "bool": {
                        "should": [
                            {"match": {"text": {"query": query, "fuzziness": "AUTO"}}},
                            {"match_phrase": {"text": {"query": query}}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                _source=["video_id", "keyframe_index", "text"],
            )
            hits = []
            for hit in response.get("hits", {}).get("hits", []):
                src = hit.get("_source", {})
                hits.append(
                    {
                        "video_id": src.get("video_id"),
                        "keyframe_index": src.get("keyframe_index"),
                        "transcript_text": src.get("text"),
                        "transcript_score": hit.get("_score"),
                    }
                )
            return hits
        except Exception as e:
            logger.error(f"Transcript search error: {e}")
            return []

    def intersect(
        self, list_results: list[list[dict]], max_results: int = 200
    ) -> list[dict]:
        # (Code cũ giữ nguyên)
        if not list_results:
            return []
        if len(list_results) == 1:
            return list_results[0]

        first_list = list_results[0]
        lookup = {(kf["video_id"], kf["keyframe_index"]): kf for kf in first_list}
        intersecting_ids = set(lookup.keys())

        for other in list_results[1:]:
            other_ids = set((kf["video_id"], kf["keyframe_index"]) for kf in other)
            intersecting_ids &= other_ids
            if not intersecting_ids:
                break

        final = [lookup[mid] for mid in intersecting_ids]
        # Sort ưu tiên fused_score
        if final:
            if "fused_score" in final[0]:
                final.sort(key=lambda x: x.get("fused_score", 0), reverse=True)
            elif "clip_score" in final[0]:
                final.sort(key=lambda x: x.get("clip_score", 0), reverse=True)
        return final[:max_results]
