import os
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import logging
from retrieval_system import VideoRetrievalSystem 
import config
import subprocess
import traceback
from utils.video_metadata import load_video_metadata 

log_file = "system.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # logging.StreamHandler() 
    ]
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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_api():
    if not search_system:
        return jsonify({"error": "Search system is not available."}), 500

    query_data = request.get_json()
    if not query_data:
        return jsonify({"error": "Invalid input: No JSON data received."}), 400

    logger.info(f"Received search request: {query_data}")

    try:
        description = query_data.get('description', '')
        result_sets = []
        
        # 1. Search Text/CLIP
        if description:
            clip_results = search_system.clip_search(description, max_results=1000)
            result_sets.append(clip_results)
    
        # 2. Search Objects
        if query_data.get('objects'):
            object_results = search_system.object_search(
                query_data['objects'], projection={'video_id': 1, 'keyframe_index': 1}
            )
            result_sets.append(object_results)

        # 3. Search Transcript
        transcript_text = query_data.get('transcript') or query_data.get('audio')
        if transcript_text:
            transcript_results = search_system.transcript_search(transcript_text, max_results=1000)
            result_sets.append(transcript_results)

        # Giao các tập kết quả
        results = search_system.intersect(result_sets)
        
        for item in results:
            vid = item.get('video_id')
            # Lấy FPS từ Cache RAM, mặc định 25 nếu không tìm thấy
            item['fps'] = VIDEO_METADATA.get(vid, 25.0)

        logger.info(f"Search completed. Number of results: {len(results)}")
        return jsonify(results[:1000])
    except Exception as e:
        logger.error(f"An error occurred during search: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred during search."}), 500

@app.route('/keyframes/<string:video_id>/keyframe_<int:keyframe_index>.webp')
def serve_frame_image(video_id, keyframe_index):
    try:
        keyframe_dir = os.path.join(config.KEYFRAMES_DIR, video_id)
        filename = f"keyframe_{keyframe_index}.webp"
        return send_from_directory(keyframe_dir, filename)
    except FileNotFoundError:
        return send_from_directory('static', 'placeholder.png'), 404

@app.route('/videos/<path:video_id>')
def serve_video_file(video_id):
    try:
        filename = f"{video_id}.mp4" 
        return send_from_directory(config.VIDEOS_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        return "Video not found", 404

# @app.route("/video-segment/<string:video_id>")
# def serve_video_segment(video_id):
#     """
#     API trả về đoạn video ngắn để preview.
#     Sử dụng ffmpeg cắt video dựa trên start time.
#     """
#     try:
#         start_time = request.args.get('start', '0')
#         duration = request.args.get('duration', '3')
#
#         video_path = os.path.join(config.VIDEOS_DIR, f"{video_id}.mp4")
#         if not os.path.exists(video_path):
#             return "Video not found", 404
#
#         cmd = [
#             "ffmpeg",
#             "-ss", start_time,
#             "-i", video_path,
#             "-t", duration,
#             "-c", "copy",       # Copy stream để nhanh nhất, không encode lại
#             "-f", "mp4",
#             "-movflags", "frag_keyframe+empty_moov",
#             "pipe:1"
#         ]
#
#         # Log lỗi ffmpeg nếu cần debug
#         process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
#
#         def generate():
#             while True:
#                 chunk = process.stdout.read(4096)
#                 if not chunk:
#                     break
#                 yield chunk
#
#         return Response(generate(), mimetype="video/mp4")
#     except Exception as e:
#         logger.error(f"An error occurred during video segment: {e}")
#         return "Error", 500
#


HLS_DIR = os.path.join(os.getcwd(), 'data', 'hls')

@app.route('/hls/<string:video_id>/<path:filename>')
def serve_hls(video_id, filename):
    """
    API phục vụ file playlist (.m3u8) và segment (.ts)
    """
    try:
        video_hls_path = os.path.join(HLS_DIR, video_id)
        # Cache 1 năm (31536000s) vì file HLS không bao giờ thay đổi
        response = send_from_directory(video_hls_path, filename)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        return response
    except FileNotFoundError:
        return "File not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
