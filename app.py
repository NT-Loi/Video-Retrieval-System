import logging
import os
import traceback
import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
import config
from retrieval_system import VideoRetrievalSystem
from utils.video_metadata import load_shot_boundaries, load_video_metadata

# ... (Logger setup giữ nguyên) ...
logger = logging.getLogger(__name__)
app = Flask(__name__)

VIDEO_METADATA = load_video_metadata("video_metadata.json")
VIDEO_SHOTS = load_shot_boundaries(os.path.join("data", "shots"))

try:
    search_system = VideoRetrievalSystem(re_ingest=False)
    logger.info("Search system initialized successfully!")
except Exception as e:
    logger.error(f"Failed to initialize search system: {e}")
    search_system = None


# ... (Hàm find_shot_for_keyframe giữ nguyên) ...
def find_shot_for_keyframe(video_id, keyframe_index):
    shots = VIDEO_SHOTS.get(video_id)
    if not shots:
        return None
    for shot in shots:
        if shot["start_frame"] <= keyframe_index <= shot["end_frame"]:
            return shot
    return None


@app.route("/")
def home():
    return render_template("index.html")


# --- API AUDIO (Giữ nguyên) ---
@app.route("/audio")
def audio_page():
    return render_template("audio.html")


# --- UPDATED SEARCH API ---
@app.route("/search", methods=["POST"])
def search_api():
    if not search_system:
        return jsonify({"error": "Search system is not available."}), 500

    query_data = request.get_json()
    if not query_data:
        return jsonify({"error": "Invalid input."}), 400

    logger.info(f"Received search request: {query_data}")

    try:
        # Hỗ trợ cả format cũ (description: string) và mới (text_queries: list)
        text_queries = query_data.get("text_queries", [])
        if not text_queries and query_data.get("description"):
            text_queries = [query_data.get("description")]

        anchor_index = int(query_data.get("anchor_index", 0))
        # Đảm bảo anchor index hợp lệ
        if anchor_index >= len(text_queries):
            anchor_index = 0

        max_results = 500
        result_sets = []

        # 1. Temporal / Text Search
        if text_queries:
            # Gọi hàm temporal_search thay vì gọi trực tiếp fused/clip search
            # Hàm này sẽ tự handle logic 1 câu hoặc 3 câu
            text_results = search_system.temporal_search(
                text_queries, anchor_index=anchor_index, max_results=max_results
            )
            result_sets.append(text_results)

        # 2. Object Search (AND logic)
        if query_data.get("objects"):
            object_results = search_system.object_search(
                query_data["objects"], projection={"video_id": 1, "keyframe_index": 1}
            )
            result_sets.append(object_results)

        # 3. Audio/Transcript Search (AND logic)
        transcript_text = query_data.get("audio")
        if transcript_text:
            transcript_results = search_system.transcript_search(
                transcript_text, max_results=max_results
            )
            result_sets.append(transcript_results)

        # Giao các tập kết quả
        # Logic: Text (Sequence) AND Object AND Audio
        # Nếu chỉ có Audio -> Trả về Audio results
        # Nếu chỉ có Text -> Trả về Temporal Results
        results = search_system.intersect(result_sets, max_results=max_results)

        # Map Metadata (FPS, Shot info)
        for item in results:
            vid = item.get("video_id")
            k_idx = item.get("keyframe_index")
            item["fps"] = VIDEO_METADATA.get(vid, 25.0)

            shot_info = find_shot_for_keyframe(vid, k_idx)
            if shot_info:
                item["shot_start_frame"] = shot_info["start_frame"]
                item["shot_end_frame"] = shot_info["end_frame"]
            else:
                item["shot_start_frame"] = k_idx
                item["shot_end_frame"] = k_idx

        logger.info(f"Search completed. Results: {len(results)}")
        return jsonify(results)

    except Exception as e:
        logger.error(f"Error search: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ... (Các phần route static/hls/login/submit giữ nguyên) ...
@app.route("/keyframes/<string:video_id>/keyframe_<int:keyframe_index>.webp")
def serve_frame_image(video_id, keyframe_index):
    try:
        keyframe_dir = os.path.join(config.KEYFRAMES_DIR, video_id)
        filename = f"keyframe_{keyframe_index}.webp"
        return send_from_directory(keyframe_dir, filename)
    except FileNotFoundError:
        return send_from_directory("static", "placeholder.png"), 404


HLS_DIR = os.path.join(os.getcwd(), "data", "hls")


@app.route("/hls/<string:video_id>/<path:filename>")
def serve_hls(video_id, filename):
    try:
        return send_from_directory(os.path.join(HLS_DIR, video_id), filename)
    except FileNotFoundError:
        return "Not found", 404


# Proxy API Login & Submit giữ nguyên như code cũ
@app.route("/api/login", methods=["POST"])
def login_proxy():
    # ... (Copy y nguyên code cũ) ...
    try:
        login_url = f"{config.EVAL_SERVER_URL}/api/v2/login"
        creds = request.get_json() or {}
        username = creds.get("username", config.EVAL_USERNAME)
        password = creds.get("password", config.EVAL_PASSWORD)
        login_resp = requests.post(
            login_url, json={"username": username, "password": password}, verify=False
        )
        if login_resp.status_code != 200:
            return jsonify({"error": "Login failed"}), 401
        session_id = login_resp.json().get("sessionId")
        list_url = f"{config.EVAL_SERVER_URL}/api/v2/client/evaluation/list"
        list_resp = requests.get(list_url, params={"session": session_id})
        return jsonify(
            {"message": "OK", "sessionId": session_id, "evaluations": list_resp.json()}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/submit", methods=["POST"])
def submit_proxy():
    # ... (Copy y nguyên code cũ) ...
    try:
        data = request.get_json()
        s_id = data.get("sessionId")
        e_id = data.get("evaluationId")
        vid = data.get("videoId")
        t_ms = data.get("timeMs")
        submit_url = f"{config.EVAL_SERVER_URL}/api/v2/submit/{e_id}"
        payload = {
            "answerSets": [
                {
                    "answers": [
                        {
                            "mediaItemName": vid,
                            "start": str(int(t_ms)),
                            "end": str(int(t_ms)),
                        }
                    ]
                }
            ]
        }
        res = requests.post(submit_url, json=payload, params={"session": s_id})
        return (
            jsonify({"success": True, "remote_response": res.json()})
            if res.status_code == 200
            else (jsonify({"error": res.text}), res.status_code)
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
