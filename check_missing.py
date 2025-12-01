import glob
import os
import sys
from pathlib import Path


# --- CẤU HÌNH MÀU SẮC CHO TERMINAL ---
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


# --- ĐƯỜNG DẪN CẤU HÌNH (Tương đối với folder /data) ---
BASE_DIR = Path(__file__).parent.absolute()
VIDEOS_DIR = BASE_DIR / "data/videos"
KEYFRAMES_DIR = BASE_DIR / "data/keyframes"
EMBEDDINGS_DIR = BASE_DIR / "data/embeddings"
OBJECTS_DIR = BASE_DIR / "data/objects"
TRANSCRIPTS_DIR = BASE_DIR / "data/transcripts"
SHOTS_DIR = BASE_DIR / "data/shots"  # <--- Đã thêm folder shots


def get_frame_indices(folder_path, extension):
    """Lấy danh sách các index của frame từ tên file (vd: keyframe_100.webp -> 100)"""
    indices = set()
    if not os.path.exists(folder_path):
        return indices

    files = glob.glob(os.path.join(folder_path, f"*{extension}"))
    for f in files:
        try:
            # Filename format expected: keyframe_123.pt or keyframe_123.webp
            name = Path(f).stem  # keyframe_123
            parts = name.split("_")
            if len(parts) > 1 and parts[-1].isdigit():
                indices.add(int(parts[-1]))
        except:
            continue
    return indices


def check_integrity():
    print(
        f"{Colors.HEADER}=== BẮT ĐẦU KIỂM TRA TOÀN VẸN DỮ LIỆU (CÓ SHOTS) ==={Colors.ENDC}"
    )
    print(f"Source of Truth: {VIDEOS_DIR}\n")

    if not VIDEOS_DIR.exists():
        print(
            f"{Colors.FAIL}LỖI NGHIÊM TRỌNG: Không tìm thấy folder videos tại {VIDEOS_DIR}{Colors.ENDC}"
        )
        return

    # Lấy danh sách video gốc
    video_files = sorted(list(VIDEOS_DIR.glob("*.mp4")))
    total_videos = len(video_files)

    if total_videos == 0:
        print(
            f"{Colors.WARNING}Không tìm thấy file .mp4 nào trong folder videos.{Colors.ENDC}"
        )
        return

    print(
        f"Tìm thấy {Colors.BOLD}{total_videos}{Colors.ENDC} videos. Đang kiểm tra từng video...\n"
    )

    missing_summary = {
        "transcripts": [],
        "objects": [],
        "shots": [],  # <--- Theo dõi shots bị thiếu
        "keyframes_folder": [],
        "embeddings_folder": [],
        "empty_keyframes": [],
        "empty_embeddings": [],
        "sync_errors": [],
    }

    for video_path in video_files:
        video_id = video_path.stem  # Ví dụ: L01_V001

        # 1. KIỂM TRA TRANSCRIPT
        has_transcript = (TRANSCRIPTS_DIR / f"{video_id}.csv").exists() or (
            TRANSCRIPTS_DIR / f"{video_id}.txt"
        ).exists()
        if not has_transcript:
            missing_summary["transcripts"].append(video_id)

        # 2. KIỂM TRA OBJECT DETECTION
        has_object = (OBJECTS_DIR / f"{video_id}_rfdetr_results.csv").exists() or (
            OBJECTS_DIR / f"{video_id}_rfdetr_results.json"
        ).exists()
        if not has_object:
            missing_summary["objects"].append(video_id)

        # 3. KIỂM TRA SHOTS (MỚI THÊM)
        # Định dạng file: L01_V001_shots.json
        has_shots = (SHOTS_DIR / f"{video_id}_shots.json").exists()
        if not has_shots:
            missing_summary["shots"].append(video_id)

        # 4. KIỂM TRA KEYFRAMES (IMAGES)
        kf_path = KEYFRAMES_DIR / video_id
        kf_exists = kf_path.exists() and kf_path.is_dir()

        kf_indices = set()
        if not kf_exists:
            missing_summary["keyframes_folder"].append(video_id)
        else:
            kf_indices = get_frame_indices(kf_path, ".webp")
            if len(kf_indices) == 0:
                missing_summary["empty_keyframes"].append(video_id)

        # 5. KIỂM TRA EMBEDDINGS (VECTORS)
        emb_path = EMBEDDINGS_DIR / video_id
        emb_exists = emb_path.exists() and emb_path.is_dir()

        emb_indices = set()
        if not emb_exists:
            missing_summary["embeddings_folder"].append(video_id)
        else:
            emb_indices = get_frame_indices(emb_path, ".pt")
            if len(emb_indices) == 0:
                missing_summary["empty_embeddings"].append(video_id)

        # 6. KIỂM TRA ĐỒNG BỘ (SYNC CHECK)
        if kf_exists and emb_exists:
            missing_emb = kf_indices - emb_indices
            missing_img = emb_indices - kf_indices

            if missing_emb or missing_img:
                error_msg = f"{video_id}: "
                if missing_emb:
                    error_msg += f"Thiếu {len(missing_emb)} vectors. "
                if missing_img:
                    error_msg += f"Thiếu {len(missing_img)} ảnh."

                missing_summary["sync_errors"].append(error_msg)

    # --- BÁO CÁO KẾT QUẢ ---
    print(f"{Colors.HEADER}=== TỔNG HỢP KẾT QUẢ ==={Colors.ENDC}")

    has_error = False

    # Report Transcript
    if missing_summary["transcripts"]:
        has_error = True
        print(
            f"\n{Colors.WARNING}[!] Thiếu Transcript ({len(missing_summary['transcripts'])} videos):{Colors.ENDC}"
        )
        print(
            ", ".join(missing_summary["transcripts"][:10])
            + ("..." if len(missing_summary["transcripts"]) > 10 else "")
        )

    # Report Objects
    if missing_summary["objects"]:
        has_error = True
        print(
            f"\n{Colors.WARNING}[!] Thiếu Object Data ({len(missing_summary['objects'])} videos):{Colors.ENDC}"
        )
        print(
            ", ".join(missing_summary["objects"][:10])
            + ("..." if len(missing_summary["objects"]) > 10 else "")
        )

    # Report Shots (MỚI)
    if missing_summary["shots"]:
        has_error = True
        print(
            f"\n{Colors.WARNING}[!] Thiếu Shot Boundary Data ({len(missing_summary['shots'])} videos):{Colors.ENDC}"
        )
        print(
            ", ".join(missing_summary["shots"][:10])
            + ("..." if len(missing_summary["shots"]) > 10 else "")
        )

    # Report Missing Folders
    if missing_summary["keyframes_folder"]:
        has_error = True
        print(
            f"\n{Colors.FAIL}[X] Thiếu hoàn toàn folder Keyframes ({len(missing_summary['keyframes_folder'])} videos):{Colors.ENDC}"
        )
        print(", ".join(missing_summary["keyframes_folder"]))

    if missing_summary["embeddings_folder"]:
        has_error = True
        print(
            f"\n{Colors.FAIL}[X] Thiếu hoàn toàn folder Embeddings ({len(missing_summary['embeddings_folder'])} videos):{Colors.ENDC}"
        )
        print(", ".join(missing_summary["embeddings_folder"]))

    # Report Empty Folders
    if missing_summary["empty_keyframes"]:
        has_error = True
        print(
            f"\n{Colors.FAIL}[X] Folder Keyframes rỗng ({len(missing_summary['empty_keyframes'])} videos):{Colors.ENDC}"
        )
        print(", ".join(missing_summary["empty_keyframes"]))

    if missing_summary["empty_embeddings"]:
        has_error = True
        print(
            f"\n{Colors.FAIL}[X] Folder Embeddings rỗng ({len(missing_summary['empty_embeddings'])} videos):{Colors.ENDC}"
        )
        print(", ".join(missing_summary["empty_embeddings"]))

    # Report Sync Errors
    if missing_summary["sync_errors"]:
        has_error = True
        print(
            f"\n{Colors.FAIL}[X] Lỗi bất đồng bộ giữa Ảnh và Vector ({len(missing_summary['sync_errors'])} videos):{Colors.ENDC}"
        )
        for err in missing_summary["sync_errors"][:20]:
            print(f"  - {err}")
        if len(missing_summary["sync_errors"]) > 20:
            print(f"  ... và {len(missing_summary['sync_errors']) - 20} lỗi khác.")

    if not has_error:
        print(
            f"\n{Colors.OKGREEN}TUYỆT VỜI! Dữ liệu (gồm cả Shots) hoàn toàn đầy đủ và đồng bộ.{Colors.ENDC}"
        )
    else:
        print(
            f"\n{Colors.BOLD}Kiểm tra hoàn tất. Vui lòng xem lại các mục đánh dấu màu đỏ hoặc vàng ở trên.{Colors.ENDC}"
        )


if __name__ == "__main__":
    check_integrity()
