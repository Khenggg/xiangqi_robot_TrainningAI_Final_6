"""Isolated integration probe: actual capture after changing taught board pose."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from pytest import MonkeyPatch
from src.core.ai_execution import execute_ai_move
from src.hardware.simulation_adapter import execute_virtual_move

spec = importlib.util.spec_from_file_location("capture_probe", "tests/unit/test_virtual_capture_execution.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
patch = MonkeyPatch()
fixture = module.capture_game.__wrapped__(patch)
runtime, state = next(fixture)
evidence = {}
try:
    bridge = state._board_observer.__self__
    provider = bridge.board_pose_provider
    runtime.bind_board_pose_provider(provider, bridge)
    prepared = runtime.prepare_board_adjustment()
    assert prepared["success"], prepared
    points = runtime.get_board_teaching_points()["points"]
    center = np.mean(list(points.values()), axis=0)
    angle = np.deg2rad(3)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    points = {name: (center + rotation @ (np.array(xyz) - center) + [10, 0, 0]).tolist() for name, xyz in points.items()}
    applied = runtime.apply_board_teaching_points(points)
    evidence["apply"] = applied
    assert applied["success"], applied
    bridge.start()
    def execute(**kwargs):
        result = execute_virtual_move(runtime, **kwargs)
        evidence["motion_success"] = result.success
        evidence["motion_message"] = result.message
        if result.success:
            victim = runtime.world.pieces["red_cannon_1"]
            moving = runtime.world.pieces["black_rook_1"]
            evidence["victim_before_commit_m"] = victim.get_position_robot().tolist()
            evidence["victim_outside_board"] = not runtime.placement_state.is_in_bounds_robot(victim.get_position_robot())
            evidence["moving_cell_before_commit"] = list(runtime.find_nearest_cell(moving.get_position_robot()))
            evidence["destination_xy_error_mm"] = float(np.linalg.norm((moving.get_position_robot() - runtime.placement_state.cell_to_robot_xyz(7, 7))[:2]) * 1000)
            assert evidence["victim_outside_board"]
            assert evidence["moving_cell_before_commit"] == [7, 7]
            assert evidence["destination_xy_error_mm"] < 1
        return result
    hw = SimpleNamespace(is_robot_ready=True, simulation_runtime=runtime, execute_piece_move=execute)
    evidence["committed"] = execute_ai_move(state, hw, ((7, 0), (7, 7)))
    evidence["fen"] = state.current_fen
    evidence["fault"] = state.move_sync_error
    evidence["placement_version"] = runtime.placement_state.placement_version
    assert evidence["committed"], evidence
    assert state.piece_ids[(7, 7)] == "black_rook_1"
    assert "red_cannon_1" not in runtime.world.pieces
    assert runtime.backend.collision_guard_enabled
    placement = runtime.placement_state
    assert state.undo_round(hw)
    assert runtime.placement_state is placement
    assert bridge._cells == state.piece_ids
    assert "red_cannon_1" in runtime.world.pieces
    evidence["undo_restores_victim_and_cells"] = True
    hw.capture_baseline_if_needed = lambda **kwargs: None
    state.reset_game(hw)
    assert not state.physical_sync_fault and not state.move_sync_error
    assert bridge._cells == state.piece_ids and len(runtime.world.pieces) == 32
    assert runtime.placement_state is placement
    evidence["new_game_preserves_taught_pose_and_resets_32_pieces"] = True
    print("CAPTURE AFTER R1-R4: PASS", evidence)
finally:
    Path("reports/cross-feature-audit-20261005/capture-after-teaching.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    fixture.close()
    patch.undo()
