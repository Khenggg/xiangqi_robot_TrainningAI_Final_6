import json
from unittest.mock import Mock

import numpy as np
import pytest

from src.simulation.board_profile import SimulationBoardProfileStore
from src.simulation.runtime import VirtualXiangqiSimulation, RuntimeOperationState
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.ui.recovery_status import describe_recovery


@pytest.fixture
def store(tmp_path):
    scene = tmp_path / "scene.json"
    scene.write_text('{}', encoding="utf-8")
    return SimulationBoardProfileStore(tmp_path / "profile.json", scene)


def teaching():
    return {"placement_version": 4, "points": {k: [i, 2, 3] for i, k in enumerate(("R1", "R2", "R3", "R4"))}}


def test_atomic_failure_preserves_previous_profile(store, monkeypatch):
    store.save(teaching(), 70)
    before = store.path.read_bytes()
    def fail(*args):
        raise OSError("Disk full")
    monkeypatch.setattr("src.simulation.board_profile.os.replace", fail)
    with pytest.raises(OSError):
        store.save(teaching(), 70)
    assert store.path.read_bytes() == before
    assert not list(store.path.parent.glob(".board-profile-*.tmp"))


@pytest.mark.parametrize("field,value", [("frame", "camera"), ("unit", "m"),
    ("source", "R1_R4_PHYSICAL"), ("schema_version", True), ("calibration_version", None),
    ("points", {"R1": [float("nan"), 0, 0]}), ("safe_transit_height_mm", -1)])
def test_incompatible_or_invalid_record_rejected(store, field, value):
    record = store.save(teaching(), 70)
    record[field] = value
    store.path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        store.load(70)


def test_geometry_or_clearance_change_rejected(store):
    store.save(teaching(), 70)
    with pytest.raises(ValueError, match="Chiều cao"):
        store.load(80)
    store.scene_path.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="hình học"):
        store.load(70)


def test_restart_restores_rotated_shifted_pose_to_all_authorities(tmp_path):
    path = tmp_path / "profile.json"
    first = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    try:
        first.start()
        first.board_profile_store = SimulationBoardProfileStore(path, first.scene_config_path)
        assert first.prepare_board_adjustment()["success"]
        points = first.get_board_teaching_points()["points"]
        center = np.mean(list(points.values()), axis=0)
        a = np.deg2rad(3)
        r = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        rotated = {k: (center + r @ (np.array(v) - center) + [10, 0, 0]).tolist() for k, v in points.items()}
        assert first.apply_board_teaching_points(rotated)["success"]
        version = first.placement_state.placement_version
        assert first.save_board_profile(version)["success"]
    finally:
        first.stop()
    second = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    try:
        second.start()
        second.board_profile_store = SimulationBoardProfileStore(path, second.scene_config_path)
        provider = FixedBoardPoseProvider(second.placement_state)
        second.bind_board_pose_provider(provider)
        old = second.placement_state
        # Restoration cannot bypass supervised preparation.
        assert not second.load_board_profile(old.placement_version)["success"]
        assert second.placement_state is old
        assert second.prepare_board_adjustment()["success"]
        assert second.load_board_profile(old.placement_version)["success"]
        assert second.placement_state is provider.get_board_placement_state()
        assert second.placement_state is second.world.board_placement_state
        assert second.backend.get_state_snapshot().placement_version == second.placement_state.placement_version
        for name, xyz in second.get_board_teaching_points()["points"].items():
            np.testing.assert_allclose(xyz, rotated[name], atol=.01)
        piece = next(iter(second.world.pieces.values()))
        assert np.isfinite(piece.get_position_robot()).all()
        with second.acquire_operation_state(RuntimeOperationState.GAME_MOVE):
            assert not second.load_board_profile(second.placement_state.placement_version)["success"]
        assert not second.load_board_profile(-1)["success"]
    finally:
        second.stop()


def test_recovery_explains_fault_pending_and_turn_without_mutation():
    state = {"physical_sync_fault": True, "move_sync_error": "Camera mismatch",
             "pending_ai_move": ((0, 3), (0, 4)), "move_execution_status": "FAILED"}
    before = dict(state)
    report = describe_recovery(state)
    assert "Camera mismatch" in report["reason"]
    assert "(0, 4)" in report["pending"]
    assert "F4" in report["action"]
    assert state == before
    assert "phím 1" in describe_recovery({**state, "turn_confirmation_required": True})["action"]
    assert "NEW GAME" in describe_recovery({**state, "pick_test_fault": "Motion blocked"})["action"]
    assert describe_recovery({}) is None
    report = describe_recovery({**state, "pending_ai_move": {"move": ((0, 3), (0, 4)), "expected_board": [["secret-board"]]}})
    assert "secret-board" not in report["pending"]
    report = describe_recovery({**state, "robot_backend": "VIRTUAL"})
    assert "NEW GAME" in report["action"] and "camera" not in report["action"]


def test_game_render_exports_recovery_details():
    from src.core.game_state import GameState
    state = GameState()
    state.physical_sync_fault = True
    state.move_execution_error = "Release failed"
    state.pending_ai_move = ((0, 3), (0, 4))
    render = state.get_render_state()
    assert render["physical_sync_fault"]
    assert render["pending_ai_move"] == state.pending_ai_move
    assert describe_recovery(render)["reason"] == "Release failed"


@pytest.mark.parametrize("capture", [False, True])
@pytest.mark.parametrize("camera_confirmed", [False, True])
def test_mock_physical_camera_commit_updates_actual_twin(capture, camera_confirmed):
    """Real game + PyBullet + telemetry; only physical executor/camera are mocked."""
    from types import SimpleNamespace
    from src.core.game_state import GameState
    from src.core.ai_execution import execute_ai_move
    from src.motion.result import MotionExecutionResult
    from src.digital_twin.live_twin_bridge import LiveTwinBridge
    from src.hardware.telemetry_publisher import TelemetryPublisher
    sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
    try:
        sim.start()
        telemetry = TelemetryPublisher(host="127.0.0.1", port=0, robot_model="FR3")
        provider = FixedBoardPoseProvider(sim.placement_state)
        bridge = LiveTwinBridge(sim.backend, provider, telemetry=telemetry,
                                world=sim.world, physical=True, owns_world=False)
        state = GameState()
        state.api_client.send_move_update_board = Mock()
        state.set_board_observer(bridge.reconcile_to_board_cells)
        assert state.sync_current_board()
        if capture:
            state.turn = "r"
            move = ((1, 7), (1, 0))  # Cannon jumps black cannon and captures knight.
            moving_id, captured_id = "red_cannon_0", "black_knight_0"
        else:
            state.turn = "b"
            move = ((0, 3), (0, 4))
            moving_id, captured_id = "black_pawn_0", None
        before = [row[:] for row in state.board]
        hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL"),
            simulation_runtime=None, is_robot_ready=True,
            execute_piece_move=Mock(return_value=MotionExecutionResult.ok()),
            verify_physical_board=Mock(side_effect=[True, camera_confirmed]))
        result = execute_ai_move(state, hw, move)
        assert result is camera_confirmed
        assert hw.verify_physical_board.call_count == 2
        if camera_confirmed:
            row, col, _ = sim.world.pieces[moving_id].get_nearest_intersection()
            assert (col, row) == move[1]
            packet_ids = {p["id"] for p in telemetry._latest_world_state["pieces"]}
            assert moving_id in packet_ids
            if capture:
                assert captured_id not in sim.world.pieces and captured_id not in packet_ids
                assert len(packet_ids) == 31
        else:
            assert state.board == before
            assert state.physical_sync_fault
            assert not execute_ai_move(state, hw, move)
            assert hw.execute_piece_move.call_count == 1
            if capture:
                assert captured_id in sim.world.pieces
    finally:
        sim.stop()
