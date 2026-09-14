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
                 max_offset_cells=0.25, foot_ratio=0.85):
        self.perspective_path = Path(perspective_path)
        self.min_confidence = float(min_confidence)
        self.max_offset_cells = float(max_offset_cells)
        self.foot_ratio = float(foot_ratio)
        self._matrix = np.load(self.perspective_path).astype(np.float32)
        if self._matrix.shape != (3, 3):
            raise ValueError("perspective.npy must contain a 3x3 camera-to-grid matrix")
        if not 0.0 <= self.foot_ratio <= 1.0:
            raise ValueError("foot_ratio must be between 0 and 1")
        print(f"[VISUAL PICK] Perspective loaded: {self.perspective_path}")

    def _box_to_grid(self, box):
        x1, y1, x2, y2 = map(float, box)
        pixel = np.array([[[ (x1 + x2) / 2.0,
                             y1 + (y2 - y1) * self.foot_ratio ]]], dtype=np.float32)
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
