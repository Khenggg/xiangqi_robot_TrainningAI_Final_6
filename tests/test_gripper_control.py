"""Unit tests for the two-output, pulse-only gripper interlock."""
import os
import sys
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from src.hardware.robot_VIP import FR5Robot, GripperCommandError


class FakeRobot:
    def __init__(self, failing_call=None, failing_indexes=()):
        self.calls = []
        self.failing_call = failing_call
        self.failing_indexes = set(failing_indexes)

    def SetToolDO(self, id, status, smooth=0, block=0):
        call = (id, status, block)
        self.calls.append(call)
        return 77 if call == self.failing_call or len(self.calls) in self.failing_indexes else 0


class FakeConnection:
    SDK_state = True

    def RobotEnable(self, _value):
        return 0

    def Mode(self, _value):
        return 0


class GripperControlTests(unittest.TestCase):
    def make_gripper(self, dry=False):
        robot = FR5Robot()
        robot.dry = dry
        robot.robot = FakeRobot()
        return robot

    @patch("src.hardware.robot_VIP.time.sleep")
    def test_open_pulses_configured_output_and_leaves_both_outputs_low(self, sleep):
        robot = self.make_gripper()
        robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN)

        self.assertEqual(robot.robot.calls, [
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
            (config.GRIPPER_OPEN_DO_ID, 1, 0),
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
        ])
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [config.GRIPPER_DIRECTION_DEADTIME_SEC, config.GRIPPER_OPEN_PULSE_SEC,
             config.GRIPPER_OPEN_SETTLE_SEC],
        )

    @patch("src.hardware.robot_VIP.time.sleep")
    def test_close_pulses_configured_output_and_leaves_both_outputs_low(self, sleep):
        robot = self.make_gripper()
        robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)

        self.assertEqual(robot.robot.calls, [
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
            (config.GRIPPER_CLOSE_DO_ID, 1, 0),
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
        ])
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [config.GRIPPER_DIRECTION_DEADTIME_SEC, config.GRIPPER_CLOSE_PULSE_SEC,
             config.GRIPPER_CLOSE_SETTLE_SEC],
        )

    @patch("src.hardware.robot_VIP.time.sleep")
    def test_enable_failure_never_attempts_other_direction(self, _sleep):
        robot = self.make_gripper()
        robot.robot.failing_call = (config.GRIPPER_CLOSE_DO_ID, 1, 0)

        with self.assertRaises(GripperCommandError):
            robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)

        self.assertNotIn((config.GRIPPER_OPEN_DO_ID, 1, 0), robot.robot.calls)
        self.assertEqual(robot.robot.calls[-2:], [
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
        ])

    def test_same_output_ids_are_rejected_before_io(self):
        robot = self.make_gripper()
        robot.gripper_close_do_id = robot.gripper_open_do_id

        with self.assertRaises(GripperCommandError):
            robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN)
        self.assertEqual(robot.robot.calls, [])

    def test_invalid_timing_is_rejected_before_io(self):
        robot = self.make_gripper()
        with patch.object(config, "GRIPPER_OPEN_PULSE_SEC", "fast"):
            with self.assertRaises(GripperCommandError):
                robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN)
        with patch.object(config, "GRIPPER_OPEN_PULSE_SEC", float("nan")):
            with self.assertRaises(GripperCommandError):
                robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN)
        self.assertEqual(robot.robot.calls, [])

    @patch("src.hardware.robot_VIP.time.sleep")
    def test_final_output_reset_failure_is_reported_after_both_low_attempts(self, _sleep):
        robot = self.make_gripper()
        # Calls 1-2 are initial all-low, 3 enables Open, 4 fails to reset it.
        robot.robot.failing_indexes = {4}

        with self.assertRaises(GripperCommandError):
            robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN)

        self.assertEqual(robot.robot.calls, [
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
            (config.GRIPPER_OPEN_DO_ID, 1, 0),
            (config.GRIPPER_OPEN_DO_ID, 0, 0), (config.GRIPPER_CLOSE_DO_ID, 0, 0),
        ])

    @patch("src.hardware.robot_VIP.time.sleep")
    def test_connect_opens_gripper_before_loading_teaching_points(self, _sleep):
        robot = FR5Robot()
        events = []
        fake_sdk = type("FakeSdk", (), {"RPC": lambda _ip: FakeConnection()})
        with patch("src.hardware.robot_VIP.robot_sdk_core", fake_sdk), \
                patch("builtins.print"), \
                patch.object(robot, "_validate_gripper_config", side_effect=lambda: events.append("validate")), \
                patch.object(robot, "_set_gripper_safe_idle", side_effect=lambda: events.append("idle")), \
                patch.object(robot, "gripper_ctrl", side_effect=lambda action: events.append(action)), \
                patch.object(robot, "_load_teaching_points", side_effect=lambda: events.append("teaching")):
            robot.connect()

        self.assertEqual(events, ["validate", "idle", config.GRIPPER_ACTION_OPEN, "teaching"])


if __name__ == "__main__":
    unittest.main()
