import json
import logging
import os

logger = logging.getLogger(__name__)


def load_video_metadata(metadata_path: str = "video_metadata.json") -> dict:
    """
    Tải metadata (FPS) của video từ file JSON có sẵn.
    Mặc định tìm file 'video_metadata.json' ở thư mục root.
    """
    if os.path.exists(metadata_path):
        logger.info(f"Loading video metadata from '{metadata_path}'...")
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            logger.info(f"Loaded metadata for {len(metadata)} videos.")
            return metadata
        except Exception as e:
            logger.error(f"Failed to read metadata file: {e}")
            return {}
    else:
        logger.warning(
            f"Metadata file not found at '{metadata_path}'. FPS will default to 25.0."
        )
        return {}
