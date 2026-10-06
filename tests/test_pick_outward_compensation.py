"""Physical board-axis pick compensation; all motion calls are mocked."""
import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import numpy as np
import config
from src.hardware.robot_VIP import FR5Robot
from src.vision.visual_pick_estimator import GridTarget


class PickOutwardTests(unittest.TestCase):
    def setUp(self):
        enabled = patch.object(config, 'PICK_OUTWARD_COMPENSATION_ENABLED', True)
        enabled.start()
        self.addCleanup(enabled.stop)

    def robot(self, angle=0):
        robot = FR5Robot()
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        # Robot X increases with board row, Y with board column.
        xy = np.array([[0, 0], [0, 366], [410, 366], [410, 0]]) @ rotation.T
        robot.teaching_points = {name: {"pose": [*point, 220, 0, 0, 0]}
                                for name, point in zip(("R1", "R2", "R3", "R4"), xy)}
        robot.move_safe_pose = Mock()
        robot.movel_pose = Mock()
        robot.gripper_ctrl = Mock()
        return robot, rotation

    def test_center_corners_knights_and_four_cell_cap(self):
        robot, _ = self.robot()
        for cell, expected in [((4, 4.5), [0, 0]), ((0, 0), [-2.8, -2.4]),
                               ((8, 9), [2.8, 2.4]), ((8, 0), [-2.8, 2.4]),
                               ((0, 9), [2.8, -2.4]), ((7, 0), [-2.8, 1.8]),
                               ((4, 4), [0, 0]), ((4, 5), [0, 0]),
                               ((6, 6), [.7, 1.2]), ((2, 3), [-.7, -1.2])]:
            with self.subTest(cell=cell):
                np.testing.assert_allclose(robot._pick_outward_offset(*cell), expected, atol=1e-10)

    def test_all_rows_drop_half_cell_symmetrically(self):
        robot, _ = self.robot()
        for row, expected in enumerate([-2.8, -2.1, -1.4, -.7, 0, 0, .7, 1.4, 2.1, 2.8]):
            with self.subTest(row=row):
                np.testing.assert_allclose(robot._pick_outward_offset(4, row), [expected, 0], atol=1e-10)

    def test_axes_rotate_with_real_board_and_invalid_axes_reject(self):
        robot, rotation = self.robot(.8)
        np.testing.assert_allclose(robot._pick_outward_offset(8, 9), rotation @ [2.8, 2.4])
        for name in robot.teaching_points:
            robot.teaching_points[name]['pose'][:2] = [0, 0]
        with self.assertRaises(ValueError):
            robot._pick_outward_offset(8, 9)

    def test_visual_and_logical_pick_share_xy_through_all_lifts_and_preserve_placement(self):
        for target in (None, GridTarget(7.91, 8.93, .9, .11)):
            with self.subTest(target=target), contextlib.redirect_stdout(io.StringIO()):
                robot, _ = self.robot()
                baseline = (robot.board_to_pose(8, 9, config.PICK_Z, rotation=config.PICK_TOOL_ROTATION)
                            if target is None else robot.board_to_pose_bilinear(
                                target.col, target.row, config.PICK_Z, rotation=config.PICK_TOOL_ROTATION))
                robot.pick_at(8, 9, target)
                robot.move_to_extra_safe(8, 9, target)
                commands = [robot.move_safe_pose.call_args_list[0].args[0],
                            *[call.args[0] for call in robot.movel_pose.call_args_list],
                            robot.move_safe_pose.call_args_list[1].args[0]]
                for pose in commands:
                    np.testing.assert_allclose(pose[:2], np.array(baseline[:2]) + [2.8, 2.4])
                    self.assertEqual(pose[3:], config.PICK_TOOL_ROTATION)
                self.assertEqual([pose[2] for pose in commands],
                                 [config.SAFE_Z, config.PICK_Z, config.SAFE_Z, config.SAFE_Z])
                place = robot.board_to_pose(3, 7, config.PLACE_Z, rotation=config.PLACE_TOOL_ROTATION)
                robot.place_at(3, 7)
                self.assertEqual(robot.movel_pose.call_args_list[2].args[0], place)

    def test_disabled_compensation_leaves_pose_unchanged(self):
        robot, _ = self.robot()
        with patch.object(config, 'PICK_OUTWARD_COMPENSATION_ENABLED', False):
            self.assertEqual(robot._apply_pick_outward_offset([1, 2, 3, 4, 5, 6], 8, 9), [1, 2, 3, 4, 5, 6])
