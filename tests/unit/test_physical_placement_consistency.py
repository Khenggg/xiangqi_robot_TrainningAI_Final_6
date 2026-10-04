"""Physical board labels, rigid grid transform, and read-only startup gates."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.domain.board_pose import BoardPlacementState, compute_rotation_matrix
from src.domain.board_pose_provider import (
    BoardCalibrationTolerancePolicy,
    calibrate_board_from_teaching_points,
)
from src.hardware.hardware_manager import HardwareManager


LIVE_CONTACT_POINTS_MM = {
    "R1": [-209.0, 210.149, 10.494],
    "R2": [-206.0, 544.595, 10.5],
    "R3": [155.0, 542.0, 10.849],
    "R4": [160.0, 215.0, 10.501],
}


def test_live_reversed_corner_winding_rejected_even_with_loose_tolerances():
    loose = BoardCalibrationTolerancePolicy(
        max_dimension_error_hard_fail_mm=25.0,
        max_edge_length_diff_mm=20.0,
        max_corner_residual_hard_fail_mm=15.0,
        max_rms_residual_hard_fail_mm=10.0,
        max_diagonal_diff_mm=15.0,
    )
    result = calibrate_board_from_teaching_points(LIVE_CONTACT_POINTS_MM, tolerance_policy=loose)
    assert not result.success
    assert result.state is None
    assert "winding is reversed" in result.error_message


def test_swapping_live_corner_labels_does_not_hide_large_geometry_error():
    points = LIVE_CONTACT_POINTS_MM
    relabeled = {"R1": points["R2"], "R2": points["R1"],
                 "R3": points["R4"], "R4": points["R3"]}
    result = calibrate_board_from_teaching_points(relabeled)
    assert not result.success
    assert result.state is None
    assert "winding is reversed" not in result.error_message


def test_valid_yaw_180_teaching_points_share_one_grid_transform():
    center_m = np.array([-0.020, 0.3815, 0.0105])
    rotation = compute_rotation_matrix(180.0)
    corners = {
        "R1": (-0.160, -0.180),
        "R2": (0.160, -0.180),
        "R3": (0.160, 0.180),
        "R4": (-0.160, 0.180),
    }
    points = {name: ((center_m + rotation @ np.array([u, v, 0.0])) * 1000.0).tolist()
              for name, (u, v) in corners.items()}
    result = calibrate_board_from_teaching_points(points)
    assert result.success, result.error_message
    state = result.state
    assert state is not None
    assert state.board_yaw_deg == pytest.approx(180.0, abs=0.01)
    for row, col in ((0, 0), (0, 8), (9, 8), (9, 0), (4, 3)):
        u, v = state.cell_to_board_local(row, col)
        from_transform = (state.T_robot_from_board @ np.array([u, v, 0.0, 1.0]))[:3]
        np.testing.assert_allclose(state.cell_to_robot_xyz(row, col), from_transform, atol=1e-6)
    np.testing.assert_allclose(state.grid_origin_robot_m, state.cell_to_robot_xyz(0, 0), atol=1e-6)


def test_nominal_scene_does_not_inherit_stale_physical_teaching_points():
    state = BoardPlacementState.compute(
        forward_shift_mm=0.0,
        board_yaw_deg=180.0,
        nominal_board_center_robot_m=[-0.020, 0.3815, 0.00525],
        nominal_board_surface_z_m=0.0105,
    )
    assert state.teaching_points is None
    np.testing.assert_allclose(state.cell_to_robot_xyz(0, 0), [-0.200, 0.5415, 0.0105], atol=1e-6)



@pytest.mark.parametrize("authorized, opt_in, has_provider", [(False, True, True), (True, False, True), (True, True, False)])
def test_physical_startup_never_implicitly_activates(authorized, opt_in, has_provider):
    cfg = SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND="PHYSICAL", AUTO_ENABLE_PHYSICAL_ROBOT=opt_in)
    manager = HardwareManager(cfg, ".")
    manager.robot = SimpleNamespace(connected=True, physical_motion_authorized=False, connect=Mock(), activate_physical_control=Mock())
    manager.board_pose_provider = object() if has_provider else None
    manager._calibrate_robot = Mock()
    manager._init_robot()
    manager.robot.connect.assert_called_once_with()
    manager.robot.activate_physical_control.assert_not_called()
    assert not manager.is_robot_ready


def test_mode_failure_prevents_servo_enable():
    from src.hardware.robot_VIP import FR5Robot, RobotCommandError
    robot = FR5Robot(); robot.dry = False; robot.connected = True
    robot.robot = Mock(); robot.robot.Mode.return_value = 112
    robot._validated_corners = Mock(); robot._validate_gripper_config = Mock()
    with pytest.raises(RobotCommandError):
        robot.activate_physical_control(commissioned=True)
    robot.robot.RobotEnable.assert_not_called()
    assert not robot.physical_motion_authorized
