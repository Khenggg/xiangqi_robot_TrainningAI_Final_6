"""Four identified QR centres define a moving, planar Xiangqi board.

Offsets are measured in board coordinates (millimetres), never image pixels.
No stored/partially observed homography is treated as a fresh measurement.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import time

import cv2
import numpy as np


CORNER_GRID = np.float32([[0, 0], [8, 0], [8, 9], [0, 9]])
CORNER_NAMES = ("TL", "TR", "BR", "BL")


def transform(points, matrix):
    points = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    result = cv2.perspectiveTransform(points, np.asarray(matrix, dtype=np.float64))[:, 0]
    if not np.isfinite(result).all():
        raise ValueError("Non-finite projected coordinates")
    return result


def qr_center(quad):
    """Intersect diagonals; averaging image vertices is wrong under perspective."""
    q = np.c_[np.asarray(quad, dtype=float).reshape(4, 2), np.ones(4)]
    p = np.cross(np.cross(q[0], q[2]), np.cross(q[1], q[3]))
    if abs(p[2]) < 1e-8:
        raise ValueError("Degenerate QR quadrilateral")
    return p[:2] / p[2]


@dataclass(frozen=True)
class BoardGeometry:
    cell_mm: tuple
    marker_ids: tuple
    marker_grid: np.ndarray

    @classmethod
    def from_dict(cls, data):
        cell = np.asarray(data["cell_mm"], dtype=float)
        if cell.shape != (2,) or not np.isfinite(cell).all() or (cell <= 0).any():
            raise ValueError("cell_mm needs measured positive [horizontal, vertical] values")
        ids, positions = [], []
        for name, corner in zip(CORNER_NAMES, CORNER_GRID):
            marker = data["markers"][name]
            offset = np.asarray(marker["qr_to_corner_mm"], dtype=float)
            if offset.shape != (2,) or not np.isfinite(offset).all():
                raise ValueError(f"Invalid measured offset for {name}")
            ids.append(marker["id"])
            # corner = QR centre + signed offset, expressed in board axes.
            positions.append(corner - offset / cell)
        if len(set(ids)) != 4 or not all(isinstance(x, str) and x for x in ids):
            raise ValueError("Exactly four distinct nonempty QR payloads are required")
        positions = np.float32(positions)
        if not cv2.isContourConvex(positions) or cv2.contourArea(positions, oriented=True) <= 0:
            raise ValueError("Marker layout must form TL/TR/BR/BL convex perimeter")
        return cls(tuple(cell), tuple(ids), positions)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Calibration:
    camera_to_grid: np.ndarray
    grid_to_camera: np.ndarray
    corners_px: np.ndarray
    timestamp: float
    generation: int
    frame_size: tuple


class QRCalibrator:
    def __init__(self, geometry, stable_frames=3, tolerance_px=2.0, max_age=2.0):
        if stable_frames < 1 or tolerance_px <= 0 or max_age <= 0:
            raise ValueError("Invalid calibration stability settings")
        self.geometry = geometry
        self.detector = cv2.QRCodeDetector()
        self.stable_frames = stable_frames
        self.tolerance_px = tolerance_px
        self.max_age = max_age
        self.current = None
        self.reason = "Waiting for all four QR codes"
        self._anchor = None
        self._count = 0
        self._generation = 0
        self._last_corners = None

    def invalidate(self, reason):
        self.current = None
        self._anchor = None
        self._count = 0
        self.reason = reason
        return None

    def update(self, frame, timestamp=None):
        try:
            ok, decoded, points, _ = self.detector.detectAndDecodeMulti(frame)
            centres = {}
            if ok and points is not None:
                for name, quad in zip(decoded, points):
                    if name in self.geometry.marker_ids:
                        if name in centres:
                            return self.invalidate(f"Duplicate QR: {name}")
                        centres[name] = qr_center(quad)
            return self.update_centres(centres, frame.shape[:2], timestamp)
        except (cv2.error, ValueError) as exc:
            return self.invalidate(f"QR decode failed: {exc}")

    def update_centres(self, centres, frame_shape, timestamp=None):
        """Pure geometry entry point, also used by synthetic verification."""
        stamp = time.monotonic() if timestamp is None else timestamp
        if set(centres) != set(self.geometry.marker_ids):
            return self.invalidate("All four identified QR codes must be visible")
        src = np.float32([centres[name] for name in self.geometry.marker_ids])
        h, w = frame_shape[:2]
        if (not np.isfinite(src).all() or not cv2.isContourConvex(src)
                or cv2.contourArea(src, oriented=True) < 400
                or (src < 0).any() or (src[:, 0] >= w).any() or (src[:, 1] >= h).any()):
            return self.invalidate("Invalid QR geometry / mirrored camera / small board")
        matrix = cv2.getPerspectiveTransform(src, self.geometry.marker_grid)
        try:
            inverse = np.linalg.inv(matrix)
            corners = transform(CORNER_GRID, inverse)
        except (ValueError, np.linalg.LinAlgError):
            return self.invalidate("Singular calibration")
        if (not cv2.isContourConvex(corners.astype(np.float32))
                or (corners < 0).any() or (corners[:, 0] >= w).any()
                or (corners[:, 1] >= h).any()):
            return self.invalidate("Actual board corners fall outside camera view")
        if self._anchor is None or np.max(np.linalg.norm(corners - self._anchor, axis=1)) > self.tolerance_px:
            self._anchor = corners.copy()
            self._count = 1
            self.current = None
        else:
            self._count += 1
        if self._count < self.stable_frames:
            self.reason = f"Board settling ({self._count}/{self.stable_frames})"
            return None
        if (self._last_corners is None
                or np.max(np.linalg.norm(corners - self._last_corners, axis=1)) > self.tolerance_px):
            self._generation += 1
            self._last_corners = corners.copy()
        self.current = Calibration(matrix, inverse, corners, stamp, self._generation, (w, h))
        self.reason = "QR calibration ready"
        return self.current

    def require_current(self, now=None):
        now = time.monotonic() if now is None else now
        if self.current is None or not 0 <= now - self.current.timestamp <= self.max_age:
            raise RuntimeError(self.reason if self.current is None else "QR measurement is stale")
        return self.current


class YoloPoseCalibrator:
    """Conservative four-corner fallback for frames where QR decoding fails."""

    def __init__(self, model_path, min_keypoint_confidence=.65, stable_frames=3,
                 tolerance_px=2.0, max_age=2.0):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))
        self.min_keypoint_confidence = float(min_keypoint_confidence)
        self.stable_frames, self.tolerance_px, self.max_age = stable_frames, tolerance_px, max_age
        self.current = None
        self.reason = "Waiting for board-pose corners"
        self._anchor = self._last_corners = None
        self._count = self._generation = 0

    def invalidate(self, reason):
        self.current = self._anchor = None
        self._count = 0
        self.reason = reason
        return None

    def update(self, frame, timestamp=None):
        if frame is None:
            return self.invalidate("No camera frame for board-pose")
        stamp = time.monotonic() if timestamp is None else timestamp
        try:
            result = self.model.predict(frame, conf=.4, verbose=False)[0]
            keypoints = result.keypoints
            if keypoints is None or len(keypoints) != 1:
                return self.invalidate("Board-pose must find exactly one board")
            corners = keypoints.xy[0].cpu().numpy().astype(np.float32)
            confidence = keypoints.conf[0].cpu().numpy() if keypoints.conf is not None else np.ones(4)
            h, w = frame.shape[:2]
            if (corners.shape != (4, 2) or np.any(confidence < self.min_keypoint_confidence)
                    or not np.isfinite(corners).all() or not cv2.isContourConvex(corners)
                    or (corners < 0).any() or (corners[:, 0] >= w).any() or (corners[:, 1] >= h).any()):
                return self.invalidate("Invalid/low-confidence board-pose geometry")
            # Model training order: TL, TR, BR, BL (the same order as CORNER_GRID).
            matrix = cv2.getPerspectiveTransform(corners, CORNER_GRID)
            inverse = np.linalg.inv(matrix)
        except (cv2.error, ValueError, np.linalg.LinAlgError, IndexError) as exc:
            return self.invalidate(f"Board-pose failed: {exc}")
        if self._anchor is None or np.max(np.linalg.norm(corners - self._anchor, axis=1)) > self.tolerance_px:
            self._anchor, self._count, self.current = corners.copy(), 1, None
        else:
            self._count += 1
        if self._count < self.stable_frames:
            self.reason = f"Board-pose settling ({self._count}/{self.stable_frames})"
            return None
        if self._last_corners is None or np.max(np.linalg.norm(corners - self._last_corners, axis=1)) > self.tolerance_px:
            self._generation += 1
            self._last_corners = corners.copy()
        self.current = Calibration(matrix, inverse, corners, stamp, self._generation, (w, h))
        self.reason = "Board-pose fallback ready"
        return self.current


class HandGuard:
    """Reject calibration frames containing a hand, which can hide QR corners."""

    def __init__(self, model_path, confidence=.50):
        from ultralytics import YOLO
        self.model, self.confidence = YOLO(str(model_path)), float(confidence)

    def hand_present(self, frame):
        result = self.model.predict(frame, conf=self.confidence, verbose=False)[0]
        return result.boxes is not None and len(result.boxes) > 0


class HybridQRCalibrator:
    """QR-first calibration; pose fallback is explicitly non-authoritative."""

    def __init__(self, qr_calibrator, pose_calibrator=None, hand_guard=None):
        self.qr, self.pose, self.hand_guard = qr_calibrator, pose_calibrator, hand_guard
        self.current, self.source = None, None
        self.reason, self.max_age = qr_calibrator.reason, qr_calibrator.max_age

    def invalidate(self, reason):
        self.current = self.source = None
        self.qr.invalidate(reason)
        if self.pose:
            self.pose.invalidate(reason)
        self.reason = reason
        return None

    def update(self, frame, timestamp=None):
        try:
            if self.hand_guard and self.hand_guard.hand_present(frame):
                return self.invalidate("Hand detected: calibration paused")
        except Exception as exc:
            return self.invalidate(f"Hand guard failed: {exc}")
        calibration = self.qr.update(frame, timestamp)
        if calibration is not None:
            self.current, self.source, self.reason = calibration, "qr", self.qr.reason
            return calibration
        if self.pose:
            calibration = self.pose.update(frame, timestamp)
            if calibration is not None:
                self.current, self.source, self.reason = calibration, "pose", self.pose.reason
                return calibration
        self.current, self.source = None, None
        self.reason = self.pose.reason if self.pose else self.qr.reason
        return None

    def require_current(self, now=None):
        now = time.monotonic() if now is None else now
        if self.current is None or not 0 <= now - self.current.timestamp <= self.max_age:
            raise RuntimeError(self.reason if self.current is None else "Camera measurement is stale")
        return self.current

    def require_qr_current(self, now=None):
        calibration = self.require_current(now)
        if self.source != "qr":
            raise RuntimeError("QR calibration is required before physical robot motion")
        return calibration


def warp_for_recognizer(frame, calibration):
    """Match upstream 450x500 warp -> centre crop 400x450 -> resize 280x315.

The four outer intersections land at (25,25),(375,25),(375,425),(25,425)
inside the 400x450 crop. Keeping this margin is essential to classification.
"""
    grid_to_crop = np.array([[350 / 8, 0, 25], [0, 400 / 9, 25], [0, 0, 1]], dtype=float)
    return cv2.warpPerspective(frame, grid_to_crop @ calibration.camera_to_grid, (400, 450))
