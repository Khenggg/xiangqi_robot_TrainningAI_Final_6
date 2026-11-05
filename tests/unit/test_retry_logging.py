"""Structured logging for pick measurement and Y/Continue retry requests."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.hardware.hardware_manager import HardwareManager
from src.vision.pick_consensus import PickTargetUnavailable


class _FailingEstimator:
    def __init__(self):
        self.last_reason = "no_valid_detection"
        self.last_measurement = {
            "nearest_col": 4.18,
            "nearest_row": 5.02,
            "nearest_offset_cells": 0.18,
            "nearest_offset_mm": 7.4,
            "nearest_confidence": 0.42,
            "low_confidence": 0,
            "outside_board": 0,
        }

    def estimate_pick_target(self, detections, col, row):
        return None

    def aggregate_targets(self, values, minimum, max_spread_cells=None):
        return None


def _events(caplog):
    return [record for record in caplog.records if getattr(record, "event", None)]


def test_pick_failure_logs_attempt_and_measured_values(caplog):
    hw = SimpleNamespace(
        config=SimpleNamespace(
            VISUAL_PICK_ENABLED=True,
            VISUAL_RING_PICK_ENABLED=False,
            VISUAL_TOP_FACE_ENABLED=False,
            VISUAL_HEIGHT_PICK_ENABLED=False,
            VISUAL_CENTER_PICK_ATTEMPTS=1,
            VISUAL_PICK_MIN_STABLE_SAMPLES=2,
            VISUAL_CENTER_PICK_MAX_JITTER_CELLS=0.12,
            VISUAL_PICK_MAX_OFFSET_MM=6.0,
        ),
        center_pick_estimator=_FailingEstimator(),
        cam_monitor=object(),
        last_pick_resolution={},
        _top_face_enabled=lambda: False,
        _occupancy_snapshot=lambda: (object(), []),
    )

    with caplog.at_level("DEBUG", logger="xiangqi"):
        with pytest.raises(PickTargetUnavailable) as error:
            HardwareManager.get_robot_center_pick_targets(hw, {"moving": (4, 5)})

    resolution = error.value.resolution
    assert resolution["mode"] == "center"
    assert resolution["attempts_detail"][0]["cell"] == [4, 5]
    assert resolution["attempts_detail"][0]["measurement"]["nearest_offset_mm"] == 7.4
    assert resolution["valid_samples"] == {"moving": 0}
    assert resolution["spread_cells"] == {"moving": None}
    names = [record.event for record in _events(caplog)]
    assert "vision.pick_attempt" in names
    assert "vision.pick_failed" in names


def test_retry_rejected_logs_pvp_mode(caplog):
    from src.ui.input_handler import InputHandler

    state = SimpleNamespace(
        session_profile=SimpleNamespace(game_mode="HUMAN_VS_HUMAN"),
        game_epoch=1,
        board_revision=0,
        pending_ai_move=None,
        pending_move=None,
        test_pick_retry=None,
        physical_sync_fault=False,
        move_sync_error=False,
        game_over=False,
        set_status=Mock(),
    )
    handler = InputHandler.__new__(InputHandler)
    handler.state = state
    handler.hw = SimpleNamespace()

    with caplog.at_level("WARNING", logger="xiangqi"):
        handler._retry_visual_pick(source="Y")

    record = next(r for r in _events(caplog) if r.event == "ui.retry_rejected")
    assert record.event_data["mode"] == "HUMAN_VS_HUMAN"
    assert record.event_data["source"] == "Y"
    assert record.event_data["reason"] == "NO_PENDING_MOVE"


def test_self_play_retry_rejected_logs(caplog):
    from src.core.self_play_controller import SelfPlayController

    state = SimpleNamespace(session_profile=SimpleNamespace(game_mode="ROBOT_VS_ROBOT"))
    hw = SimpleNamespace(motion_worker=SimpleNamespace(busy=False))
    controller = SelfPlayController(state, hw)

    with caplog.at_level("WARNING", logger="xiangqi"):
        assert controller.retry_visual_pick(source="Y") is False

    record = next(r for r in _events(caplog) if r.event == "ui.retry_rejected")
    assert record.event_data["mode"] == "ROBOT_VS_ROBOT"
    assert record.event_data["source"] == "Y"
    assert record.event_data["reason"] == "NOT_PICK_PAUSED"


def test_hvr_retry_requested_logs(caplog, monkeypatch):
    from src.ui.input_handler import InputHandler
    import src.core.visual_move_coordinator as coordinator

    monkeypatch.setattr(coordinator, "retry_is_current", lambda state: True)
    state = SimpleNamespace(
        session_profile=SimpleNamespace(game_mode="HUMAN_VS_ROBOT"),
        game_epoch=2,
        board_revision=5,
        pending_ai_move={
            "move": ((6, 4), (5, 4)),
            "moving_color": "r",
            "expected_board": [],
            "captured_piece": ".",
        },
        pending_move=SimpleNamespace(move_id="m1"),
        visual_pick_retry={
            "stage": "pre_pick",
            "reason": "no stable center",
            "resolution": {"mode": "center"},
        },
        test_pick_retry=None,
        game_over=False,
        physical_sync_fault=False,
        move_sync_error=False,
        set_status=Mock(),
    )
    handler = InputHandler.__new__(InputHandler)
    handler.state = state
    handler.hw = SimpleNamespace(dry_run=True)
    handler._queue_or_run = lambda operation: None

    with caplog.at_level("INFO", logger="xiangqi"):
        handler._retry_visual_pick(source="Y")

    record = next(r for r in _events(caplog) if r.event == "ui.retry_pick_requested")
    assert record.event_data["source"] == "Y"
    assert record.event_data["mode"] == "HUMAN_VS_ROBOT"
    assert record.event_data["move_id"] == "m1"
    assert record.event_data["stage"] == "pre_pick"
    assert record.event_data["resolution"] == {"mode": "center"}


def test_v_routes_pick_pause_to_guarded_retry_instead_of_baseline():
    import pygame
    from src.ui.input_handler import InputHandler
    handler = InputHandler.__new__(InputHandler)
    handler.state = SimpleNamespace(
        visual_pick_retry={"stage": "pre_pick"}, physical_sync_fault=False,
        move_sync_error=None, set_status=Mock())
    handler.hw = SimpleNamespace()
    handler._motion_busy = Mock(return_value=False)
    handler._client_capabilities = Mock(return_value={"camera_enabled": True})
    handler._retry_visual_pick = Mock()
    handler.resume_automatic_scanning = Mock()
    handler.handle_keyboard(pygame.K_v)
    handler._retry_visual_pick.assert_called_once_with(source="V")
    handler.resume_automatic_scanning.assert_not_called()


def test_v_never_retries_pick_while_motion_is_busy():
    import pygame
    from src.ui.input_handler import InputHandler
    handler = InputHandler.__new__(InputHandler)
    handler.state = SimpleNamespace(visual_pick_retry={"stage": "pre_pick"}, set_status=Mock())
    handler._motion_busy = Mock(return_value=True)
    handler._retry_visual_pick = Mock()
    handler.handle_keyboard(pygame.K_v)
    handler._retry_visual_pick.assert_not_called()


def test_compact_continue_click_retries_at_actual_rendered_position():
    from src.ui.input_handler import InputHandler
    from src.ui.board_renderer import BoardRenderer, BTN_CONTINUE_RECT
    render_state = dict(client_controls_compact=True, camera_enabled=True,
                        robot_moves_enabled=True, simulation_enabled=True,
                        game_mode='HUMAN_VS_ROBOT', visual_pick_retry=True)
    rect = BoardRenderer.client_continue_rect(render_state)
    assert not BTN_CONTINUE_RECT.collidepoint(rect.center)
    handler = InputHandler.__new__(InputHandler)
    handler.state = SimpleNamespace(visual_pick_retry={'stage':'pre_pick'}, game_over=False,
                                   get_render_state=lambda:render_state)
    handler._motion_busy=Mock(return_value=False)
    handler._retry_visual_pick=Mock()
    handler.handle_mouse_down(*rect.center)
    handler._retry_visual_pick.assert_called_once_with(source='CONTINUE')
