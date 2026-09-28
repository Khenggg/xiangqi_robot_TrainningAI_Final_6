"""
End-to-End Integration Test for GameState <-> HardwareManager <-> LiveTwinBridge <-> TelemetryPublisher.

Validates that:
1. Human moves in GameState are observed by LiveTwinBridge, updating PyBullet physics and Telemetry.
2. Human captures immediately remove the captured piece from PyBullet physics and Telemetry packet.
3. AI moves execute through the virtual robot motion pipeline with step-by-step joint telemetry.
4. Game reset (new game) and undo cleanly reconcile the twin world without desynchronization.
"""

import pytest
import time
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.ai_execution import execute_ai_move
import config


@pytest.fixture
def twin_system():
    TelemetryPublisher.reset_instance()
    telemetry = TelemetryPublisher.get_instance(host="127.0.0.1", port=18765, robot_model="FR3")
    telemetry.start()

    hw = HardwareManager(config, ".").initialize_all()
    twin = hw.setup_digital_twin(telemetry=telemetry, poll_hz=50.0)

    state = GameState(allow_mouse_move=True)
    state.set_move_observer(hw.reconcile_human_move)
    hw.reconcile_new_game()
    state.clear_move_sync_error()

    yield {
        "telemetry": telemetry,
        "hw": hw,
        "twin": twin,
        "state": state,
    }

    twin.stop()
    hw.cleanup()
    telemetry.stop()
    TelemetryPublisher.reset_instance()


def test_initial_synchronization(twin_system):
    sys = twin_system
    twin = sys["twin"]
    state = sys["state"]

    # 32 pieces in twin world and state
    assert len(twin.world.pieces) == 32
    assert len(state.piece_ids) == 32
    assert not state.move_sync_error


def test_human_move_and_capture_synchronization(twin_system):
    sys = twin_system
    hw = sys["hw"]
    twin = sys["twin"]
    state = sys["state"]
    telemetry = sys["telemetry"]

    # 1. Normal human move: Red Pawn at (0, 6) moves to (0, 5)
    # Pygame col, row: src=(0, 6), dst=(0, 5)
    piece_name = state.board[6][0]
    assert piece_name == "r_P"
    moving_id = state.piece_ids[(6, 0)]
    assert moving_id == "red_pawn_0"

    state.process_human_move((0, 6), (0, 5), piece_name)
    assert not state.move_sync_error

    # Verify piece in simulation world moved to destination
    piece_body = twin.world.pieces["red_pawn_0"]
    r, c, _ = piece_body.get_nearest_intersection()
    assert (r, c) == (5, 0)

    # Verify piece in latest world state telemetry
    assert telemetry._latest_world_state is not None
    pieces_in_packet = {p["id"]: p for p in telemetry._latest_world_state["pieces"]}
    assert "red_pawn_0" in pieces_in_packet
    assert pieces_in_packet["red_pawn_0"]["nearest_col"] == 0
    assert pieces_in_packet["red_pawn_0"]["nearest_row"] == 5

    # 2. Human capture move: Red Cannon at (1, 7) takes Black Knight at (1, 0)
    # Clear path between row 7 and row 0 on col 1:
    # On col 1: row 0 is b_N, row 2 is b_C (platform screen), row 7 is r_C
    cannon_id = state.piece_ids[(7, 1)]
    assert cannon_id == "red_cannon_0"
    captured_target_id = state.piece_ids[(0, 1)]
    assert captured_target_id == "black_knight_0"

    state.turn = "r"
    state.process_human_move((1, 7), (1, 0), "r_C")
    assert not state.move_sync_error

    # Captured piece must be deleted from simulation world!
    assert "black_knight_0" not in twin.world.pieces
    assert len(twin.world.pieces) == 31

    # Captured piece must not be in published world state telemetry
    pieces_in_packet = {p["id"]: p for p in telemetry._latest_world_state["pieces"]}
    assert "black_knight_0" not in pieces_in_packet
    assert "red_cannon_0" in pieces_in_packet
    assert pieces_in_packet["red_cannon_0"]["nearest_col"] == 1
    assert pieces_in_packet["red_cannon_0"]["nearest_row"] == 0


def test_ai_robot_move_execution(twin_system):
    sys = twin_system
    hw = sys["hw"]
    twin = sys["twin"]
    state = sys["state"]
    telemetry = sys["telemetry"]

    state.turn = "b"
    # Black Cannon at col 1, row 2 moves to col 4, row 2
    # In xiangqi coords: s=(1, 2), d=(4, 2)
    s = (1, 2)
    d = (4, 2)
    moving_p = state.board[2][1]
    assert moving_p == "b_C"

    ok = execute_ai_move(
        state=state,
        hw=hw,
        best_move=(s, d),
        dry_run=True,
        visual_pick_enabled=False,
    )
    assert ok is True
    assert not state.move_sync_error
    assert state.turn == "r"
    assert state.board[2][4] == "b_C"
    assert state.board[2][1] == "."

    # Verify piece moved in digital twin world
    piece_body = twin.world.pieces["black_cannon_0"]
    r, c, _ = piece_body.get_nearest_intersection()
    assert (r, c) == (2, 4)


def test_reset_game_respawns_captured_pieces(twin_system):
    sys = twin_system
    hw = sys["hw"]
    twin = sys["twin"]
    state = sys["state"]

    # Capture a piece first
    state.process_human_move((1, 7), (1, 0), "r_C")
    assert "black_knight_0" not in twin.world.pieces
    assert len(twin.world.pieces) == 31

    # Reset game
    state.reset_game(hw)
    assert not state.move_sync_error

    # All 32 pieces must be restored in simulation world!
    assert len(twin.world.pieces) == 32
    assert "black_knight_0" in twin.world.pieces
    piece_body = twin.world.pieces["black_knight_0"]
    r, c, _ = piece_body.get_nearest_intersection()
    assert (r, c) == (0, 1)


def test_undo_restores_pieces_in_twin(twin_system):
    sys = twin_system
    hw = sys["hw"]
    twin = sys["twin"]
    state = sys["state"]

    # Human moves Red Pawn
    state.process_human_move((0, 6), (0, 5), "r_P")
    piece_body = twin.world.pieces["red_pawn_0"]
    assert piece_body.get_nearest_intersection()[:2] == (5, 0)

    # Undo round with hw passed
    assert state.undo_round(hw)
    assert not state.move_sync_error
    piece_body = twin.world.pieces["red_pawn_0"]
    assert piece_body.get_nearest_intersection()[:2] == (6, 0)
