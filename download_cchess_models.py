import os
import sys
import urllib.request
from pathlib import Path

MODELS = {
    "pose_4_v6.onnx": "https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition/resolve/main/onnx/pose/4_v6-0301.onnx",
    "layout_nano_v3.onnx": "https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition/resolve/main/onnx/layout_recognition/nano_v3-0319.onnx"
}

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def download_file(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 1024 * 1024:
        print(f"[OK] Already downloaded: {dest_path.name} ({dest_path.stat().st_size / (1024 * 1024):.1f} MB)")
        return

    print(f"[DOWNLOADING] {dest_path.name} from {url} ...")
    
    def reporthook(count, block_size, total_size):
        if total_size > 0:
            percent = count * block_size * 100 / total_size
            downloaded_mb = (count * block_size) / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            sys.stdout.write(f"\r  Progress: {percent:5.1f}% ({downloaded_mb:.1f} / {total_mb:.1f} MB)")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, str(dest_path), reporthook=reporthook)
    sys.stdout.write("\n")
    print(f"[OK] Finished: {dest_path.name} ({dest_path.stat().st_size / (1024 * 1024):.1f} MB)")

def main():
    base_dir = Path(__file__).resolve().parent
    models_dir = base_dir / "models" / "cchess"
    models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("[CChess Models] Downloading ONNX models from HuggingFace...")
    print("=" * 60)

    for filename, url in MODELS.items():
        dest = models_dir / filename
        download_file(url, dest)

    print("\n[SUCCESS] All ONNX models ready at:", models_dir)

if __name__ == "__main__":
    main()
