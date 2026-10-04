"""Actual PyBullet reproduction of the user's stopped h9h2 capture."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import config
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.core.fen_utils import fen_to_board_array
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.hardware.simulation_adapter import execute_virtual_move, select_capture_slot
from src.simulation.runtime import VirtualXiangqiSimulation, RuntimeOperationState, RuntimeOperationBusy

FEN = "rnbakabr1/9/1c2c1n2/p1p1p1p1p/4P4/9/P1P3P1P/4C2C1/4A4/RNBAK1BNR b - - 0 8"


@pytest.fixture
def capture_game(monkeypatch):
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")
    runtime = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    runtime.connect()
    state = GameState(allow_mouse_move=True)
    state.board, state.turn = fen_to_board_array(FEN)
    state.move_number = 8
    state.update_fen_from_board()
    for src, dst in [((2,7),(2,4)), ((0,7),(2,6)), ((0,8),(0,7)),
                     ((7,1),(7,4)), ((6,4),(4,4)), ((9,5),(8,4))]:
        state.piece_ids[dst] = state.piece_ids.pop(src)
    bridge = LiveTwinBridge(runtime.backend, FixedBoardPoseProvider(runtime.placement_state),
                            world=runtime.world, physical=False, owns_world=False)
    state.set_board_observer(bridge.reconcile_to_board_cells)
    state.api_client.send_move_update_board = Mock()
    assert state.sync_current_board()
    assert runtime.runtime_go_service_safe()["success"]
    try:
        yield runtime, state
    finally:
        bridge.close()
        runtime.disconnect()
        runtime.world.close()


@pytest.mark.parametrize("blocked_release", [False, True])
def test_capture_physics_precedes_commit_and_failed_land_retains_victim(capture_game, monkeypatch, blocked_release):
    runtime, state = capture_game
    before = [row[:] for row in state.board]
    before_fen = state.current_fen
    source_before = runtime.world.pieces["black_rook_1"].get_position_robot().copy()
    original = runtime.backend.move_cartesian
    def move_cartesian(pose, **kwargs):
        if blocked_release and pose[2] < 10.0:
            runtime.backend._last_error = "Test obstacle blocks capture landing"
            runtime.backend._motion_state = "COLLISION_REJECTED"
            return False
        return original(pose, **kwargs)
    monkeypatch.setattr(runtime.backend, "move_cartesian", move_cartesian)
    physics_evidence = []
    def execute(**kwargs):
        result = execute_virtual_move(runtime, **kwargs)
        if result.success:
            # BEFORE commit can reconcile/remove the victim collider.
            victim = runtime.world.pieces["red_cannon_1"]
            victim_pos = victim.get_position_robot()
            physics_evidence.append(victim_pos.copy())
            assert not runtime.placement_state.is_in_bounds_robot(victim_pos)
            assert abs(victim_pos[2] - victim.height_m / 2) < 0.001
            assert np.linalg.norm(victim.get_velocity()[0]) < 0.01
            assert runtime.find_nearest_cell(runtime.world.pieces["black_rook_1"].get_position_robot()) == (7,7)
            assert runtime.world.get_attached_piece() is None
        return result
    hw = SimpleNamespace(is_robot_ready=True, simulation_runtime=runtime, execute_piece_move=execute)
    result = execute_ai_move(state, hw, ((7,0),(7,7)))
    assert runtime.backend.collision_guard_enabled
    assert runtime.operation_state == RuntimeOperationState.IDLE
    if blocked_release:
        assert not result and state.board == before and state.current_fen == before_fen
        assert state.turn == "b" and state.physical_sync_fault
        assert "blocks capture landing" in state.move_sync_error
        assert runtime.world.get_attached_piece().piece_id == "red_cannon_1"
        np.testing.assert_allclose(runtime.world.pieces["black_rook_1"].get_position_robot(), source_before, atol=0.001)
    else:
        assert result, state.move_sync_error
        assert len(physics_evidence) == 1
        assert state.turn == "r" and state.board[7][7] == "b_R" and state.board[0][7] == "."
        assert state.piece_ids[(7,7)] == "black_rook_1"
        assert "red_cannon_1" not in state.piece_ids.values()
        assert "red_cannon_1" not in runtime.world.pieces
        assert state.r_captured == ["r_C"]
        assert not state.physical_sync_fault


def test_capture_wrong_victim_does_not_move_robot(capture_game):
    runtime, _ = capture_game
    before = runtime.backend.get_state_snapshot()
    result = execute_virtual_move(runtime,7,0,7,7,True,
                                  piece_id="black_rook_1",captured_piece_id="red_cannon_0")
    assert not result.success and "identity" in result.message
    assert runtime.backend.get_state_snapshot().joints_deg == before.joints_deg
    assert runtime.world.get_attached_piece() is None


def test_live_poll_cannot_rewind_borrowed_runtime_world(capture_game):
    from dataclasses import replace
    import time
    runtime, state = capture_game
    bridge = state._board_observer.__self__
    current = runtime.backend.get_state_snapshot()
    queued_old_pose = replace(current, joints_deg=list(runtime.backend.DEFAULT_HOME_JOINTS_DEG),
                              timestamp=time.time(), measurement_timestamp=None)
    joints = runtime.world._synced_robot_joints.copy()
    tcp = runtime.world.gripper.tcp_pos.copy()
    simulation_time = runtime.world.sim_time
    assert bridge.sync_robot_state(queued_old_pose)
    np.testing.assert_allclose(runtime.world._synced_robot_joints, joints, atol=0)
    np.testing.assert_allclose(runtime.world.gripper.tcp_pos, tcp, atol=0)
    assert runtime.world.sim_time == simulation_time


@pytest.mark.parametrize("never_settles", [False, True])
@pytest.mark.parametrize("start_from_home", [False, True])
def test_elephant_capture_with_running_live_poll(capture_game, monkeypatch, never_settles, start_from_home):
    runtime, state = capture_game
    state.board, state.turn = fen_to_board_array(
        "rnbakab2/9/1c7/p1p1n1p1p/9/9/P1P3P1P/Rc2B2r1/9/1NBAKA1NR b - - 0 16")
    state.piece_ids = GameState().piece_ids
    for cell in ((7,7),(7,1),(6,4),(3,4)):
        state.piece_ids.pop(cell)
    for src, dst in [((2,7),(7,1)), ((0,7),(3,4)), ((0,8),(7,7)), ((9,0),(7,0)), ((9,6),(7,4))]:
        state.piece_ids[dst] = state.piece_ids.pop(src)
    assert state.sync_current_board()
    if start_from_home:
        assert runtime.backend.move_joint(runtime.backend.DEFAULT_HOME_JOINTS_DEG)
    bridge = state._board_observer.__self__
    bridge.start()
    if never_settles:
        from src.simulation.physics.piece import PiecePhysicalState
        original_settle = runtime.world.step_until_settled
        def settle_with_persistent_disturbance(max_steps=None):
            steps = original_settle(max_steps=max_steps)
            if runtime.backend.get_state_snapshot().trajectory_stage == "PAYLOAD_CLEAR":
                runtime.world.pieces["red_knight_1"].physical_state = PiecePhysicalState.SETTLING
            return steps
        monkeypatch.setattr(runtime.world, "step_until_settled", settle_with_persistent_disturbance)
    physical_evidence = []
    def execute(**kwargs):
        result = execute_virtual_move(runtime, **kwargs)
        if result.success:
            victim = runtime.world.pieces["red_elephant_1"]
            assert not runtime.placement_state.is_in_bounds_robot(victim.get_position_robot())
            assert abs(victim.get_position_robot()[2] - victim.height_m / 2.0) < 0.001
            assert runtime.find_nearest_cell(runtime.world.pieces["black_rook_1"].get_position_robot()) == (7,4)
            physical_evidence.append(True)
        return result
    hw = SimpleNamespace(is_robot_ready=True,simulation_runtime=runtime,execute_piece_move=execute)
    result = execute_ai_move(state,hw,((7,7),(4,7)))
    if never_settles:
        assert not result and "PAYLOAD_UNSAFE_WORLD_NOT_SETTLED" in state.move_sync_error
        assert state.turn == "b" and state.board[7][4] == "r_E"
        assert state.physical_sync_fault and runtime.world.get_attached_piece() is not None
        return
    assert result, (state.move_sync_error, [
        (body.piece_id, str(body.physical_state), body.get_position_robot().tolist(),
         [v.tolist() for v in body.get_velocity()]) for body in runtime.world.pieces.values()
        if str(body.physical_state).endswith(("SETTLING", "FALLING"))])
    assert physical_evidence == [True] and state.turn == "r"
    assert state.board[7][4] == "b_R" and state.board[7][7] == "."
    assert "red_elephant_1" not in runtime.world.pieces


def test_batch_excludes_other_threads_but_allows_owned_pick_steps(capture_game):
    runtime, _ = capture_game
    rejected = []
    def contender():
        try:
            with runtime.acquire_operation_state(RuntimeOperationState.MOTION):
                rejected.append(False)
        except RuntimeOperationBusy:
            rejected.append(True)
    with runtime.acquire_operation_state(RuntimeOperationState.GAME_MOVE):
        with runtime.acquire_operation_state(RuntimeOperationState.MOTION):
            assert runtime.operation_state == RuntimeOperationState.GAME_MOVE
            with pytest.raises(RuntimeOperationBusy):
                with runtime.acquire_operation_state(RuntimeOperationState.MOTION):
                    pass
        worker = threading.Thread(target=contender)
        worker.start(); worker.join(timeout=2)
        assert not worker.is_alive()
        assert rejected == [True]


def test_capture_area_inside_board_is_invalid(capture_game):
    runtime, _ = capture_game
    slot = select_capture_slot(runtime)
    assert slot is not None
    # Reconfigure the only available slot to an occupied board location.
    runtime.capture_area = {"support":"SIMULATED_FLOOR", "slots_in_board_grid":[[7,7]]}
    with pytest.raises(ValueError, match="inside the board"):
        select_capture_slot(runtime)


def test_occupied_slot_is_skipped_and_slot_frame_follows_board(capture_game):
    from dataclasses import replace
    runtime, _ = capture_game
    original = runtime.placement_state
    slot = select_capture_slot(runtime)
    fake = SimpleNamespace(capture_area={"support":"SIMULATED_FLOOR","slots_in_board_grid":[[12,2]]},
        placement_state=original, geom=runtime.geom, PLACE_RELEASE_CLEARANCE_M=runtime.PLACE_RELEASE_CLEARANCE_M,
        target_tool_euler_deg=runtime.target_tool_euler_deg,
        backend=SimpleNamespace(solve_tcp_ik=Mock(return_value=SimpleNamespace(success=True))),
        world=SimpleNamespace(pieces={"occupied":SimpleNamespace(get_position_robot=lambda:slot)}))
    assert select_capture_slot(fake) is None
    fake.backend.solve_tcp_ik.assert_not_called()
    fake.world.pieces = {}
    shifted = replace(original, board_yaw_deg=90.0, rotation_matrix=None,
                      board_center_robot_m=[original.board_center_robot_m[0]+0.03,
                                            original.board_center_robot_m[1]+0.02,
                                            original.board_center_robot_m[2]])
    fake.placement_state = shifted
    moved = select_capture_slot(fake)
    assert not np.allclose(slot[:2], moved[:2])
    np.testing.assert_allclose(original.robot_to_board_local(slot)[:2],
                               shifted.robot_to_board_local(moved)[:2], atol=1e-9)
    assert moved[2] == 0.0
