"""Interactive, camera-only validation for visual pick correction.

This does not initialize :class:`FR5Robot`, send a robot command, or change
``config.py``.  It exercises the same YOLO-box -> ``VisualPickEstimator`` path
used immediately before a real pick, then records its accuracy and stability.

Usage (from the repository root)::

    .\\.venv312\\Scripts\\python.exe tests\\visual_pick_validation.py

Place one clearly visible piece with its *physical centre* on the prompted
board intersection.  Press SPACE to collect the configured sample count at
that position.  Press Q to stop early.  Results are placed under
``tests/results/visual_pick_<timestamp>/``.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import config
from src.vision.visual_pick_estimator import VisualPickEstimator
from src.vision.camera_source import open_camera

try:
    from ultralytics import YOLO
except ImportError as exc:  # pragma: no cover - only reached on an incomplete setup
    raise SystemExit("Missing ultralytics. Run this with the project virtual environment.") from exc


# Spread over corners, edges, river, and centre; all coordinates are (col, row).
DEFAULT_POINTS = (
    (0, 0), (4, 0), (8, 0), (0, 4), (4, 4), (8, 4), (0, 5), (4, 5),
    (8, 5), (0, 9), (4, 9), (8, 9), (2, 2), (6, 2), (2, 7), (6, 7),
)


def parse_points(value: str | None) -> tuple[tuple[float, float], ...]:
    if not value:
        return DEFAULT_POINTS
    try:
        points = tuple(tuple(map(float, item.split(","))) for item in value.split(";"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--points must look like '0,0;4,4;8,9'") from exc
    if not points or any(len(point) != 2 or not (0 <= point[0] <= 8 and 0 <= point[1] <= 9)
                         for point in points):
        raise argparse.ArgumentTypeError("every point must be a board coordinate: 0<=col<=8, 0<=row<=9")
    return points


def error_mm(actual_col: float, actual_row: float, expected_col: float, expected_row: float) -> float:
    """Grid error converted with the project board's configured physical pitches."""
    return math.hypot(
        (actual_col - expected_col) * float(config.CELL_SIZE_X),
        (actual_row - expected_row) * float(config.CELL_SIZE_Y),
    )


def draw_overlay(frame, detections, target, expected, inverse_matrix, status):
    image = frame.copy()
    for _cls_id, confidence, (x1, y1, x2, y2) in detections:
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 150, 255), 1)
        cv2.putText(image, f"{confidence:.2f}", (int(x1), max(15, int(y1) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 150, 255), 1)
    expected_pixel = cv2.perspectiveTransform(
        np.array([[[expected[0], expected[1]]]], dtype=np.float32), inverse_matrix)[0][0]
    cv2.drawMarker(image, tuple(np.int32(expected_pixel)), (0, 255, 255), cv2.MARKER_CROSS, 22, 2)
    if target is not None:
        selected_pixel = cv2.perspectiveTransform(
            np.array([[[target.col, target.row]]], dtype=np.float32), inverse_matrix)[0][0]
        cv2.circle(image, tuple(np.int32(selected_pixel)), 7, (0, 255, 0), 2)
        message = (f"target=({target.col:.3f},{target.row:.3f}) "
                   f"error={error_mm(target.col, target.row, *expected):.2f} mm")
    else:
        message = "REJECTED -> real system would use logical cell centre"
    cv2.putText(image, status, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(image, message, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="Camera-only visual-pick validation (no robot commands).")
    parser.add_argument("--camera", type=int, default=int(config.VIDEO_SOURCE))
    parser.add_argument("--samples", type=int, default=30, help="consecutive frames to collect at each point")
    parser.add_argument("--lighting-profile", default="unknown",
                        help="environment label, e.g. lab_standard, dim, glare, side_shadow")
    parser.add_argument("--notes", default="", help="optional setup notes, e.g. LED 500 lux, exposure locked")
    parser.add_argument("--points", help="semicolon-separated expected grid points, e.g. 0,0;4,4;8,9")
    parser.add_argument("--model", type=Path, default=PROJECT_DIR / "models" / "best.pt")
    parser.add_argument("--perspective", type=Path, default=PROJECT_DIR / "perspective.npy")
    parser.add_argument("--output", type=Path, default=PROJECT_DIR / "tests" / "results")
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2 so stability can be measured")
    points = parse_points(args.points)
    if not args.model.is_file() or not args.perspective.is_file():
        parser.error("model or perspective file does not exist; calibrate camera first")

    profile = re.sub(r"[^A-Za-z0-9_-]+", "_", args.lighting_profile).strip("_") or "unknown"
    run_dir = args.output / f"visual_pick_{profile}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "run_metadata.json").write_text(json.dumps({
        "lighting_profile": profile,
        "notes": args.notes,
        "camera_index": args.camera,
        "samples_per_point": args.samples,
        "visual_pick_min_confidence": config.VISUAL_PICK_MIN_CONFIDENCE,
        "visual_pick_max_offset_cells": config.VISUAL_PICK_MAX_OFFSET_CELLS,
        "visual_pick_foot_ratio": config.VISUAL_PICK_FOOT_RATIO,
    }, indent=2), encoding="utf-8")
    estimator = VisualPickEstimator(args.perspective, config.VISUAL_PICK_MIN_CONFIDENCE,
                                    config.VISUAL_PICK_MAX_OFFSET_CELLS,
                                    config.VISUAL_PICK_FOOT_RATIO)
    inverse_matrix = np.linalg.inv(estimator._matrix)
    model = YOLO(str(args.model))
    try:
        cap = open_camera(args.camera)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    rows: list[dict] = []
    try:
        for point_index, expected in enumerate(points, start=1):
            collected = 0
            recording = False
            print(f"\n[{point_index}/{len(points)}] Put one piece at grid {expected}. Press SPACE to record.")
            while collected < args.samples:
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Camera frame read failed")
                result = model.predict(frame, conf=config.VISUAL_PICK_MIN_CONFIDENCE,
                                       iou=0.35, imgsz=640, verbose=False)[0]
                detections = [(int(box.cls[0]), float(box.conf[0]), tuple(map(float, box.xyxy[0])))
                              for box in result.boxes]
                target = estimator.estimate_pick_target(detections, *expected)
                display = draw_overlay(frame, detections, target, expected, inverse_matrix,
                                       f"Point {point_index}/{len(points)} | "
                                       f"{'RECORDING' if recording else 'SPACE start'} | "
                                       f"{collected}/{args.samples}")
                cv2.imshow("Visual Pick Validation — CAMERA ONLY", display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    return write_results(run_dir, rows, cancelled=True, lighting_profile=profile)
                if key == ord(" ") and not recording:
                    recording = True
                    print(f"  Recording {args.samples} consecutive frames...")
                    continue
                if not recording:
                    continue
                row = {"point": point_index, "expected_col": expected[0], "expected_row": expected[1],
                       "accepted": target is not None}
                if target is not None:
                    row.update(actual_col=target.col, actual_row=target.row, confidence=target.confidence,
                               offset_cells=target.offset_cells,
                               error_mm=error_mm(target.col, target.row, *expected))
                else:
                    row.update(actual_col="", actual_row="", confidence="", offset_cells="", error_mm="")
                rows.append(row)
                cv2.imwrite(str(run_dir / f"p{point_index:02d}_s{collected + 1:02d}.png"), display)
                collected += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return write_results(run_dir, rows, cancelled=False, lighting_profile=profile)


def write_results(run_dir: Path, rows: list[dict], cancelled: bool, lighting_profile: str) -> int:
    fields = ["point", "expected_col", "expected_row", "accepted", "actual_col", "actual_row",
              "confidence", "offset_cells", "error_mm"]
    with (run_dir / "samples.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    errors = np.array([float(row["error_mm"]) for row in rows if row["accepted"]], dtype=float)
    accepted = len(errors)
    per_point_stability = {}
    for point in sorted({row["point"] for row in rows}):
        samples = [row for row in rows if row["point"] == point and row["accepted"]]
        if len(samples) < 2:
            per_point_stability[str(point)] = None
            continue
        cols = np.array([float(row["actual_col"]) for row in samples]) * float(config.CELL_SIZE_X)
        rows_mm = np.array([float(row["actual_row"]) for row in samples]) * float(config.CELL_SIZE_Y)
        per_point_stability[str(point)] = float(math.hypot(np.std(cols), np.std(rows_mm)))
    stability_values = [value for value in per_point_stability.values() if value is not None]
    acceptance_rate = accepted / len(rows) if rows else 0.0
    accuracy_pass = bool(accepted and np.median(errors) <= 2.0 and np.percentile(errors, 95) <= 4.0
                         and stability_values and max(stability_values) <= 1.5)
    summary = {
        "lighting_profile": lighting_profile,
        "cancelled": cancelled, "samples_recorded": len(rows), "accepted": accepted,
        "rejected": len(rows) - accepted,
        "acceptance_rate": acceptance_rate,
        "fallback_rate": 1.0 - acceptance_rate,
        "median_error_mm": float(np.median(errors)) if accepted else None,
        "p95_error_mm": float(np.percentile(errors, 95)) if accepted else None,
        "per_point_stability_mm": per_point_stability,
        "worst_stability_mm": max(stability_values) if stability_values else None,
        "visual_correction_accuracy_pass": accuracy_pass,
        "interpretation": "Acceptance/fallback rates are diagnostic measurements, not a universal pass gate. "
                          "A rejected frame maps to None in VisualPickEstimator; production code then uses "
                          "the logical-cell-centre fallback.",
        "accuracy_criteria": "For accepted correction frames: median <= 2.0 mm, p95 <= 4.0 mm, "
                             "and every point's positional standard deviation <= 1.5 mm",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nResults: {run_dir}\n{json.dumps(summary, indent=2)}")
    return 0 if not cancelled else 2


if __name__ == "__main__":
    raise SystemExit(main())
