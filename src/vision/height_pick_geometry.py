"""BBox height correction with pose rebuilt from the current board calibration."""
import json
from pathlib import Path

import cv2
import numpy as np

from src.vision.pick_geometry import BOARD_CORNERS, PickGeometry, finite_array
from src.vision.visual_pick_estimator import VisualPickEstimator, GridTarget


def aggregate_height_targets(observations, expected_cell, min_samples=2, max_spread=.12):
    """Mean of coherent observations; otherwise guarded top-three median."""
    if not 2 <= min_samples <= 5 or not np.isfinite(max_spread) or max_spread <= 0:
        raise ValueError("Invalid height aggregation limits")
    targets = [t for t in observations if t is not None]
    if len(targets) < min_samples:
        return None, "insufficient measured samples"
    points = np.array([[t.col, t.row] for t in targets])
    if not np.isfinite(points).all() or not np.isfinite([t.confidence for t in targets]).all():
        return None, "nonfinite measured samples"
    median = np.median(points, axis=0)
    if np.max(np.linalg.norm(points-median, axis=1)) <= max_spread:
        center, method = np.mean(points, axis=0), "mean"
        support = targets
    else:
        if len(targets) < 3:
            return None, "unstable samples; need three for median"
        support = sorted(targets, key=lambda t: t.confidence, reverse=True)[:3]
        chosen = np.array([[t.col, t.row] for t in support])
        center, method = np.median(chosen, axis=0), "top3-median"
        if np.max(np.linalg.norm(chosen-center, axis=1)) > max_spread:
            return None, "top-three samples too dispersed"
    return GridTarget(float(center[0]), float(center[1]),
                      float(np.mean([t.confidence for t in support])),
                      float(np.linalg.norm(center-np.asarray(expected_cell)))), method


def load_intrinsics(path, camera_index, frame_size):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (data.get("schema") != 1 or data.get("camera_index") != camera_index
            or tuple(data.get("frame_size", ())) != tuple(frame_size)):
        raise ValueError("Intrinsics camera/resolution differs from active camera")
    k = finite_array(data["camera_matrix"], (3, 3))
    distortion = finite_array(data["distortion"]).reshape(-1)
    if (k[0, 0] <= 0 or k[1, 1] <= 0 or not np.allclose(k[2], [0, 0, 1])
            or k[0, 1] != 0 or k[1, 0] != 0
            or len(distortion) not in (4, 5, 8, 12, 14)):
        raise ValueError("Invalid camera intrinsics")
    return k, distortion


def geometry_from_board(intrinsics_path, perspective, camera_index, frame_size,
                        board_mm, piece_height_mm, max_error_px=3.0):
    """Four actual board corners only; no fabricated independent intersections."""
    k, distortion = load_intrinsics(intrinsics_path, camera_index, frame_size)
    dimensions = finite_array(board_mm, (2,))
    if (np.any(dimensions <= 0) or piece_height_mm is None
            or not np.isfinite(piece_height_mm) or piece_height_mm <= 0
            or not np.isfinite(max_error_px) or max_error_px <= 0):
        raise ValueError("Measure board dimensions and piece height first")
    matrix = finite_array(perspective, (3, 3))
    pixels = cv2.perspectiveTransform(BOARD_CORNERS.reshape(1, 4, 2), np.linalg.inv(matrix))[0]
    if (not np.isfinite(pixels).all() or np.any(pixels < 0)
            or np.any(pixels >= np.asarray(frame_size))
            or abs(cv2.contourArea(pixels.astype(np.float32))) < 1):
        raise ValueError("Invalid active board corners")
    world = np.column_stack((BOARD_CORNERS * dimensions / [8, 9], np.zeros(4)))
    ok, rvec, tvec = cv2.solvePnP(world, pixels, k, distortion, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError("Board pose estimation failed")
    projected = cv2.projectPoints(world, rvec, tvec, k, distortion)[0].reshape(4, 2)
    error = float(np.max(np.linalg.norm(projected-pixels, axis=1)))
    if not np.isfinite(error) or error > max_error_px:
        raise ValueError(f"Board pose inconsistent with intrinsics: {error:.2f}px")
    geometry = PickGeometry({
        "schema": 1, "camera_matrix": k.tolist(), "distortion": distortion.tolist(),
        "rvec": rvec.ravel().tolist(), "tvec": tvec.ravel().tolist(),
        "board_mm": dimensions.tolist(), "piece_height_mm": float(piece_height_mm),
        "frame_size": list(frame_size), "camera_index": int(camera_index),
    }, require_validation=False)
    geometry.pose_error_px = error
    return geometry


class HeightPickEstimator(VisualPickEstimator):
    """Same selection/temporal checks as bbox picks, with a height-aware mapping."""
    def __init__(self, geometry, min_confidence=.45, max_offset_cells=.25,
                 outside_margin_mm=None):
        self.geometry = geometry
        self.min_confidence = float(min_confidence)
        self.max_offset_cells = float(max_offset_cells)
        self._configure_outside_margin((geometry.width, geometry.height), outside_margin_mm)

    def _box_to_grid(self, box):
        x1, y1, x2, y2 = finite_array(box, (4,))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Invalid bbox")
        xy = self.geometry.pixels_to_top_xy([[(x1+x2)/2, (y1+y2)/2]])
        col, row = self.geometry.xy_to_grid(xy)[0]
        return float(col), float(row)

    def estimate_pick_target(self, detections, expected_col, expected_row):
        self.last_box = None
        target = super().estimate_pick_target(detections, expected_col, expected_row)
        if target is not None:
            for _, confidence, box in detections or []:
                if float(confidence) < self.min_confidence:
                    continue
                try:
                    col, row = self._box_to_grid(box)
                except (ValueError, TypeError, cv2.error):
                    continue
                if np.allclose([col, row], [target.col, target.row], atol=1e-8, rtol=0) and float(confidence) == target.confidence:
                    self.last_box = tuple(map(float, box))
                    break
        return target
