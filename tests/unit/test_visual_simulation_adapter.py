"""Merge-boundary tests; every controller is mocked and no SDK is connected."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.hardware.hardware_manager import HardwareManager
from src.hardware.simulation_adapter import (
    BorrowedPhysicalStateSource, execute_virtual_move, physical_board_provider,
)
from src.domain.board_pose import BoardPlacementState


def manager(tmp_path, mode="PHYSICAL", dry=False):
    cfg = SimpleNamespace(DRY_RUN=dry, ROBOT_BACKEND=mode)
    h = HardwareManager(cfg, tmp_path)
    h.robot = SimpleNamespace(connected=True, dry=False, robot=Mock(), ip="unused",
                             physical_motion_authorized=False, connect=Mock())
    return h


def test_physical_connect_is_read_only_and_uncalibrated_motion_blocked(tmp_path):
    h = manager(tmp_path)
    h._init_robot()
    h.robot.connect.assert_called_once()
    assert not h.is_robot_ready
    assert h.board_pose_provider is None
    h.robot.robot.RobotEnable.assert_not_called()
    h.robot.robot.MoveJ.assert_not_called()
    h.robot.robot.SetToolDO.assert_not_called()
    assert not h.execute_piece_move(0, 0, 0, 1, False)


def test_physical_dry_run_does_not_connect(tmp_path):
    h = manager(tmp_path, dry=True)
    h._init_robot()
    h.robot.connect.assert_not_called()


def test_borrowed_source_uses_existing_handle_only():
    rpc = Mock()
    robot = SimpleNamespace(connected=True, dry=False, robot=rpc, ip="unused")
    with patch("src.hardware.backends.physical_fr3.robot_sdk_core.RPC") as create:
        source = BorrowedPhysicalStateSource(robot)
        assert source._reader._rpc is rpc
        create.assert_not_called()
    assert not hasattr(source, "move_cartesian")
    assert not hasattr(source, "set_gripper")


def test_unknown_contact_offset_cannot_read_teaching_points():
    robot = SimpleNamespace(robot=Mock())
    with pytest.raises(ValueError, match="contact offset"):
        physical_board_provider(robot, SimpleNamespace())
    robot.robot.GetRobotTeachingPoint.assert_not_called()


def test_visual_command_correction_is_diagnostic_not_a_motion_interlock():
    state = BoardPlacementState.compute(0.)
    points = {}
    for name, cell in zip(("R1", "R2", "R3", "R4"), ((0, 0), (0, 8), (9, 8), (9, 0))):
        points[name] = list(state.cell_to_robot_xyz(*cell) * 1000.) + [180., 0., 0.] + [0.] * 6 + [2., 0.]
    rpc = Mock()
    rpc.GetRobotTeachingPoint.side_effect = lambda name: (0, points[name])
    robot = SimpleNamespace(robot=rpc, tool_num=0, user_num=1,
        board_to_pose_bilinear=lambda col, row, z: list(state.cell_to_robot_xyz(row, col)[:2] * 1000.) + [z])
    cfg = SimpleNamespace(BOARD_CALIBRATION_OFFSET_MM=[0., 0., 0.],
        BOARD_CALIBRATION_OFFSET_FRAME="ROBOT_BASE", BOARD_CALIBRATION_PROVENANCE="SYNTHETIC_TEST_ONLY")
    assert physical_board_provider(robot, cfg).is_calibrated
    assert (robot.tool_num, robot.user_num) == (2, 0)
    robot.tool_num, robot.user_num = 0, 1
    robot.board_to_pose_bilinear = lambda col, row, z: list(state.cell_to_robot_xyz(row,col)[:2]*1000. + [5.,0.]) + [z]
    provider = physical_board_provider(robot, cfg)
    assert provider.visual_command_xy_difference_mm == pytest.approx(5., abs=.001)
    assert (robot.tool_num, robot.user_num) == (2, 0)


def test_virtual_failed_pick_never_places_or_reports_success():
    state = BoardPlacementState.compute(0.0)
    piece = SimpleNamespace(get_position_robot=lambda: state.cell_to_robot_xyz(0, 0))
    runtime = SimpleNamespace(world=SimpleNamespace(pieces={"black_rook_0": piece}),
                              placement_state=state, find_nearest_cell=lambda _: (0, 0),
                              pick_piece=Mock(return_value={"success": False, "error": "NO_JAW_CONTACT"}),
                              place_piece=Mock())
    result = execute_virtual_move(runtime, 0, 0, 0, 1, False)
    assert not result and not result.success
    assert "NO_JAW_CONTACT" in result.message
    runtime.place_piece.assert_not_called()


def test_virtual_capture_without_configured_disposal_is_rejected_before_pick():
    state = BoardPlacementState.compute(0.0)
    runtime = SimpleNamespace(pick_piece=Mock(), capture_area={}, placement_state=state,
        find_nearest_cell=lambda pos: (0, 0) if np.allclose(pos, state.cell_to_robot_xyz(0, 0)) else (1, 0),
        world=SimpleNamespace(pieces={
            "black_rook_0": SimpleNamespace(get_position_robot=lambda: state.cell_to_robot_xyz(0, 0)),
            "red_rook_0": SimpleNamespace(get_position_robot=lambda: state.cell_to_robot_xyz(1, 0))}))
    result = execute_virtual_move(runtime, 0, 0, 0, 1, True, piece_id="black_rook_0")
    assert not result
    runtime.pick_piece.assert_not_called()


def test_physical_typed_result_and_callbacks_are_preserved(tmp_path):
    h = manager(tmp_path)
    h.physical_telemetry_ready = Mock(return_value=True)
    h.robot.physical_motion_authorized = True
    h.board_pose_provider = object()
    from src.hardware.simulation_adapter import SimulationMotionResult
    expected = SimulationMotionResult.ok()
    h.robot.move_piece = Mock(return_value=expected)
    callback = Mock()
    assert h.execute_piece_move(0, 0, 0, 1, False, piece_id="black_rook_0",
                                refresh_moving_visual_target=callback) is expected
    h.robot.move_piece.assert_called_once_with(0, 0, 0, 1, False,
                                               refresh_moving_visual_target=callback)
