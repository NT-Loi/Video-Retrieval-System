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
