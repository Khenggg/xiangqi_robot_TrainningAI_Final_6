"""Offline diagnostic probes, not hardware replay or regression-fix claims.

The fake controller acknowledges commands while reporting an unchanged, distant
pose. Passing demonstrates the current missing feedback boundary.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest

from src.hardware import robot_VIP
from src.hardware.hardware_manager import HardwareManager
from src.motion.stages import MotionStage


@pytest.fixture
def robot(monkeypatch):
    monkeypatch.setattr(robot_VIP, "robot_sdk_core", SimpleNamespace(
        RPC=Mock(side_effect=AssertionError("Real SDK construction forbidden"))))
    monkeypatch.setattr(robot_VIP.time, "sleep", lambda *_: None)
    profile = Path(__file__).resolve().parents[2] / "calibration/physical_teaching_points_user0.json"
    adapter = robot_VIP.FR5Robot(dry_run=False, teaching_points_path=profile)
    adapter._load_fixed_teaching_points()  # File only; no connection.
    measured = [348.6, 148.4, 395.6, -59.3, -42.7, 110.0]
    adapter.robot = SimpleNamespace(
        MoveCart=Mock(return_value=0), MoveL=Mock(),
        SetToolDO=Mock(return_value=0),
        GetActualTCPPose=Mock(return_value=(0, measured)),
        GetActualJointPosDegree=Mock(), GetRobotMotionDone=Mock(return_value=(0, 0)),
    )
    adapter.connected = adapter.physical_motion_authorized = True
    adapter.gripper_command_known = True
    backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(),
        motion_state="MOVING"))
    hardware = SimpleNamespace(backend=backend)
    adapter.telemetry_readiness = lambda: HardwareManager.physical_telemetry_ready(hardware)
    return adapter


def test_moving_snapshot_passes_normal_stage_readiness():
    hardware = SimpleNamespace(backend=SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state="MOVING")))
    assert HardwareManager.physical_telemetry_ready(hardware)
    assert not HardwareManager.physical_telemetry_ready(hardware, require_idle=True)


def test_acknowledged_but_unreached_approach_still_reaches_grip(robot):
    # No fake motion updates measured TCP and motion-done remains false.
    robot.pick_at(7, 2)
    assert robot.gripper_closed_estimate is True
    robot.robot.SetToolDO.assert_any_call(id=0, status=1, block=0)
    robot.robot.GetActualTCPPose.assert_not_called()
    robot.robot.GetActualJointPosDegree.assert_not_called()
    robot.robot.GetRobotMotionDone.assert_not_called()
    # The nominal vertical stage also uses PTP instead of MoveL.
    robot.robot.MoveL.assert_not_called()
    assert len(robot.robot.MoveCart.call_args_list) == 3
    assert robot._last_completed_stage == MotionStage.LIFT


def test_land_failure_retains_approach_completed_without_measured_arrival(robot):
    robot.robot.MoveCart.side_effect = [0, 112]
    with pytest.raises(robot_VIP.RobotCommandError) as caught:
        robot.pick_at(7, 2)
    assert caught.value.backend_code == 112
    assert robot._last_completed_stage == MotionStage.APPROACH
    assert robot._active_stage == MotionStage.LAND
    robot.robot.GetActualTCPPose.assert_not_called()
    robot.robot.SetToolDO.assert_not_called()
