"""Offline pick/place tests: failed arm moves must stop subsequent actions."""
import contextlib
import io
import unittest
from unittest.mock import Mock

import numpy as np
import config
from src.hardware.robot_VIP import FR5Robot, RobotMotionError
from src.hardware.robot_sdk_core import RobotCommunicationError


class MotionErrorAbortTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def robot(self):
        robot = FR5Robot()
        robot.dry = False
        robot.connected = True
        robot.robot = Mock()
        robot.board_to_pose = lambda col, row, z, **kwargs: [col, row, z, 0, 0, 0]
        robot._pick_outward_offset = Mock(return_value=np.zeros(2))
        robot.gripper_ctrl = Mock()
        return robot

    def test_pick_error_112_stops_before_descent_or_grasp(self):
        for responses, expected_moves in (([112], 1), ([0, 112], 2)):
            with self.subTest(responses=responses):
                robot = self.robot()
                robot.robot.MoveCart.side_effect = responses
                with self.assertRaisesRegex(RobotMotionError, "112"):
                    robot.pick_at(3, 4)
                self.assertEqual(robot.robot.MoveCart.call_count, expected_moves)
                self.assertNotIn(config.GRIPPER_ACTION_CLOSE,
                                 [c.args[0] for c in robot.gripper_ctrl.call_args_list])

    def test_each_motion_wrapper_rejects_every_nonzero_status(self):
        for error in (112, -4, 1):
            for method, args in (("move_safe_pose", ([1]*6,)),
                                 ("movel_pose", ([1]*6,)),
                                 ("movej_joint", ([1]*6, [1]*6))):
                with self.subTest(error=error, method=method):
                    robot = self.robot()
                    robot.robot.MoveCart.return_value = error
                    robot.robot.MoveJ.return_value = error
                    with self.assertRaises(RobotMotionError):
                        getattr(robot, method)(*args)

    def test_home_motion_failure_has_no_alternate_move(self):
        robot = self.robot()
        robot.robot.GetRobotTeachingPoint.return_value = (0, [1]*12)
        robot.robot.MoveJ.return_value = 112
        with self.assertRaises(RobotMotionError):
            robot.go_to_home_chess()
        robot.robot.MoveJ.assert_called_once()
        robot.robot.MoveCart.assert_not_called()

    def test_ambiguous_home_response_has_no_alternate_move(self):
        robot = self.robot()
        robot.robot.GetRobotTeachingPoint.return_value = (0, [1]*12)
        robot.robot.MoveJ.side_effect = RobotCommunicationError("completion unknown")
        with self.assertRaises(RobotCommunicationError):
            robot.go_to_home_chess()
        robot.robot.MoveJ.assert_called_once()
        robot.robot.MoveCart.assert_not_called()

    def test_idle_motion_failure_has_no_alternate_move(self):
        robot = self.robot()
        robot.robot.MoveCart.return_value = 112
        with self.assertRaises(RobotMotionError):
            robot.go_to_idle_home()
        robot.robot.MoveCart.assert_called_once()

    def test_connect_failure_is_not_reported_as_success(self):
        robot = self.robot()
        robot.connected = False
        robot.connect = Mock(side_effect=RuntimeError("offline"))
        with self.assertRaisesRegex(RuntimeError, "move not executed"):
            robot.move_piece(3, 4, 3, 5, False)
        robot.robot.MoveCart.assert_not_called()
        robot.gripper_ctrl.assert_not_called()

    def test_unknown_motion_completion_latches_all_later_motion(self):
        robot = self.robot()
        robot.robot.MoveCart.side_effect = RobotCommunicationError("response lost")
        with self.assertRaises(RobotCommunicationError):
            robot.move_safe_pose([1]*6)
        self.assertTrue(robot.communication_fault)
        robot.robot.MoveCart.side_effect = None
        robot.robot.MoveCart.return_value = 0
        with self.assertRaises(RobotCommunicationError):
            robot.movel_pose([1]*6)
        with self.assertRaises(RobotCommunicationError):
            robot.movej_joint([1]*6, [1]*6)
        robot.robot.MoveCart.assert_called_once()
        robot.robot.MoveJ.assert_not_called()

    def test_resume_requires_both_read_probe_and_fresh_idle_state(self):
        robot = self.robot()
        robot._latch_communication_fault()
        fault_at = robot._communication_fault_at
        robot.robot.GetControllerIP.return_value = (0, "offline")
        robot.robot.has_fresh_idle_state.return_value = False
        self.assertFalse(robot.can_resume_after_communication_fault())
        self.assertTrue(robot.communication_fault)
        robot.robot.has_fresh_idle_state.return_value = True
        self.assertTrue(robot.can_resume_after_communication_fault())
        health_args = robot.robot.has_fresh_idle_state.call_args.kwargs
        self.assertGreaterEqual(health_args['after'], fault_at)
        self.assertEqual(health_args['timeout'], .5)
        self.assertEqual(health_args['max_age'], .5)
        self.assertFalse(robot.communication_fault)
        robot.robot.MoveCart.return_value = 0
        robot.movel_pose([1]*6)
        robot.robot.MoveCart.assert_called_once()

    def test_failed_resume_probe_keeps_latch(self):
        robot = self.robot()
        robot._latch_communication_fault()
        robot.robot.GetControllerIP.side_effect = RobotCommunicationError("still offline")
        self.assertFalse(robot.can_resume_after_communication_fault())
        self.assertTrue(robot.communication_fault)
        robot.robot.has_fresh_idle_state.assert_not_called()

    def test_gripper_communication_fault_blocks_energizing_but_allows_low(self):
        robot = self.robot()
        robot.robot.SetToolDO.side_effect = RobotCommunicationError("lost output response")
        with self.assertRaises(RobotCommunicationError):
            robot._set_tool_do(0, config.GRIPPER_ACTIVE_STATUS)
        self.assertTrue(robot.communication_fault)
        robot.robot.SetToolDO.side_effect = None
        robot.robot.SetToolDO.return_value = 0
        with self.assertRaises(RobotCommunicationError):
            robot._set_tool_do(1, config.GRIPPER_ACTIVE_STATUS)
        robot._set_tool_do(0, config.GRIPPER_IDLE_STATUS)
        self.assertEqual(robot.robot.SetToolDO.call_count, 2)


if __name__ == "__main__":
    unittest.main()
