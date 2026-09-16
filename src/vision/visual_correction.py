"""Locate the actual centre of a known Xiangqi piece after QR board alignment.

The 90-cell classifier tells us *which* intersections are occupied.  This
module deliberately does not guess piece identity: it only refines the physical
centre of a piece expected at one known intersection.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class VisualTarget:
    """A conservative, camera-measured continuous grid point for one piece."""

    col: float
    row: float
    confidence: float
    offset_cells: float
    radius_cells: float
    generation: int
    timestamp: float


class VisualCorrector:
    """Find circular Xiangqi pieces in a locally rectified board image.

    QR calibration removes board perspective first. Hough-circle candidates are
    then accepted only in a small neighbourhood of the expected occupied
    intersection. This prevents a nearby piece or an empty-board ornament from
    becoming a pick target.
    """

    def __init__(self, pixels_per_cell=120, min_radius_cells=.20,
                 max_radius_cells=.58, max_offset_cells=.34,
                 min_confidence=.60, hough_param2=10):
        values = (pixels_per_cell, min_radius_cells, max_radius_cells,
                  max_offset_cells, min_confidence, hough_param2)
        if (pixels_per_cell < 60 or not 0 < min_radius_cells < max_radius_cells < .75
                or not 0 < max_offset_cells < .5 or not 0 < min_confidence <= 1
                or hough_param2 < 4 or not all(np.isfinite(values))):
            raise ValueError("Invalid visual-correction settings")
        self.scale = int(pixels_per_cell)
        self.min_radius = float(min_radius_cells)
        self.max_radius = float(max_radius_cells)
        self.max_offset = float(max_offset_cells)
        self.min_confidence = float(min_confidence)
        self.hough_param2 = float(hough_param2)

    def _canvas(self, frame, calibration):
        # One-cell margin makes corner pieces fully visible and keeps their
        # centres away from a warp border.
        matrix = np.array([[self.scale, 0, self.scale],
                           [0, self.scale, self.scale],
                           [0, 0, 1]], dtype=np.float64) @ calibration.camera_to_grid
        return cv2.warpPerspective(frame, matrix, (10 * self.scale, 11 * self.scale),
                                   flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_REPLICATE)

    def locate(self, frame, calibration, expected_col, expected_row):
        """Return a target or ``None``. Never return a distant/ambiguous circle."""
        if not (0 <= expected_col <= 8 and 0 <= expected_row <= 9):
            raise ValueError("Expected visual correction cell is outside the board")
        canvas = self._canvas(frame, calibration)
        grey = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        grey = cv2.medianBlur(grey, 5)
        cx, cy = (expected_col + 1) * self.scale, (expected_row + 1) * self.scale
        # Include a whole piece at the permitted centre offset, but no adjacent
        # intersection. A local ROI makes Hough much less sensitive to board art.
        half = int(math.ceil((self.max_offset + self.max_radius + .08) * self.scale))
        x0, y0 = max(0, int(cx - half)), max(0, int(cy - half))
        x1, y1 = min(canvas.shape[1], int(cx + half)), min(canvas.shape[0], int(cy + half))
        roi = grey[y0:y1, x0:x1]
        circles = cv2.HoughCircles(
            roi, cv2.HOUGH_GRADIENT, dp=1.15, minDist=max(1, int(self.scale * .48)),
            param1=100, param2=self.hough_param2,
            minRadius=max(1, int(self.min_radius * self.scale)),
            maxRadius=max(2, int(self.max_radius * self.scale)),
        )
        if circles is None:
            return None
        candidates = []
        preferred_radius = (self.min_radius + self.max_radius) / 2
        radius_span = (self.max_radius - self.min_radius) / 2
        for x, y, radius_px in circles[0]:
            col = (float(x) + x0) / self.scale - 1
            row = (float(y) + y0) / self.scale - 1
            radius = float(radius_px) / self.scale
            offset = math.hypot(col - expected_col, row - expected_row)
            if offset > self.max_offset:
                continue
            proximity = max(0.0, 1.0 - offset / self.max_offset)
            radius_score = max(0.0, 1.0 - abs(radius - preferred_radius) / radius_span)
            # Hough itself validates circular edge evidence. This score is used
            # only to choose between those local candidates and to gate motion.
            # A circle that passes Hough already has edge evidence. Keep a
            # baseline for it, then reward proximity/radius; otherwise a valid
            # piece near the safe edge of the correction window is rejected.
            score = .45 + .35 * proximity + .20 * radius_score
            candidates.append((score, col, row, radius, offset))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        best = candidates[0]
        # Two materially different centres with nearly identical support are
        # unsafe: ask for an unobstructed frame instead of choosing arbitrarily.
        if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < .05:
            return None
        score, col, row, radius, offset = best
        if score < self.min_confidence:
            return None
        return VisualTarget(col, row, score, offset, radius,
                            calibration.generation, calibration.timestamp)

    def verify(self, frame, calibration, expected_col, expected_row):
        """Return a target only if a piece is physically close enough to its cell."""
        return self.locate(frame, calibration, expected_col, expected_row)
