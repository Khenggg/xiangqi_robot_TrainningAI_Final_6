"""Validate a clone/runtime without connecting to camera or robot."""
import argparse
import importlib
import os
from pathlib import Path
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def check_assets(config):
    required = ["main.py", "models/best.pt", "models/cchess/pose_4_v6.onnx",
                "models/cchess/layout_nano_v3.onnx", "assets/ui/ink-jade-landscape-1440x1080.png", config.MOONFISH_EXE]
    if config.VISUAL_HEIGHT_PICK_ENABLED or config.VISUAL_RING_PICK_ENABLED:
        required.append(config.VISUAL_CAMERA_INTRINSICS_PATH)
    if config.VISUAL_TOP_FACE_ENABLED:
        required.append(config.VISUAL_PICK_GEOMETRY_PATH)
    for name in required:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing/empty project asset: {path}. Clone/extract the complete repository.")
        with path.open("rb") as source:
            if source.read(128).startswith(b"version https://git-lfs.github.com/spec/"):
                raise RuntimeError(f"Asset is a Git LFS pointer: {path}. Run git lfs pull.")
    print("Project assets OK", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-only", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError(f"Python 3.12 x64 required; current interpreter: {sys.executable}")
    print(f"Python: {sys.executable}", flush=True)
    import config
    check_assets(config)
    if args.assets_only:
        return
    for module in ("cv2", "pygame", "numpy", "requests", "torch", "torchvision", "ultralytics", "onnxruntime"):
        importlib.import_module(module)
        print(f"Import OK: {module}", flush=True)
    from ultralytics import YOLO
    YOLO(str(ROOT / "models/best.pt"))
    print("YOLO + models/best.pt OK", flush=True)
    from src.vision.cchess_recognizer import CChessRecognizer
    CChessRecognizer(ROOT / "models/cchess/pose_4_v6.onnx", ROOT / "models/cchess/layout_nano_v3.onnx")
    print("CChess ONNX models OK", flush=True)
    if config.VISUAL_HEIGHT_PICK_ENABLED or config.VISUAL_RING_PICK_ENABLED:
        from src.vision.height_pick_geometry import load_intrinsics
        load_intrinsics(ROOT / config.VISUAL_CAMERA_INTRINSICS_PATH,
                        config.VIDEO_SOURCE, (config.VIDEO_FRAME_WIDTH, config.VIDEO_FRAME_HEIGHT))
        print("Bundled camera intrinsics OK", flush=True)
    # Imports only: never import main or instantiate HardwareManager.
    for module in ("src.hardware.hardware_manager", "src.core.game_state", "src.ui.board_renderer",
                   "src.ui.input_handler", "src.ui.debug_dashboard"):
        importlib.import_module(module)
    print("Runtime preflight OK (no camera/robot connection attempted)", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print("\nPreflight failed. Run SETUP_WINDOWS.bat; keep the full error/log for diagnosis.", file=sys.stderr)
        sys.exit(1)
