import glob
import json
import logging
import os
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


def load_video_metadata(
    videos_dir: str, cache_path: str = "data/video_metadata_cache.json"
) -> dict:
    """
    Tải metadata (FPS) của video.
    Ưu tiên đọc từ file JSON cache để tăng tốc độ khởi động.
    Nếu không có cache, sẽ quét thư mục và tạo cache mới.
    """

    # 1. Cố gắng đọc từ Cache trước
    if os.path.exists(cache_path):
        logger.info(f"Found metadata cache at '{cache_path}'. Loading...")
        try:
            with open(cache_path, "r") as f:
                metadata_cache = json.load(f)
            logger.info(
                f"Metadata loaded successfully from cache ({len(metadata_cache)} videos)."
            )
            return metadata_cache
        except Exception as e:
            logger.warning(
                f"Failed to read cache file: {e}. Fallback to scanning directory."
            )

    # 2. Nếu không có cache, thực hiện quét đĩa (Thao tác nặng)
    metadata_cache = {}

    if not os.path.exists(videos_dir):
        logger.error(f"Directory not found: {videos_dir}")
        return metadata_cache

    video_files = glob.glob(os.path.join(videos_dir, "*.mp4"))
    logger.info(
        f"Scanning {len(video_files)} videos in '{videos_dir}' to extract FPS (First run only)..."
    )

    for i, video_path in enumerate(video_files):
        try:
            video_id = Path(video_path).stem  # Lấy tên file làm ID (VD: L01_V001)
            cap = cv2.VideoCapture(video_path)

            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                # Fallback nếu không đọc được FPS hoặc FPS lỗi
                if fps is None or fps <= 0:
                    fps = 25.0

                metadata_cache[video_id] = float(fps)
                cap.release()
            else:
                logger.warning(f"Could not open video: {video_path}")
                metadata_cache[video_id] = 25.0  # Fallback safe

        except Exception as e:
            logger.error(f"Error reading metadata for {video_path}: {e}")
            metadata_cache[video_id] = 25.0

        # Log tiến độ mỗi 100 video để biết server không bị treo
        if (i + 1) % 100 == 0:
            logger.info(f"Processed {i + 1}/{len(video_files)} videos...")

    # 3. Lưu kết quả vào Cache
    try:
        # Đảm bảo thư mục chứa cache tồn tại
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        with open(cache_path, "w") as f:
            json.dump(metadata_cache, f, indent=2)
        logger.info(
            f"Saved metadata cache to '{cache_path}'. Next startup will be instant."
        )
    except Exception as e:
        logger.error(f"Failed to save metadata cache: {e}")

    return metadata_cache

def load_shot_metadata(shots_dir: str, cache_path: str = "data/shot_metadata_cache.json") -> dict:
    """
    Tải metadata (shot info) của video keyframes.
    Ưu tiên đọc từ file JSON cache để tăng tốc độ khởi động.
    Nếu không có cache, sẽ quét thư mục và tạo cache mới.
    """

    # 1. Cố gắng đọc từ Cache trước
    if os.path.exists(cache_path):
        logger.info(f"Found shot metadata cache at '{cache_path}'. Loading...")
        try:
            with open(cache_path, "r") as f:
                shot_metadata_cache = json.load(f)
            logger.info(
                f"Shot metadata loaded successfully from cache ({len(shot_metadata_cache)} videos)."
            )
            return shot_metadata_cache
        except Exception as e:
            logger.warning(
                f"Failed to read shot cache file: {e}. Fallback to scanning directory."
            )

    # 2. Nếu không có cache, thực hiện quét đĩa
    shot_metadata_cache = {}

    if not os.path.exists(shots_dir):
        logger.error(f"Directory not found: {shots_dir}")
        return shot_metadata_cache

    shot_files = glob.glob(os.path.join(shots_dir, "*.json"))
    logger.info(
        f"Scanning {len(shot_files)} shot files in '{shots_dir}' to extract shot info (First run only)..."
    )

    for i, shot_path in enumerate(shot_files):
        try:
            video_id = Path(shot_path).stem  # Lấy tên file làm ID (VD: L01_V001)
            video_id = video_id.replace("_shots", "")  # Loại bỏ hậu tố _shots
            with open(shot_path, "r") as f:
                shot_data = json.load(f)
            shot_items = shot_data.get("items", [])
            reverse_map = {}

            for shot_id, shot in enumerate(shot_items):
                start = shot["start_frame"]
                end = shot["end_frame"]

                # map every frame in this range to this shot
                for frame in range(start, end + 1):
                    reverse_map[frame] = shot_id

            shot_metadata_cache[video_id] = reverse_map

        except Exception as e:
            logger.error(f"Error reading shot metadata for {shot_path}: {e}")
            shot_metadata_cache[video_id] = {}

        # Log tiến độ mỗi 100 file để biết server không bị treo
        if (i + 1) % 100 == 0:
            logger.info(f"Processed {i + 1}/{len(shot_files)} shot files...")

    # 3. Lưu kết quả vào Cache
    try:
        # Đảm bảo thư mục chứa cache tồn tại
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(shot_metadata_cache, f, indent=2)
        logger.info(
            f"Saved shot metadata cache to '{cache_path}'. Next startup will be instant."
        )
    except Exception as e:
        logger.error(f"Failed to save shot metadata cache: {e}")
    return shot_metadata_cache

load_shot_metadata("")