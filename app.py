import logging
import os
import subprocess
import traceback

import requests
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

import config
from retrieval_system import VideoRetrievalSystem
from utils.video_metadata import load_video_metadata

log_file = "system.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

VIDEO_METADATA = load_video_metadata(config.VIDEOS_DIR)

try:
    search_system = VideoRetrievalSystem(re_ingest=False)
    logger.info("Search system initialized successfully!")
except Exception as e:
    logger.error(f"Failed to initialize search system: {e}")
    logger.error(traceback.format_exc())
    search_system = None


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

        # 1. Search Text/CLIP
        if description:
            clip_results = search_system.clip_search(description, max_results=500)
            result_sets.append(clip_results)

        # 2. Search Objects
        if query_data.get("objects"):
            object_results = search_system.object_search(
                query_data["objects"], projection={"video_id": 1, "keyframe_index": 1}
            )
            result_sets.append(object_results)

        # 3. Search Transcript
        transcript_text = query_data.get("transcript") or query_data.get("audio")
        if transcript_text:
            transcript_results = search_system.transcript_search(transcript_text)
            result_sets.append(transcript_results)

        # Giao các tập kết quả
        results = search_system.intersect(result_sets)

        for item in results:
            vid = item.get("video_id")
            # Lấy FPS từ Cache RAM, mặc định 25 nếu không tìm thấy
            item["fps"] = VIDEO_METADATA.get(vid, 25.0)

        logger.info(f"Search completed. Number of results: {len(results)}")
        return jsonify(results)
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


@app.route("/videos/<path:video_id>")
def serve_video_file(video_id):
    try:
        filename = f"{video_id}.mp4"
        return send_from_directory(config.VIDEOS_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        return "Video not found", 404


HLS_DIR = os.path.join(os.getcwd(), "data", "hls")


@app.route("/hls/<string:video_id>/<path:filename>")
def serve_hls(video_id, filename):
    """
    API phục vụ file playlist (.m3u8) và segment (.ts)
    """
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
    """
    Thực hiện Login và lấy danh sách Evaluation
    """
    try:
        # 1. Login
        login_url = f"{config.EVAL_SERVER_URL}/api/v2/login"
        creds = request.get_json() or {}
        username = creds.get("username", config.EVAL_USERNAME)
        password = creds.get("password", config.EVAL_PASSWORD)

        login_resp = requests.post(
            login_url, json={"username": username, "password": password}, verify=False
        )
        if login_resp.status_code != 200:
            return (
                jsonify(
                    {
                        "error": "Login failed on remote server",
                        "details": login_resp.text,
                    }
                ),
                401,
            )

        session_id = login_resp.json().get("sessionId")

        # 2. Get Evaluation List
        list_url = f"{config.EVAL_SERVER_URL}/api/v2/client/evaluation/list"
        list_resp = requests.get(list_url, params={"session": session_id})

        if list_resp.status_code != 200:
            return (
                jsonify(
                    {
                        "error": "Failed to get evaluation list",
                        "details": list_resp.text,
                    }
                ),
                400,
            )

        eval_list = list_resp.json()
        if not eval_list:
            return jsonify({"error": "No evaluations found"}), 404

        # --- UPDATE: Trả về toàn bộ danh sách để Client chọn ---
        return jsonify(
            {
                "message": "Login successful",
                "sessionId": session_id,
                "evaluations": eval_list,  # Trả về list
            }
        )

    except Exception as e:
        logger.error(f"Login proxy error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/submit", methods=["POST"])
def submit_proxy():
    """
    Gửi kết quả submit
    """
    try:
        data = request.get_json()
        session_id = data.get("sessionId")
        evaluation_id = data.get("evaluationId")
        video_id = data.get("videoId")
        time_ms = data.get("timeMs")  # Thời gian tính bằng milliseconds

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

        # Gửi request lên server đánh giá
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
