import glob
import json
import logging
import os

logger = logging.getLogger(__name__)


def load_video_metadata(metadata_path: str = "video_metadata.json") -> dict:
    """
    Tải metadata (FPS) của video từ file JSON có sẵn.
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


def load_shot_boundaries(shots_dir: str = "data/shots") -> dict:
    """
    Load toàn bộ file JSON trong data/shots vào RAM để tra cứu nhanh.
    Return structure: { "Video_ID": [ {"start_frame": 0, "end_frame": 50}, ... ] }
    """
    shots_map = {}
    if not os.path.exists(shots_dir):
        logger.warning(f"Shots directory not found at {shots_dir}")
        return shots_map

    logger.info(f"Loading shot boundaries from {shots_dir}...")
    json_files = glob.glob(os.path.join(shots_dir, "*.json"))

    for fpath in json_files:
        try:
            # Filename format expected: L01_V001_shots.json -> Key: L01_V001
            filename = os.path.basename(fpath)
            video_id = filename.replace("_shots.json", "")

            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # data structure: {"total": 305, "items": [{"start_frame":...}, ...]}
                if "items" in data:
                    shots_map[video_id] = data["items"]
        except Exception as e:
            logger.error(f"Error loading shot file {fpath}: {e}")

    logger.info(f"Loaded shots for {len(shots_map)} videos.")
    return shots_map
