"""
Unit tests for BoardPoseProvider and FixedBoardPoseProvider.
"""

import unittest
from src.domain.board_pose import BoardPlacementState
from src.domain.board_pose_provider import BoardPoseProvider, FixedBoardPoseProvider


class BoardPoseProviderTests(unittest.TestCase):

    def test_fixed_board_pose_provider_default(self):
        provider = FixedBoardPoseProvider()
        self.assertIsInstance(provider, BoardPoseProvider)
        state = provider.get_board_placement_state()
        self.assertIsInstance(state, BoardPlacementState)
        self.assertEqual(state.board_yaw_deg, 90.0)

    def test_from_teaching_points_calculation(self):
        # 4 corners in mm
        # R1: col 0, row 0
        # R2: col 8, row 0
        # R3: col 8, row 9
        # R4: col 0, row 9
        # Under 90 deg: col moves along -X_robot, row moves along -Y_robot
        teaching_points = {
            "R1": {"pose": [-200.0, 180.0, 50.0, 180.0, 0.0, 0.0]},
            "R2": {"pose": [-520.0, 180.0, 50.0, 180.0, 0.0, 0.0]},
            "R3": {"pose": [-520.0, -180.0, 50.0, 180.0, 0.0, 0.0]},
            "R4": {"pose": [-200.0, -180.0, 50.0, 180.0, 0.0, 0.0]},
        }
        provider = FixedBoardPoseProvider.from_teaching_points(teaching_points, board_yaw_deg=90.0)
        state = provider.get_board_placement_state()

        # Mean center X = (-200 - 520 - 520 - 200) / 4 = -360.0 mm -> -0.360 m
        # Mean center Y = (180 + 180 - 180 - 180) / 4 = 0.0 mm -> 0.0 m
        # Surface Z = 50.0 mm -> 0.050 m
        self.assertAlmostEqual(state.board_center_robot_m[0], -0.360, places=4)
        self.assertAlmostEqual(state.board_center_robot_m[1], 0.0, places=4)
        self.assertAlmostEqual(state.board_surface_z_robot_m, 0.050, places=4)

    def test_missing_teaching_point_raises(self):
        teaching_points = {
            "R1": {"pose": [-200.0, 180.0, 50.0, 180.0, 0.0, 0.0]},
            "R2": {"pose": [-520.0, 180.0, 50.0, 180.0, 0.0, 0.0]},
            # R3 missing
            "R4": {"pose": [-200.0, -180.0, 50.0, 180.0, 0.0, 0.0]},
        }
        with self.assertRaises(ValueError):
            FixedBoardPoseProvider.from_teaching_points(teaching_points)


if __name__ == "__main__":
    unittest.main()
