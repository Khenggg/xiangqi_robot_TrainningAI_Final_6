"""Estimate a safe, camera-corrected board coordinate for picking a piece."""
from dataclasses import dataclass
from pathlib import Path
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class GridTarget:
    """Camera-derived pick point in continuous Xiangqi grid coordinates."""

    col: float
    row: float
    confidence: float
    offset_cells: float


class VisualPickEstimator:
    """Maps fresh YOLO boxes to conservative, expected board-cell pick targets."""

    def __init__(self, perspective_path, min_confidence=0.45,
                 max_offset_cells=0.25, foot_ratio=0.85, point_mode="foot"):
        self.perspective_path = Path(perspective_path)
        self.min_confidence = float(min_confidence)
        self.max_offset_cells = float(max_offset_cells)
        self.foot_ratio = float(foot_ratio)
        self.point_mode = str(point_mode)
        self._matrix = np.load(self.perspective_path).astype(np.float32)
        if self._matrix.shape != (3, 3):
            raise ValueError("perspective.npy must contain a 3x3 camera-to-grid matrix")
        if not 0.0 <= self.foot_ratio <= 1.0:
            raise ValueError("foot_ratio must be between 0 and 1")
        if self.point_mode not in {"center", "foot"}:
            raise ValueError("point_mode must be 'center' or 'foot'")
        print(f"[VISUAL PICK] Perspective loaded: {self.perspective_path}")

    def _box_to_grid(self, box):
        x1, y1, x2, y2 = map(float, box)
        center_x = (x1 + x2) / 2.0
        point_y = ((y1 + y2) / 2.0 if self.point_mode == "center"
                   else y1 + (y2 - y1) * self.foot_ratio)
        pixel = np.array([[[center_x, point_y]]], dtype=np.float32)
        col, row = cv2.perspectiveTransform(pixel, self._matrix)[0][0]
        return float(col), float(row)

    def estimate_pick_target(self, detections, expected_col, expected_row):
        """Return the nearest valid target for the expected cell, otherwise ``None``.

        Detection class IDs are deliberately ignored: game state determines which
        piece is expected at the source/destination cell.
        """
        candidates = []
        for _class_id, confidence, box in detections or []:
            confidence = float(confidence)
            if confidence < self.min_confidence:
                continue
            try:
                col, row = self._box_to_grid(box)
            except (ValueError, TypeError, cv2.error) as exc:
                print(f"[VISUAL PICK] Ignore invalid detection: {exc}")
                continue
            if not (0.0 <= col <= 8.0 and 0.0 <= row <= 9.0):
                continue
            offset = math.hypot(col - expected_col, row - expected_row)
            if offset <= self.max_offset_cells:
                candidates.append((offset, -confidence, col, row, confidence))

        if not candidates:
            print(f"[VISUAL PICK] Fallback ({expected_col},{expected_row}): no confident detection within "
                  f"{self.max_offset_cells:.2f} cell(s).")
            return None

        offset, _neg_confidence, col, row, confidence = min(candidates)
        target = GridTarget(col=col, row=row, confidence=confidence, offset_cells=offset)
        print(f"[VISUAL PICK] Target ({expected_col},{expected_row}) -> "
              f"({col:.3f},{row:.3f}), conf={confidence:.2f}, offset={offset:.3f} cells")
        return target

    def has_detection_in_cell(self, detections, expected_col, expected_row, cell_half_width=0.5):
        """Return occupancy for an entire calibrated cell, independent of pick offset.

        A piece shifted too far to safely pick can still obstruct a square.  This
        deliberately uses the square cell boundary instead of
        ``max_offset_cells``, which is reserved for safe gripper correction.
        """
        half_width = float(cell_half_width)
        if not 0.0 < half_width <= 0.5:
            raise ValueError("cell_half_width must be in (0, 0.5]")
        for _class_id, confidence, box in detections or []:
            if float(confidence) < self.min_confidence:
                continue
            try:
                col, row = self._box_to_grid(box)
            except (ValueError, TypeError, cv2.error):
                continue
            if abs(col - expected_col) <= half_width and abs(row - expected_row) <= half_width:
                return True
        return False

    @staticmethod
    def aggregate_targets(targets, min_samples=2, max_spread_cells=None):
        """Use a median only when enough measured targets form a tight cluster."""
        targets = [target for target in targets if target is not None]
        if len(targets) < int(min_samples):
            return None
        median_col = float(np.median([target.col for target in targets]))
        median_row = float(np.median([target.row for target in targets]))
        if max_spread_cells is not None:
            max_spread_cells = float(max_spread_cells)
            if any(math.hypot(target.col - median_col, target.row - median_row) > max_spread_cells
                   for target in targets):
                print(f"[VISUAL PICK] Fallback: samples exceed {max_spread_cells:.2f} cell jitter.")
                return None
        return GridTarget(
            col=median_col,
            row=median_row,
            confidence=float(np.median([target.confidence for target in targets])),
            offset_cells=float(np.median([target.offset_cells for target in targets])),
        )
