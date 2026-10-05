import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from src.vision.auto_calibrate import AutoCalibrator, stable_corner_consensus, run_calibration_flow


CORNERS = np.array([[100, 100], [600, 100], [600, 600], [100, 600]], dtype=np.float32)


class CalibrationSafetyTests(unittest.TestCase):
    def test_stable_cluster_rejects_one_wrong_corner_outlier(self):
        samples = [CORNERS + (i % 3 - 1) for i in range(10)]
        outlier = CORNERS.copy()
        outlier[2] += 30
        samples += [outlier, outlier]
        np.testing.assert_allclose(stable_corner_consensus(samples), CORNERS, atol=1)

    def test_two_competing_corner_locations_are_rejected(self):
        wrong = CORNERS.copy()
        wrong[2] += 25
        self.assertIsNone(stable_corner_consensus([CORNERS] * 6 + [wrong] * 6))

    def test_insufficient_samples_and_nonfinite_points_are_rejected(self):
        self.assertIsNone(stable_corner_consensus([CORNERS] * 5))
        invalid = CORNERS.copy()
        invalid[0, 0] = np.nan
        self.assertFalse(AutoCalibrator().sanity_check_geometry(invalid, 720, 720)[0])

    def test_custom_minimum_score_is_used(self):
        class Recognizer:
            def detect_board_corners(self, frame):
                return CORNERS[[0, 1, 3, 2]], np.ones(4) * 0.15
        corners, _ = AutoCalibrator(Recognizer(), min_kpt_conf=0.2).predict_corners(np.zeros((720, 720, 3), np.uint8))
        self.assertIsNone(corners)

    def run_flow(self, path, key):
        class Capture:
            def read(self):
                return True, np.zeros((720, 720, 3), np.uint8)
        with patch('src.vision.auto_calibrate.config.DRY_RUN', False), \
             patch('src.vision.auto_calibrate.time.sleep'), \
             patch.object(AutoCalibrator, 'predict_corners', return_value=(CORNERS, 0.24)), \
             patch('src.vision.auto_calibrate.cv2.namedWindow'), \
             patch('src.vision.auto_calibrate.cv2.imshow'), \
             patch('src.vision.auto_calibrate.cv2.destroyWindow'), \
             patch('src.vision.auto_calibrate.cv2.waitKey', return_value=ord(key)), \
             patch('src.vision.auto_calibrate.calibrate_perspective_camera') as manual:
            if key == 'm':
                manual.return_value = np.eye(3)
            result = run_calibration_flow(Capture(), path, cchess_recognizer=object())
            return result, manual.call_count

    def test_cancel_preserves_existing_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'perspective.npy'
            np.save(path, np.eye(3))
            before = path.read_bytes()
            with self.assertRaises(RuntimeError):
                self.run_flow(path, 'q')
            self.assertEqual(before, path.read_bytes())

    def test_accept_saves_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'perspective.npy'
            matrix, manual_calls = self.run_flow(path, 's')
            np.testing.assert_allclose(np.load(path), matrix)
            self.assertEqual(manual_calls, 0)

    def test_manual_selection_does_not_save_auto_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'perspective.npy'
            _, manual_calls = self.run_flow(path, 'm')
            self.assertEqual(manual_calls, 1)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
