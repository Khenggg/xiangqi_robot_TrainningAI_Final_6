import time
import unittest

import cv2
import numpy as np

from src.vision.qr_calibration import Calibration, CORNER_GRID, transform
from src.vision.visual_correction import VisualCorrector


GRID_TO_CAMERA = np.array([[88, 7, 130], [4, 92, 110], [.002, -.001, 1]], dtype=float)


def calibration():
    camera_to_grid = np.linalg.inv(GRID_TO_CAMERA)
    corners = transform(CORNER_GRID, GRID_TO_CAMERA)
    return Calibration(camera_to_grid, GRID_TO_CAMERA, corners, time.monotonic(), 4, (1000, 1100))


def scene(circles=()):
    image = np.full((1100, 1000, 3), 225, np.uint8)
    cal = calibration()
    # Board lines exercise the detector against a realistic local background.
    for c in range(9):
        points = transform([[c, 0], [c, 9]], cal.grid_to_camera).astype(int)
        cv2.line(image, tuple(points[0]), tuple(points[1]), (100, 100, 100), 2)
    for r in range(10):
        points = transform([[0, r], [8, r]], cal.grid_to_camera).astype(int)
        cv2.line(image, tuple(points[0]), tuple(points[1]), (100, 100, 100), 2)
    for col, row, radius in circles:
        centre = transform([[col, row]], cal.grid_to_camera)[0].astype(int)
        # Apparent circular pieces in camera image remain circular enough after
        # QR rectification for this controlled geometry test.
        cv2.circle(image, tuple(centre), radius, (35, 35, 35), -1)
        cv2.circle(image, tuple(centre), radius, (250, 250, 250), 3)
    return image, cal


class VisualCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.corrector = VisualCorrector(pixels_per_cell=120, min_radius_cells=.22,
                                         max_radius_cells=.52, max_offset_cells=.34,
                                         min_confidence=.55, hough_param2=12)

    def test_finds_actual_offset_centre_in_rectified_board(self):
        image, cal = scene([(4.20, 3.85, 35)])
        target = self.corrector.locate(image, cal, 4, 4)
        self.assertIsNotNone(target)
        # The source test image intentionally has projective camera geometry;
        # sub-pixel Hough centre error below .08 cell is acceptable here.
        self.assertAlmostEqual(target.col, 4.20, delta=.08)
        self.assertAlmostEqual(target.row, 3.85, delta=.08)
        self.assertLess(target.offset_cells, .30)
        self.assertEqual(target.generation, 4)

    def test_rejects_empty_wrong_cell_and_distant_piece(self):
        blank, cal = scene()
        self.assertIsNone(self.corrector.locate(blank, cal, 4, 4))
        distant, _ = scene([(4.60, 4.0, 35)])
        self.assertIsNone(self.corrector.locate(distant, cal, 4, 4))

    def test_prefers_the_expected_piece_over_nearby_board_detail(self):
        image, cal = scene([(4.12, 4.0, 35)])
        target = self.corrector.locate(image, cal, 4, 4)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 4.12, delta=.08)

    def test_corner_piece_has_margin_and_is_corrected(self):
        image, cal = scene([(.16, .12, 35)])
        target = self.corrector.locate(image, cal, 0, 0)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, .16, delta=.06)
        self.assertAlmostEqual(target.row, .12, delta=.06)

    def test_generation_and_offsets_are_bound_to_measurement(self):
        image, cal = scene([(4.1, 4.0, 35)])
        target = self.corrector.verify(image, cal, 4, 4)
        self.assertEqual(target.timestamp, cal.timestamp)
        self.assertGreaterEqual(target.confidence, self.corrector.min_confidence)


if __name__ == "__main__":
    unittest.main()
