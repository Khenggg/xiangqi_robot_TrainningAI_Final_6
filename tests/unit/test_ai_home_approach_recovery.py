"""Reproduce the first offline AI reply with actual PyBullet geometry."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import config
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.hardware.simulation_adapter import execute_virtual_move
from src.simulation.runtime import VirtualXiangqiSimulation


@pytest.mark.parametrize("block_service", [False, True])
def test_first_ai_cannon_move_routes_safely_or_leaves_board_uncommitted(monkeypatch, block_service):
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")
    runtime = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    runtime.connect()
    backend = runtime.backend
    provider = FixedBoardPoseProvider(runtime.placement_state)
    bridge = LiveTwinBridge(backend, provider, world=runtime.world,
                            physical=False, owns_world=False)
    service_attempts = []
    rejected_paths = []
    real_move_joint = backend.move_joint

    def checked_joint(target, **kwargs):
        if np.allclose(target, backend.SERVICE_SAFE_JOINTS_DEG, atol=0.01):
            service_attempts.append(list(target))
            if block_service:
                backend._last_error = "Test interlock: service route unavailable"
                backend._motion_state = "COLLISION_REJECTED"
                return False
        ok = real_move_joint(target, **kwargs)
        if not ok:
            rejected_paths.append(backend._last_error)
        return ok

    monkeypatch.setattr(backend, "move_joint", checked_joint)
    state = GameState(allow_mouse_move=True)
    state.api_client.send_move_update_board = Mock()
    state.set_board_observer(bridge.reconcile_to_board_cells)
    physically_placed = []
    def execute_move(**kwargs):
        result = execute_virtual_move(runtime, **kwargs)
        if result.success:
            # Inspect physics BEFORE the logical commit/board observer can
            # reconcile positions. A post-observer check alone could hide a
            # misplaced piece behind snapshot reconciliation.
            physically_placed.append(runtime.find_nearest_cell(
                runtime.world.pieces["black_cannon_1"].get_position_robot()))
        return result
    hw = SimpleNamespace(is_robot_ready=True, simulation_runtime=runtime,
                         execute_piece_move=execute_move)
    try:
        state.process_human_move((4, 6), (4, 5), "r_P")
        assert state.turn == "b" and not state.move_sync_error
        before = [row[:] for row in state.board]
        result = execute_ai_move(state, hw, ((7, 2), (4, 2)))
        assert service_attempts
        assert any("red_rook_0" in str(error) for error in rejected_paths)
        assert backend.collision_guard_enabled
        if block_service:
            assert not result
            assert state.board == before and state.turn == "b"
            assert state.physical_sync_fault and "service route unavailable" in state.move_sync_error
            assert runtime.world.get_attached_piece() is None
        else:
            assert result, state.move_sync_error
            assert state.board[2][7] == "." and state.board[2][4] == "b_C"
            assert state.turn == "r" and not state.physical_sync_fault
            assert state.piece_ids[(2, 4)] == "black_cannon_1"
            assert physically_placed == [(2, 4)]
            assert runtime.find_nearest_cell(runtime.world.pieces["black_cannon_1"].get_position_robot()) == (2, 4)
            assert runtime.world.get_attached_piece() is None
            assert len(state.move_log) == 2
    finally:
        bridge.close()
        runtime.disconnect()
        runtime.world.close()
