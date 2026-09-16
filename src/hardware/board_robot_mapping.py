"""Compose moving board geometry with a FIXED camera-to-robot planar reference."""
import json
from pathlib import Path

import cv2
import numpy as np

from src.vision.qr_calibration import CORNER_GRID, transform


class BoardRobotMapping:
    def __init__(self, reference, calibration_provider):
        self.reference = reference
        self.provider = calibration_provider
        pixels = np.float32(reference["camera_points_px"])
        robot = np.float32(reference["robot_points_xy_mm"])
        if pixels.shape != (4, 2) or robot.shape != (4, 2):
            raise ValueError("Four paired camera pixels and robot XY coordinates are required")
        for points in (pixels, robot):
            if (not np.isfinite(points).all() or not cv2.isContourConvex(points)
                    or abs(cv2.contourArea(points)) < 1):
                raise ValueError("Invalid reference quadrilateral")
        self.camera_to_robot = cv2.getPerspectiveTransform(pixels, robot)
        self.bounds = np.asarray(reference["xy_limits_mm"], dtype=float)
        if (self.bounds.shape != (2, 2) or not np.isfinite(self.bounds).all()
                or (self.bounds[:, 0] >= self.bounds[:, 1]).any()):
            raise ValueError("xy_limits_mm must be [[xmin,xmax],[ymin,ymax]]")
        self.max_shift_mm = float(reference.get("motion_tolerance_mm", 1.0))
        if not 0 < self.max_shift_mm <= 5:
            raise ValueError("motion_tolerance_mm must be in (0,5]")
        self.frozen = None

    @classmethod
    def load(cls, path, provider):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")), provider)

    def begin(self):
        current = self.provider()
        if list(current.frame_size) != self.reference["frame_size"]:
            raise RuntimeError("Camera resolution differs from robot reference; recalibrate")
        self.frozen = current
        try:
            for point in CORNER_GRID:
                self.xy(*point)
        except Exception:
            self.frozen = None
            raise

    def end(self):
        self.frozen = None

    def check(self):
        if self.frozen is None:
            raise RuntimeError("No QR robot motion transaction is active")
        current = self.provider()
        if current.frame_size != self.frozen.frame_size:
            raise RuntimeError("Camera resolution changed during motion")
        before = transform(self.frozen.corners_px, self.camera_to_robot)
        after = transform(current.corners_px, self.camera_to_robot)
        if np.max(np.linalg.norm(after - before, axis=1)) > self.max_shift_mm:
            raise RuntimeError("Board moved during motion; stop and reconcile physical board")

    def xy(self, col, row):
        self.check()
        if not 0 <= col <= 8 or not 0 <= row <= 9:
            raise ValueError("Robot target is outside the Xiangqi grid")
        matrix = self.camera_to_robot @ self.frozen.grid_to_camera
        xy = transform([[col, row]], matrix)[0]
        if (xy < self.bounds[:, 0]).any() or (xy > self.bounds[:, 1]).any():
            raise RuntimeError("QR target is outside configured robot XY workspace")
        return xy.tolist()
