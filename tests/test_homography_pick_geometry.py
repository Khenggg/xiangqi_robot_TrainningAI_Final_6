"""Offline homography/top-rim checks; no camera or robot connection."""
import unittest

import cv2
import numpy as np

from src.vision.homography_pick_geometry import HomographyPickGeometry
from src.vision.top_face_pick_estimator import TopFacePickEstimator


class HomographyPickTests(unittest.TestCase):
    def setUp(self):
        # Red at image top, black at bottom: both axes reverse.
        self.matrix = np.array([[-.02, 0, 10], [0, -.02, 11], [0, 0, 1.]])
        self.geometry = HomographyPickGeometry(self.matrix, 1, (640, 640), (250, 281.25))

    def test_reversed_camera_maps_corners_and_round_trips(self):
        pixels = [[500, 550], [100, 550], [100, 100], [500, 100]]
        grid = [[0, 0], [8, 0], [8, 9], [0, 9]]
        xy = self.geometry.pixels_to_top_xy(pixels)
        np.testing.assert_allclose(self.geometry.xy_to_grid(xy), grid, atol=1e-10)
        np.testing.assert_allclose(self.geometry.project(xy), pixels, atol=1e-10)

    def test_changed_camera_frame_or_matrix_and_bad_geometry_rejected(self):
        self.geometry.validate_context(1, (640, 640), (250, 281.25), 10, self.matrix)
        for camera, frame, matrix in [(2, (640, 640), self.matrix),
                                      (1, (320, 320), self.matrix),
                                      (1, (640, 640), np.eye(3))]:
            with self.assertRaises(ValueError):
                self.geometry.validate_context(camera, frame, (250, 281.25), 10, matrix)
        for matrix in [np.zeros((3, 3)), np.full((3, 3), np.nan)]:
            with self.assertRaises(ValueError):
                HomographyPickGeometry(matrix, 1, (640, 640), (250, 281.25))

    def test_projective_skew_round_trip_and_horizon_rejection(self):
        pixels = np.array([[510, 540], [120, 520], [150, 110], [480, 90]], np.float32)
        grid = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], np.float32)
        matrix = cv2.getPerspectiveTransform(pixels, grid)
        geometry = HomographyPickGeometry(matrix, 1, (640, 640), (250, 281.25))
        np.testing.assert_allclose(geometry.xy_to_grid(geometry.pixels_to_top_xy(pixels)), grid, atol=1e-8)
        interior = geometry.grid_to_xy([[2.3, 5.4], [4, 4.5]])
        np.testing.assert_allclose(geometry.pixels_to_top_xy(geometry.project(interior)), interior, atol=1e-8)
        horizon_matrix = np.array([[1., 0, 0], [0, 1, 0], [1, 0, -10]])
        horizon = HomographyPickGeometry(horizon_matrix, 1, (640, 640), (250, 281.25))
        with self.assertRaises(ValueError):
            horizon.pixels_to_top_xy([[10, 20]])

    def test_synthetic_raster_rim_picks_center_not_character_and_no_rim_rejected(self):
        estimator = TopFacePickEstimator(self.geometry)
        frame = np.full((640, 640, 3), 80, np.uint8)
        center = (300, 300)
        cv2.circle(frame, center, 22, (255, 255, 255), -1)
        angles = np.linspace(0, 2*np.pi, 240, endpoint=False)
        rim = np.rint(np.array(center) + 15*np.column_stack((np.cos(angles), np.sin(angles)))).astype(np.int32)
        cv2.polylines(frame, [rim], True, (15, 15, 15), 1)
        cv2.drawMarker(frame, (304, 298), (0, 0, 0), cv2.MARKER_CROSS, 12, 2)
        grid = self.geometry.xy_to_grid(self.geometry.pixels_to_top_xy([center]))[0]
        detection = [(0, .95, [277, 277, 323, 323])]
        target = estimator.estimate_pick_target(frame, detection, *grid)
        self.assertIsNotNone(target, estimator.last_reason)
        self.assertLess(np.linalg.norm(np.array([target.col, target.row])-grid), .03)
        cv2.circle(frame, center, 22, (255, 255, 255), -1)
        cv2.drawMarker(frame, center, (0, 0, 0), cv2.MARKER_CROSS, 12, 2)
        self.assertIsNone(estimator.estimate_pick_target(frame, detection, *grid))


if __name__ == "__main__":
    unittest.main()
