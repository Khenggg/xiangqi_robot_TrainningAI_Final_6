"""
Unit tests for MotionCoordinator.
Verifies pick, place, and capture choreographies against RobotBackend interface.
"""

import unittest
from unittest.mock import MagicMock

from src.domain.board_pose import BoardPlacementState
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.hardware.backends.base import RobotBackend
from src.motion.coordinator import MotionCoordinator
from src.vision.visual_pick_estimator import GridTarget


class MotionCoordinatorTests(unittest.TestCase):

    def setUp(self):
        self.mock_backend = MagicMock(spec=RobotBackend)
        self.mock_backend.set_gripper.return_value = True
        self.mock_backend.move_cartesian.return_value = True

        self.provider = FixedBoardPoseProvider.from_forward_shift(forward_shift_mm=0.0)
        self.coordinator = MotionCoordinator(
            backend=self.mock_backend,
            board_pose_provider=self.provider,
            safe_clearance_z_mm=40.0,
            pick_depth_offset_mm=0.0,
        )

    def test_pick_choreography_sequence(self):
        ok = self.coordinator.pick(row=0, col=0)
        self.assertTrue(ok)

        # Verify gripper opened first, then closed
        self.assertEqual(self.mock_backend.set_gripper.call_count, 2)
        self.assertEqual(self.mock_backend.set_gripper.call_args_list[0][1]["closed"], False)
        self.assertEqual(self.mock_backend.set_gripper.call_args_list[1][1]["closed"], True)

        # Verify Cartesian moves: approach -> descend -> lift
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 3)

    def test_pick_with_visual_target(self):
        vt = GridTarget(col=0.15, row=0.25, confidence=0.8, offset_cells=0.29)
        ok = self.coordinator.pick(row=0, col=0, visual_target=vt)
        self.assertTrue(ok)
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 3)

    def test_place_choreography_sequence(self):
        ok = self.coordinator.place(row=1, col=2)
        self.assertTrue(ok)

        # Verify gripper opened on placement
        self.assertEqual(self.mock_backend.set_gripper.call_count, 1)
        self.assertEqual(self.mock_backend.set_gripper.call_args_list[0][1]["closed"], False)

        # Verify Cartesian moves: approach -> descend -> lift
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 3)

    def test_execute_move_without_capture(self):
        ok = self.coordinator.execute_move(src_row=0, src_col=0, dst_row=1, dst_col=0, is_capture=False)
        self.assertTrue(ok)
        # pick (3 moves) + place (3 moves) = 6 moves
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 6)

    def test_execute_move_with_capture(self):
        ok = self.coordinator.execute_move(
            src_row=0, src_col=0, dst_row=1, dst_col=0,
            is_capture=True, capture_bin_cell=(-1.0, -1.0)
        )
        self.assertTrue(ok)
        # capture: pick dst (3) + place bin (3) = 6
        # move: pick src (3) + place dst (3) = 6
        # Total = 12 Cartesian moves
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 12)

    def test_execute_move_with_custom_capture_pose(self):
        custom_pose = [-226.0, 225.0, 290.0, 180.0, 0.0, 90.0]
        ok = self.coordinator.execute_move(
            src_row=0, src_col=0, dst_row=1, dst_col=0,
            is_capture=True, capture_bin_pose_mm=custom_pose
        )
        self.assertTrue(ok)
        self.assertEqual(self.mock_backend.move_cartesian.call_count, 12)

    def test_fails_fast_on_backend_cartesian_error(self):
        self.mock_backend.move_cartesian.return_value = False
        ok = self.coordinator.pick(row=0, col=0)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
