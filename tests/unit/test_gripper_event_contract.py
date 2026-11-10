"""Contract tests for physical gripper actions shared by the twin and relay."""

import threading
from unittest.mock import Mock, patch

import config
from src.digital_twin.gripper_events import ATTACH, IDLE, RELEASE, gripper_intent
from src.hardware.robot_VIP import FR5Robot


def _robot_with_mock_listener():
    robot = object.__new__(FR5Robot)
    robot.dry = True
    robot._gripper_lock = threading.Lock()
    robot._motion_stop = threading.Event()
    robot.gripper_close_do_id = 1
    robot.gripper_open_do_id = 0
    robot.gripper_command_known = False
    robot.gripper_closed_estimate = False
    robot.motion_listener = Mock()
    robot._pulse_gripper_direction = Mock()
    return robot


def test_gripper_intent_distinguishes_safe_gap_from_release():
    assert gripper_intent(config.GRIPPER_ACTION_CLOSE, False) == ATTACH
    assert gripper_intent(config.GRIPPER_ACTION_OPEN_MAX, True) == RELEASE
    assert gripper_intent(config.GRIPPER_ACTION_RELEASE, True) == RELEASE
    assert gripper_intent(config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP, False) == IDLE
    # Legacy two-argument listeners keep the old boolean meaning.
    assert gripper_intent(None, True) == ATTACH
    assert gripper_intent(None, False) == RELEASE


def test_gripper_ctrl_passes_action_to_motion_listener():
    robot = _robot_with_mock_listener()
    with patch("src.hardware.robot_VIP.time.sleep"):
        robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    robot.motion_listener.assert_called_once_with(
        "gripper", True, config.GRIPPER_ACTION_CLOSE)


def test_gripper_ctrl_safe_gap_reports_non_release_action():
    robot = _robot_with_mock_listener()
    with patch("src.hardware.robot_VIP.time.sleep"):
        robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP)
    robot.motion_listener.assert_called_once_with(
        "gripper", False, config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP)


def test_short_release_opens_only_then_leaves_both_outputs_off():
    robot = FR5Robot()
    robot.dry = True
    robot._set_tool_do = Mock(return_value=0)
    with patch("src.hardware.robot_VIP.time.sleep"), \
            patch.object(robot._motion_stop, "wait") as wait:
        robot.gripper_ctrl(config.GRIPPER_ACTION_RELEASE)
    assert [c.args for c in robot._set_tool_do.call_args_list] == [
        (0, 0), (1, 0), (0, 1), (0, 0), (1, 0)]
    wait.assert_called_once_with(0.06)
    assert robot.gripper_command_known and not robot.gripper_closed_estimate


def test_board_place_opens_fully_lifts_then_returns_to_safe_gap():
    robot = FR5Robot()
    robot.dry = True
    robot.board_to_pose = Mock(side_effect=lambda col, row, z, **kw: [col, row, z, 180, 0, 0])
    calls = []
    robot.move_safe_pose = Mock(side_effect=lambda *a, **kw: calls.append("approach"))
    robot.movel_pose = Mock(side_effect=lambda pose: calls.append(pose[2]))
    robot.gripper_ctrl = Mock(side_effect=lambda action: calls.append(action))
    robot.place_at(4, 2)
    assert calls == ["approach", config.PLACE_Z, config.GRIPPER_ACTION_OPEN_MAX, config.SAFE_Z,
                     config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP]


def test_every_pick_reestablishes_safe_gap_before_approach():
    robot = FR5Robot()
    robot.dry = True
    robot.gripper_command_known = True
    robot.gripper_closed_estimate = False
    robot.board_to_pose = Mock(side_effect=lambda col, row, z, **kw: [col, row, z, 180, 0, 0])
    robot.board_to_pose_bilinear = robot.board_to_pose
    calls = []
    robot.move_safe_pose = Mock(side_effect=lambda *a, **kw: calls.append("approach"))
    robot.movel_pose = Mock(side_effect=lambda pose: calls.append(pose[2]))
    robot.gripper_ctrl = Mock(side_effect=lambda action: calls.append(action))
    robot.pick_at(4, 2)
    assert calls[:5] == [config.GRIPPER_ACTION_OPEN_MAX, config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP,
                         "approach", config.PICK_Z, config.GRIPPER_ACTION_CLOSE]


def test_failed_release_blocks_lift_and_attempts_both_outputs_off():
    import pytest
    from src.hardware.robot_VIP import GripperCommandError
    robot = FR5Robot()
    robot.dry = True
    robot.board_to_pose = Mock(side_effect=lambda col, row, z, **kw: [col, row, z, 180, 0, 0])
    robot.move_safe_pose = Mock()
    robot.movel_pose = Mock()
    robot._set_tool_do = Mock(side_effect=[0, 0, GripperCommandError("ON failed"), 0, 0])
    with patch("src.hardware.robot_VIP.time.sleep"), pytest.raises(GripperCommandError):
        robot.place_at(4, 2)
    assert robot.movel_pose.call_count == 1  # PLACE_LAND only, no lift after failure.
    assert [c.args for c in robot._set_tool_do.call_args_list][-2:] == [(0, 0), (1, 0)]
