import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.vision.visual_pick_estimator import VisualPickEstimator
from src.vision.visual_pick_estimator import GridTarget
from src.hardware.robot_VIP import FR5Robot


class VisualPickEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        perspective = Path(self.temp_dir.name) / "perspective.npy"
        # Identity makes pixel coordinates equal grid coordinates for deterministic tests.
        np.save(perspective, np.eye(3, dtype=np.float32))
        self.estimator = VisualPickEstimator(perspective, min_confidence=0.45,
                                             max_offset_cells=0.25, foot_ratio=0.85)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_selects_nearest_detection_using_foot_point(self):
        # Box foot point: x=3.10, y=1 + ((2.17647 - 1) * .85) = 2.00.
        detections = [
            (0, 0.80, (3.00, 1.00, 3.20, 2.17647)),
            (1, 0.99, (3.60, 1.00, 3.80, 2.17647)),
        ]
        target = self.estimator.estimate_pick_target(detections, expected_col=3.0, expected_row=2.0)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 3.10, places=5)
        self.assertAlmostEqual(target.row, 2.0, places=5)

    def test_rejects_low_confidence_out_of_board_and_far_detections(self):
        detections = [
            (0, 0.44, (2.0, 2.0, 2.0, 2.0)),
            (0, 0.90, (9.0, 2.0, 9.0, 2.0)),
            (0, 0.90, (2.6, 2.0, 2.6, 2.0)),
        ]
        self.assertIsNone(self.estimator.estimate_pick_target(detections, 2.0, 2.0))

    def test_returns_target_when_foot_is_within_safe_offset(self):
        detections = [(5, 0.70, (2.00, 1.00, 2.20, 2.00))]
        target = self.estimator.estimate_pick_target(detections, expected_col=2.1, expected_row=1.85)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 2.1, places=5)
        self.assertAlmostEqual(target.row, 1.85, places=5)
        self.assertAlmostEqual(target.offset_cells, 0.0, places=5)


class PhysicalPoseTests(unittest.TestCase):
    def test_visual_grid_float_generates_physical_xy_and_pick_rotation(self):
        robot = FR5Robot()
        robot.teaching_points = {
            "R1": {"pose": [0, 0, 0, 0, 0, 0]},
            "R2": {"pose": [0, 80, 0, 0, 0, 0]},
            "R3": {"pose": [90, 80, 0, 0, 0, 0]},
            "R4": {"pose": [90, 0, 0, 0, 0, 0]},
        }
        target = GridTarget(col=4.0, row=4.5, confidence=0.9, offset_cells=0.1)
        # robot_VIP has Vietnamese/emoji diagnostic logging; it is irrelevant to
        # this coordinate unit test and may not be encodable by a Windows shell.
        with contextlib.redirect_stdout(io.StringIO()):
            pose = robot.board_to_pose_bilinear(target.col, target.row, 250.0,
                                                rotation=[10.0, 20.0, 30.0])
        # X includes the project-wide OFFSET_X (currently +5mm); Y has no offset.
        self.assertEqual(pose, [50.0, 40.0, 250.0, 10.0, 20.0, 30.0])


if __name__ == "__main__":
    unittest.main()
