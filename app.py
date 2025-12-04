import logging
import os
import traceback

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory

import config
from retrieval_system import VideoRetrievalSystem
from utils.video_metadata import load_shot_boundaries, load_video_metadata

log_file = "system.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- LOAD METADATA & SHOTS TỪ FILE ---
VIDEO_METADATA = load_video_metadata("video_metadata.json")
# Load Shot Boundaries
VIDEO_SHOTS = load_shot_boundaries(os.path.join("data", "shots"))

try:
    search_system = VideoRetrievalSystem(re_ingest=False)
    logger.info("Search system initialized successfully!")
except Exception as e:
    logger.error(f"Failed to initialize search system: {e}")
    logger.error(traceback.format_exc())
    search_system = None


def find_shot_for_keyframe(video_id, keyframe_index):
    """Tìm start/end frame của shot chứa keyframe_index này"""
    shots = VIDEO_SHOTS.get(video_id)
    if not shots:
        return None

    # Duyệt qua các shot (có thể tối ưu bằng binary search nếu cần)
    for shot in shots:
        if shot["start_frame"] <= keyframe_index <= shot["end_frame"]:
            return shot
    return None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search_api():
    if not search_system:
        return jsonify({"error": "Search system is not available."}), 500

    query_data = request.get_json()
    if not query_data:
        return jsonify({"error": "Invalid input: No JSON data received."}), 400

    logger.info(f"Received search request: {query_data}")

    try:
        description = query_data.get("description", "")
        result_sets = []

        # 1. Search by criteria
        if description:
            if query_data.get("criteria") == "fused_score":
                results = search_system.fused_search(
                    description, max_results=1000
                )
            elif query_data.get("criteria") == "clip_score":
                results = search_system.clip_search(
                    description, max_results=1000
                )
            else:
                results = search_system.beit3_search(
                    description, max_results=1000
                )
            result_sets.append(results)

        # 2. Search Objects
        if query_data.get("objects"):
            object_results = search_system.object_search(
                query_data["objects"], projection={"video_id": 1, "keyframe_index": 1}
            )
            result_sets.append(object_results)

        # 3. Search Transcript
        transcript_text = query_data.get("audio")
        if transcript_text:
            transcript_results = search_system.transcript_search(transcript_text, max_results=1000)
            result_sets.append(transcript_results)

        # Giao các tập kết quả
        results = search_system.intersect(result_sets)

        for item in results:
            vid = item.get("video_id")
            k_idx = item.get("keyframe_index")

            # Lấy FPS
            item["fps"] = VIDEO_METADATA.get(vid, 25.0)

            # Map Shot Info
            shot_info = find_shot_for_keyframe(vid, k_idx)
            if shot_info:
                item["shot_start_frame"] = shot_info["start_frame"]
                item["shot_end_frame"] = shot_info["end_frame"]
            else:
                # Fallback nếu không tìm thấy shot (coi như 1 frame là 1 shot)
                item["shot_start_frame"] = k_idx
                item["shot_end_frame"] = k_idx

        logger.info(f"Search completed. Number of results: {len(results)}")
        return jsonify(results[:1000])
    except Exception as e:
        logger.error(f"An error occurred during search: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred during search."}), 500


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
        video_hls_path = os.path.join(HLS_DIR, video_id)
        response = send_from_directory(video_hls_path, filename)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except FileNotFoundError:
        return "File not found", 404


@app.route("/api/login", methods=["POST"])
def login_proxy():
    # ... (Giữ nguyên code login cũ)
    try:
        login_url = f"{config.EVAL_SERVER_URL}/api/v2/login"
        creds = request.get_json() or {}
        username = creds.get("username", config.EVAL_USERNAME)
        password = creds.get("password", config.EVAL_PASSWORD)

        login_resp = requests.post(
            login_url, json={"username": username, "password": password}, verify=False
        )
        if login_resp.status_code != 200:
            return jsonify({"error": "Login failed", "details": login_resp.text}), 401

        session_id = login_resp.json().get("sessionId")
        list_url = f"{config.EVAL_SERVER_URL}/api/v2/client/evaluation/list"
        list_resp = requests.get(list_url, params={"session": session_id})

        if list_resp.status_code != 200:
            return jsonify({"error": "Failed to get eval list"}), 400

        return jsonify(
            {
                "message": "Login successful",
                "sessionId": session_id,
                "evaluations": list_resp.json(),
            }
        )
    except Exception as e:
        logger.error(f"Login proxy error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/submit", methods=["POST"])
def submit_proxy():
    # ... (Giữ nguyên code submit cũ)
    try:
        data = request.get_json()
        session_id = data.get("sessionId")
        evaluation_id = data.get("evaluationId")
        video_id = data.get("videoId")
        time_ms = data.get("timeMs")

        if not all([session_id, evaluation_id, video_id, time_ms is not None]):
            return jsonify({"error": "Missing required fields"}), 400

        submit_url = f"{config.EVAL_SERVER_URL}/api/v2/submit/{evaluation_id}"
        payload = {
            "answerSets": [
                {
                    "answers": [
                        {
                            "mediaItemName": video_id,
                            "start": str(int(time_ms)),
                            "end": str(int(time_ms)),
                        }
                    ]
                }
            ]
        }
        response = requests.post(
            submit_url, json=payload, params={"session": session_id}
        )
        if response.status_code == 200:
            return jsonify({"success": True, "remote_response": response.json()})
        else:
            return (
                jsonify({"success": False, "error": response.text}),
                response.status_code,
            )
    except Exception as e:
        logger.error(f"Submit proxy error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
