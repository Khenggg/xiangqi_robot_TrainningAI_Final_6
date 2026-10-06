"""Metric camera geometry. No robot, empirical offsets, or old measurements."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import cv2
import numpy as np


BOARD_CORNERS = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=float)
VALIDATION_CELLS = ((0, 0), (8, 0), (8, 9), (0, 9), (4, 4))


def finite_array(value, shape=None):
    result = np.asarray(value, dtype=np.float64)
    if (shape is not None and result.shape != shape) or not np.isfinite(result).all():
        raise ValueError("Invalid/nonfinite geometry array")
    return result


class PickGeometry:
    """Board XY in mm, Z toward camera; piece plane is 10 mm above board.

    Axis orientation is defined by ordered board clicks, NOT robot axes. The
    sign of camera Z selects the normal pointing from the board toward camera.
    """

    def __init__(self, data, require_validation=True):
        self.data = dict(data)
        if data.get("schema") != 1:
            raise ValueError("Unsupported pick geometry schema")
        self.k = finite_array(data["camera_matrix"], (3, 3))
        self.dist = finite_array(data["distortion"]).reshape(-1)
        if (len(self.dist) not in (4, 5, 8, 12, 14) or self.k[0, 0] <= 0
                or self.k[1, 1] <= 0 or not np.allclose(self.k[2], [0, 0, 1])
                or self.k[0, 1] != 0 or self.k[1, 0] != 0
                or abs(np.linalg.det(self.k)) < 1e-9):
            raise ValueError("Invalid camera intrinsics")
        self.rvec = finite_array(data["rvec"]).reshape(3, 1)
        self.tvec = finite_array(data["tvec"]).reshape(3, 1)
        self.rotation = cv2.Rodrigues(self.rvec)[0]
        self.camera_center = (-self.rotation.T @ self.tvec).ravel()
        self.width, self.height = map(float, data["board_mm"])
        self.piece_height = float(data["piece_height_mm"])
        self.frame_size = tuple(data["frame_size"])
        self.camera_index = int(data["camera_index"])
        if (not np.isfinite([self.width, self.height, self.piece_height]).all()
                or min(self.width, self.height, self.piece_height) <= 0
                or len(self.frame_size) != 2
                or any(not isinstance(n, int) or n <= 0 for n in self.frame_size)
                or abs(self.camera_center[2]) <= self.piece_height):
            raise ValueError("Invalid board dimensions/frame/pose")
        self.top_z = np.sign(self.camera_center[2]) * self.piece_height
        world = np.column_stack((self.grid_to_xy(BOARD_CORNERS), np.zeros(4)))
        if np.any((self.rotation @ world.T + self.tvec)[2] <= 0):
            raise ValueError("Board is behind camera")
        self.profile_id = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
        if require_validation:
            self.validate_commissioning()

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def grid_to_xy(self, cells):
        return finite_array(cells) * [self.width / 8, self.height / 9]

    def xy_to_grid(self, points):
        return finite_array(points) / [self.width / 8, self.height / 9]

    def pixels_to_top_xy(self, pixels):
        pixels = finite_array(pixels).reshape(-1, 1, 2)
        rays = cv2.undistortPoints(pixels, self.k, self.dist).reshape(-1, 2)
        directions = np.column_stack((rays, np.ones(len(rays)))) @ self.rotation
        if not np.isfinite(directions).all() or np.any(np.abs(directions[:, 2]) < 1e-7):
            raise ValueError("Nonfinite or near-parallel ray")
        distance = (self.top_z - self.camera_center[2]) / directions[:, 2]
        if np.any(distance <= 0) or not np.isfinite(distance).all():
            raise ValueError("Piece plane lies behind camera ray")
        world = self.camera_center + distance[:, None] * directions
        return finite_array(world[:, :2])

    def project(self, xy, top=True):
        xy = finite_array(xy).reshape(-1, 2)
        points = np.column_stack((xy, np.full(len(xy), self.top_z if top else 0)))
        return cv2.projectPoints(points, self.rvec, self.tvec, self.k, self.dist)[0].reshape(-1, 2)

    def validate_context(self, camera_index, frame_size, board_mm, piece_height_mm,
                         perspective_matrix, tolerance_px=4.0):
        if not np.isfinite(tolerance_px) or tolerance_px <= 0:
            raise ValueError("Invalid corner tolerance")
        if (int(camera_index) != self.camera_index or tuple(frame_size) != self.frame_size
                or not np.allclose(board_mm, [self.width, self.height], atol=1e-6)
                or not np.isclose(piece_height_mm, self.piece_height, atol=1e-6)):
            raise ValueError("Camera/frame/board/height differs from calibrated profile")
        matrix = finite_array(perspective_matrix, (3, 3))
        actual = cv2.perspectiveTransform(BOARD_CORNERS.reshape(1, -1, 2), np.linalg.inv(matrix))[0]
        expected = self.project(self.grid_to_xy(BOARD_CORNERS), top=False)
        error = np.linalg.norm(actual - expected, axis=1)
        if not np.isfinite(error).all() or max(error) > tolerance_px:
            raise ValueError(f"Board/camera moved or corner calibration differs: {max(error):.2f}px")

    def validate_commissioning(self):
        quality = self.data.get("quality", {})
        values = [quality.get("intrinsic_rms_px", float("inf")),
                  quality.get("pose_max_error_px", float("inf")),
                  quality.get("max_error_mm", float("nan"))]
        if (not np.isfinite(values).all() or not 0 < values[2] <= 5
                or not 0 <= values[0] <= 1.0 or not 0 <= values[1] <= 2.0
                or quality.get("intrinsic_views", 0) < 12
                or quality.get("diverse_views") is not True
                or quality.get("operator_approved") is not True):
            raise ValueError("Profile is not commissioned with sufficient calibration quality")
        pattern = self.data.get("pattern", {})
        shape = pattern.get("inner_corners", [])
        square = pattern.get("square_mm", float("nan"))
        if (len(shape) != 2 or any(not isinstance(n, int) or n < 3 for n in shape)
                or not np.isfinite(square) or square <= 0):
            raise ValueError("Missing printed target dimensions/measured square size")
        pose = self.data.get("pose_observations", {})
        cells = finite_array(pose.get("cells", [])).reshape(-1, 2)
        pixels = finite_array(pose.get("pixels", [])).reshape(-1, 2)
        if (len(cells) < 9 or len(cells) != len(pixels)
                or len(np.unique(cells, axis=0)) != len(cells)
                or len(np.unique(pixels, axis=0)) != len(pixels)
                or np.any(np.ptp(cells, axis=0) < [8, 9])
                or np.any(cells < 0) or np.any(cells > [8, 9])
                or np.any(pixels < 0) or np.any(pixels >= self.frame_size)):
            raise ValueError("Missing/distributed pose observations")
        if np.max(np.linalg.norm(self.project(self.grid_to_xy(cells), top=False) - pixels, axis=1)) > 2.0:
            raise ValueError("Stored board pose fails reprojection check")
        observations = self.data.get("height_validation", [])
        found = set()
        for entry in observations:
            cell = tuple(entry["cell"])
            if cell not in VALIDATION_CELLS or cell in found:
                raise ValueError("Invalid/duplicate independent validation cell")
            found.add(cell)
            pixel = finite_array(entry["pixel"], (2,))
            if np.any(pixel < 0) or np.any(pixel >= self.frame_size):
                raise ValueError("Independent validation pixel outside frame")
            measured = self.pixels_to_top_xy([pixel])[0]
            error = np.linalg.norm(measured - self.grid_to_xy(cell))
            if error > values[2]:
                raise ValueError(f"Independent height validation exceeds tolerance: {error:.2f}mm")
        if found != set(VALIDATION_CELLS):
            raise ValueError("Need independent 10mm validation at four corners and center")

    def save_approved(self, path):
        self.validate_commissioning()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            backup = path.with_name(path.name + ".backup-" + stamp)
            backup.write_bytes(path.read_bytes())
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def calibrate_intrinsics(image_points, pattern, square_mm, frame_size):
    """Reject duplicate/location-poor/tilt-poor captures before fitting K."""
    cols, rows = pattern
    if min(cols, rows) < 3 or not np.isfinite(square_mm) or square_mm <= 0:
        raise ValueError("Measure printed checkerboard square in mm")
    if len(frame_size) != 2 or not np.isfinite(frame_size).all() or min(frame_size) <= 0:
        raise ValueError("Invalid calibration frame size")
    if len(image_points) < 12:
        raise ValueError("Need at least 12 diverse checkerboard views")
    views = [finite_array(p).reshape(-1, 2) for p in image_points]
    if any(len(p) != cols * rows for p in views):
        raise ValueError("Wrong checkerboard corner count")
    scale = np.array(frame_size)
    centers = np.array([p.mean(axis=0) / scale for p in views])
    if np.any(np.ptp(centers, axis=0) < .25):
        raise ValueError("Move pattern across image center AND edges in both axes")
    for i, points in enumerate(views):
        if any(np.sqrt(np.mean((points - other) ** 2)) < 5 for other in views[:i]):
            raise ValueError("Duplicate checkerboard captures")
    objects = np.zeros((cols * rows, 3), np.float32)
    objects[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_mm
    rms, k, dist, rvecs, _ = cv2.calibrateCamera(
        [objects.copy() for _ in views], [p.astype(np.float32) for p in views], tuple(frame_size), None, None)
    normals = np.array([cv2.Rodrigues(r)[0][:, 2] for r in rvecs])
    if (not np.isfinite(rms) or rms > 1.0
            or np.max(np.linalg.norm(normals - normals.mean(axis=0), axis=1)) < .15):
        raise ValueError("Intrinsics failed: RMS >1px or insufficient pattern tilts")
    return rms, k, dist


def estimate_board_pose(cells, pixels, k, dist, board_mm):
    cells = finite_array(cells).reshape(-1, 2)
    pixels = finite_array(pixels).reshape(-1, 2)
    if len(cells) < 9 or len(cells) != len(pixels) or len(np.unique(pixels, axis=0)) < 9:
        raise ValueError("Need nine independent distributed board intersections")
    if (np.linalg.matrix_rank(cells - cells.mean(axis=0)) < 2
            or len(np.unique(cells, axis=0)) != len(cells)
            or np.any(cells < 0) or np.any(cells > [8, 9])
            or np.any(np.ptp(cells, axis=0) < [8, 9])):
        raise ValueError("Degenerate board clicks")
    points = np.column_stack((cells * np.asarray(board_mm) / [8, 9], np.zeros(len(cells))))
    ok, rvec, tvec = cv2.solvePnP(points, pixels, k, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok or np.any((cv2.Rodrigues(rvec)[0] @ points.T + tvec)[2] <= 0):
        raise ValueError("PnP failed or board behind camera")
    projected = cv2.projectPoints(points, rvec, tvec, k, dist)[0].reshape(-1, 2)
    maximum = float(np.max(np.linalg.norm(projected - pixels, axis=1)))
    if not np.isfinite(maximum) or maximum > 2.0:
        raise ValueError(f"Board clicks inconsistent with camera: {maximum:.2f}px (>2px)")
    return rvec, tvec, maximum
