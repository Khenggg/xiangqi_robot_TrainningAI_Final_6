"""Approximate top-rim coordinates using only the board homography.

No lens or piece-height compensation: XY distances are board-plane estimates.
"""
import hashlib

import numpy as np

from src.vision.pick_geometry import finite_array


class HomographyPickGeometry:
    def __init__(self, matrix, camera_index, frame_size, board_mm):
        self.matrix = finite_array(matrix, (3, 3)).copy()
        if np.linalg.matrix_rank(self.matrix) != 3:
            raise ValueError("Singular board homography")
        self.inverse = np.linalg.inv(self.matrix)
        self.camera_index = int(camera_index)
        self.frame_size = tuple(frame_size)
        self.board_mm = finite_array(board_mm, (2,))
        if (np.any(self.board_mm <= 0) or len(self.frame_size) != 2
                or any(not isinstance(n, (int, np.integer)) or n <= 0 for n in self.frame_size)):
            raise ValueError("Invalid board dimensions/frame")
        self.pitch = self.board_mm / [8, 9]
        self.profile_id = "BOARD-H-APPROX-" + hashlib.sha256(self.matrix.tobytes()).hexdigest()[:8]

    def grid_to_xy(self, cells):
        return finite_array(cells) * self.pitch

    def xy_to_grid(self, points):
        return finite_array(points) / self.pitch

    @staticmethod
    def _transform(points, matrix):
        points = finite_array(points).reshape(-1, 2)
        homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
        if np.any(np.abs(homogeneous[:, 2]) < 1e-9):
            raise ValueError("Point lies on homography horizon")
        return finite_array(homogeneous[:, :2] / homogeneous[:, 2:3])

    def pixels_to_top_xy(self, pixels):
        return self.grid_to_xy(self._transform(pixels, self.matrix))

    def project(self, xy, top=True):
        return self._transform(self.xy_to_grid(xy), self.inverse)

    def validate_context(self, camera_index, frame_size, board_mm, piece_height_mm,
                         perspective_matrix, tolerance_px=4.0):
        current = finite_array(perspective_matrix, (3, 3))
        # Freeze the calibration for this runtime; a new calibration needs re-init.
        if (int(camera_index) != self.camera_index or tuple(frame_size) != self.frame_size
                or not np.allclose(board_mm, self.board_mm, rtol=0, atol=1e-6)
                or not np.allclose(current, self.matrix, rtol=0, atol=1e-9)):
            raise ValueError("Camera/frame/board/homography changed; recalibrate and restart")
