from unittest.mock import Mock
import pytest

from src.hardware.robot_VIP import FR5Robot, MotionStage


def make_robot():
    robot = FR5Robot()
    robot.connected = True
    robot.dry = False
    robot.pick_at = Mock()
    robot.move_to_extra_safe = Mock()
    robot.place_in_capture_bin = Mock()
    robot.place_at = Mock()
    robot.go_to_home_chess = Mock()
    return robot


def test_move_piece_returns_completed_result_after_safe_home():
    robot = make_robot()

    result = robot.move_piece(0, 0, 0, 1, is_capture=False)

    assert result.success is True
    assert result.stage is MotionStage.COMPLETED
    robot.pick_at.assert_called_once_with(0, 0, visual_target=None)
    robot.place_at.assert_called_once_with(0, 1)
    robot.go_to_home_chess.assert_called_once()


def test_move_piece_returns_failed_result_when_motion_stage_raises():
    robot = make_robot()
    robot.place_at.side_effect = RuntimeError("place failed")

    result = robot.move_piece(0, 0, 0, 1, is_capture=False)

    assert result.success is False
    assert result.stage is MotionStage.PLACE
    assert "place failed" in result.error
    robot.go_to_home_chess.assert_not_called()


def test_capture_reconcile_failure_preserves_legacy_recovery_exception():
    robot = make_robot()
    reconcile_capture = Mock(return_value=False)

    with pytest.raises(RuntimeError, match="not visually clear"):
        robot.move_piece(0, 0, 0, 1, is_capture=True, verify_capture_cleared=reconcile_capture)

    assert robot.pick_at.call_count == 1
    assert robot.pick_at.call_args.args[:2] == (0, 1)
    robot.place_at.assert_not_called()


def test_geometry_refresh_fallback_does_not_fail_successful_motion():
    robot = make_robot()
    refresh_target = Mock(return_value=None)

    result = robot.move_piece(
        0, 0, 0, 1, is_capture=False,
        refresh_moving_visual_target=refresh_target,
    )

    assert result.success is True
    assert result.stage is MotionStage.COMPLETED
