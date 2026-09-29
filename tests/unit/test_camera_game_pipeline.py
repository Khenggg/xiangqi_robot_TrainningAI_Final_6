"""Camera boards drive GameState, PyBullet bodies and the emitted viewer state."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core import xiangqi
from src.core.game_state import GameState
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.ui.input_handler import InputHandler


@pytest.fixture
def camera_game(monkeypatch):
    monkeypatch.setattr("config.GAME_MODE", "HUMAN_VS_HUMAN")
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    backend = PhysicalFR3Backend(dry_run=True)
    backend.connect()  # dry-run backend; no controller socket
    telemetry = TelemetryPublisher(port=0)
    bridge = LiveTwinBridge(backend, FixedBoardPoseProvider.from_forward_shift(0), telemetry)
    state.set_move_observer(bridge.reconcile_human_move)
    state.set_board_observer(bridge.reconcile_to_board_cells)
    commands = Mock(side_effect=AssertionError("Camera path commanded a robot"))
    backend.move_joint = commands
    backend.move_cartesian = commands
    backend.set_gripper = commands
    camera = SimpleNamespace(get_fresh_snapshot=lambda: (object(), []))
    results = []
    hw = SimpleNamespace(cam_monitor=camera, cchess_recognizer=object(),
                         yolo_detector=None, twin_bridge=bridge,
                         recognize_board_state=lambda frame: results.pop(0),
                         capture_baseline_if_needed=lambda force_delay=0: True)
    try:
        yield state, bridge, telemetry, InputHandler(state, hw), results, commands
    finally:
        bridge.close()


def _scan(handler, results, board, *, quality=True, second=None):
    results.extend([{"success": True, "quality_ok": quality, "board": board},
                    {"success": True, "quality_ok": quality, "board": second if second is not None else board}])
    return handler._handle_space_key()


@pytest.mark.parametrize("start_black,move,captured", [
    (False, ((1, 7), (1, 0)), "black_knight_0"),
    (True, ((1, 2), (1, 9)), "red_knight_0"),
])
def test_camera_capture_either_color_removes_actual_body_and_viewer_piece(camera_game, start_black, move, captured):
    state, bridge, telemetry, handler, results, commands = camera_game
    if start_black:
        state.turn = "b"
    expected, _ = xiangqi.make_temp_move(state.board, move)
    assert _scan(handler, results, expected)
    assert state.board == expected
    assert captured not in bridge.world.pieces
    assert captured not in {piece["id"] for piece in telemetry._latest_world_state["pieces"]}
    assert len(bridge.world.pieces) == 31
    assert state.turn == ("r" if start_black else "b")
    commands.assert_not_called()


def test_camera_moves_both_colors_and_rejects_flicker_or_extra_board_changes(camera_game):
    state, bridge, telemetry, handler, results, commands = camera_game
    for move in [((0, 6), (0, 5)), ((0, 3), (0, 4))]:
        expected, _ = xiangqi.make_temp_move(state.board, move)
        before = deepcopy(state.board)
        assert not _scan(handler, results, expected, second=before)
        assert state.board == before
        assert _scan(handler, results, expected)
        assert state.board == expected
    assert state.piece_ids[(4, 0)] == "black_pawn_0"
    assert bridge.world.pieces["black_pawn_0"].get_nearest_intersection()[:2] == (4, 0)
    assert any(p["id"] == "black_pawn_0" and p["nearest_row"] == 4
               for p in telemetry._latest_world_state["pieces"])
    commands.assert_not_called()


def test_explicit_full_scan_recovers_moved_and_captured_board_without_arm_motion(camera_game):
    state, bridge, telemetry, handler, results, commands = camera_game
    camera_board, _ = xiangqi.make_temp_move(state.board, ((1, 7), (1, 0)))
    results.extend([{"success": True, "quality_ok": True, "board": camera_board}] * 2)
    assert handler.resume_automatic_scanning()
    assert state.board == camera_board
    assert state.piece_ids[(0, 1)] == "red_cannon_0"
    assert state.turn == "b"
    assert "black_knight_0" not in bridge.world.pieces
    assert "black_knight_0" not in {p["id"] for p in telemetry._latest_world_state["pieces"]}
    commands.assert_not_called()


def test_multi_change_rescan_requires_operator_to_confirm_turn(camera_game):
    import pygame

    state, bridge, _telemetry, handler, results, commands = camera_game
    observed = [row[:] for row in state.board]
    observed[6][0], observed[5][0] = ".", observed[6][0]
    observed[3][8], observed[4][8] = ".", observed[3][8]
    results.extend([{"success": True, "quality_ok": True, "board": observed}] * 2)
    assert handler.resume_automatic_scanning()
    assert state.board == observed
    assert state.turn_confirmation_required
    assert state.move_sync_error
    assert "phím 1" in state.status_message
    assert not state.process_human_move((2, 6), (2, 5), "r_P")
    handler.handle_keyboard(pygame.K_2)
    assert state.turn == "b"
    assert not state.turn_confirmation_required
    assert not state.move_sync_error
    commands.assert_not_called()
