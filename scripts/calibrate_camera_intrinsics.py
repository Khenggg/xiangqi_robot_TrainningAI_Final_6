"""Camera intrinsics only: no board clicks, top-rim profile or robot tests."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import config
from scripts.calibrate_pick_geometry import capture_pattern, read_frame, WINDOW
from src.vision.height_pick_geometry import load_intrinsics


from src.vision.camera_source import open_camera


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=config.VIDEO_SOURCE)
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf", "any"), default=config.VIDEO_BACKEND)
    parser.add_argument("--square-mm", type=float, required=True,
                        help="Measured printed checkerboard square size")
    parser.add_argument("--cols", type=int, default=9)
    parser.add_argument("--rows", type=int, default=6)
    parser.add_argument("--output", type=Path, default=ROOT / config.VISUAL_CAMERA_INTRINSICS_PATH)
    args = parser.parse_args()
    cap = open_camera(args.camera, args.backend)
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.VIDEO_FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.VIDEO_FRAME_HEIGHT)
        if not cap.isOpened():
            raise RuntimeError("Camera unavailable; close RUN first")
        # Use the same requested resolution as HardwareManager; record actual frame size.
        for _ in range(30):
            cap.read()
        frame = read_frame(cap)
        frame_size = frame.shape[1::-1]
        cv2.namedWindow(WINDOW)
        rms, k, dist, views = capture_pattern(
            cap, (args.cols, args.rows), args.square_mm, frame_size,
            diagnostic_path=args.output.parent / f"intrinsic_samples_camera{args.camera}.npz")
        data = {"schema": 1, "camera_index": args.camera, "frame_size": list(frame_size),
                "camera_matrix": k.tolist(), "distortion": dist.ravel().tolist(),
                "intrinsic_rms_px": float(rms), "views": views,
                "pattern": {"inner_corners": [args.cols, args.rows], "square_mm": args.square_mm}}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            load_intrinsics(temporary, args.camera, frame_size)
            if args.output.exists():
                from datetime import datetime, timezone
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
                args.output.with_name(args.output.name + ".backup-" + stamp).write_bytes(args.output.read_bytes())
            os.replace(temporary, args.output)
        finally:
            if temporary.exists():
                temporary.unlink()
        print(f"Saved intrinsics: {args.output}; RMS={rms:.3f}px; frame={frame_size}")
        print("Enter measured VISUAL_HEIGHT_PIECE_MM in config.py, then run normal board AUTO CALIBRATION.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled; existing calibration preserved.")
    except Exception as exc:
        print(f"Calibration failed: {exc}")
        sys.exit(1)
