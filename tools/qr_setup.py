"""Generate QR PNGs and bind a measured planar camera/robot reference offline."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from src.vision.qr_calibration import BoardGeometry, QRCalibrator
from src.hardware.board_robot_mapping import BoardRobotMapping


def make_markers(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    encoder = cv2.QRCodeEncoder_create()
    for corner in ("TL", "TR", "BR", "BL"):
        code = encoder.encode("XQ:" + corner)
        # Extra quiet zone; nearest-neighbour keeps modules sharp for printing.
        code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        path = output / f"XQ_{corner}.png"
        if path.exists():
            raise FileExistsError(f"Refusing to replace {path}")
        if not cv2.imwrite(str(path), cv2.resize(code, None, fx=12, fy=12, interpolation=cv2.INTER_NEAREST)):
            raise OSError(f"Could not write {path}")
        print(path)


def bind(image_path, layout, robot_points, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to replace {output}; choose a new reference path")
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise ValueError("Cannot read reference image")
    cal = QRCalibrator(BoardGeometry.load(layout), stable_frames=1).update(frame)
    if cal is None:
        raise ValueError("Reference image must contain all four readable QR codes")
    data = json.loads(Path(robot_points).read_text(encoding="utf-8"))
    data.update(camera_points_px=cal.corners_px.tolist(), frame_size=list(cal.frame_size))
    mapping = BoardRobotMapping(data, lambda: cal)
    mapping.begin()
    mapping.end()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {output}. Camera must remain fixed relative to robot.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    markers = sub.add_parser("markers")
    markers.add_argument("--out", type=Path, default=Path("assets/qr_markers"))
    reference = sub.add_parser("bind")
    for flag in ("image", "layout", "robot-points", "out"):
        reference.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "markers":
        make_markers(args.out)
    else:
        bind(args.image, args.layout, args.robot_points, args.out)


if __name__ == "__main__":
    main()
