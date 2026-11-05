"""Offline incident probes. Every hardware operation is an explicit mock.

PASS establishes the current dispatch boundary, not a safe physical trajectory.
"""
from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot, RobotCommandError


def test_approach_passes_auto_joint_config_without_start_pose_query():
    fake_sdk = SimpleNamespace(MoveCart=Mock(return_value=0))
    adapter = SimpleNamespace(
        _require_actuation=Mock(), _validate_pose=FR5Robot._validate_pose,
        default_vel=50.0, _set_planned_command=Mock(), dry=False,
        robot=fake_sdk, tool_num=0, user_num=0,
    )
    target = [-120.0, 500.0, 220.0, 180.0, 0.0, -73.2]
    assert FR5Robot.move_safe_pose(adapter, target) == 0
    fake_sdk.MoveCart.assert_called_once_with(
        desc_pos=target, tool=0, user=0, vel=50.0,
        acc=0.0, ovl=100.0, blendT=-1.0, config=-1,
    )
    # The fake has no joint-query, IK, planning or collision API. Dispatch still occurs.


def test_activation_accepts_idle_and_board_match_without_start_pose_contract():
    state = SimpleNamespace(
        ai_thinking=False, pending_move=None, physical_sync_fault=False,
        pending_test_motion=None, recovery_required=False, mode_change_pending=False,
        move_sync_error=None, board=[["."] * 9 for _ in range(10)], sync_current_board=Mock(),
    )
    robot = SimpleNamespace(connected=True, teaching_points_error=None,
                            activate_physical_control=Mock(return_value=True))
    hardware = SimpleNamespace(
        _closing=False, session_control=None, stop_coordinator=None,
        profile=SimpleNamespace(physical_robot_enabled=True), dry_run=False,
        config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL"), robot=robot,
        _piece_move_lock=Lock(), physical_telemetry_ready=Mock(return_value=True),
        verify_physical_board=Mock(return_value=True),
    )
    assert HardwareManager.activate_physical_game(hardware, state, commissioned=True)
    hardware.physical_telemetry_ready.assert_called_once_with(require_idle=True)
    robot.activate_physical_control.assert_called_once_with(commissioned=True)
    # No measured start joints, route or validated first-approach state is supplied.


def test_error14_at_approach_prevents_descent_and_grip():
    adapter = SimpleNamespace(
        board_to_pose_bilinear=Mock(side_effect=[
            [-120.0, 500.0, 220.0, 180.0, 0.0, -73.2],
            [-120.0, 500.0, 178.0, 180.0, 0.0, -73.2],
            [-120.0, 500.0, 178.0, 180.0, 0.0, -73.2],
        ]),
        gripper_command_known=True, gripper_closed_estimate=False,
        move_safe_pose=Mock(side_effect=RobotCommandError("Robot MoveCart error code: 14", 14)),
        movel_pose=Mock(), gripper_ctrl=Mock(),
    )
    adapter._run_stage = lambda stage, operation, *args, **kwargs: operation(*args, **kwargs)
    target = SimpleNamespace(col=6.95, row=1.94, offset_cells=0.079, confidence=0.85)
    with pytest.raises(RobotCommandError, match="14"):
        FR5Robot.pick_at(adapter, 7, 2, visual_target=target)
    adapter.movel_pose.assert_not_called()
    adapter.gripper_ctrl.assert_not_called()
