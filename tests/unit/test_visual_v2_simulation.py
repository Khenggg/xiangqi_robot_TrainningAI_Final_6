"""Real PyBullet diagnostic parity, including board rotation and collision rejection."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from src.hardware.hardware_manager import HardwareManager
from src.core.game_state import GameState
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer


def test_hover_rotated_r1_r4_uses_guard_and_preserves_pieces(monkeypatch):
    import config
    monkeypatch.setattr(config,'ROBOT_BACKEND','VIRTUAL')
    monkeypatch.setattr(config,'DRY_RUN',True)
    monkeypatch.setattr(config,'GAME_ONLY',False,raising=False)
    manager=HardwareManager(config,Path(__file__).resolve().parents[2])
    manager._init_robot()
    bridge=manager.setup_digital_twin(start=False)
    state=GameState(allow_mouse_move=True)
    state.api_client=Mock(room_id=None)
    state.set_board_observer(bridge.reconcile_to_board_cells)
    runtime=manager.simulation_runtime
    try:
        assert state.sync_current_board()
        assert runtime.runtime_go_service_safe()['success']
        assert runtime.prepare_board_adjustment()['success']
        points=runtime.get_board_teaching_points()['points']
        center=np.mean(list(points.values()),axis=0)
        a=np.deg2rad(3)
        rotation=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
        points={k:(center+rotation@(np.array(v)-center)+[10,0,0]).tolist() for k,v in points.items()}
        assert runtime.apply_board_teaching_points(points)['success']
        before={pid:piece.get_position_robot().copy() for pid,piece in runtime.world.pieces.items()}
        fen=state.current_fen
        pose=manager.execute_hover_test((4,6))
        target=runtime.placement_state.cell_to_robot_xyz(6,4)*1000
        assert np.linalg.norm(np.array(pose[:2])-target[:2])<.1
        assert pose[2]>target[2]
        assert runtime.world.get_attached_piece() is None and state.current_fen==fen
        for pid,p in before.items():
            assert np.linalg.norm(runtime.world.pieces[pid].get_position_robot()-p)<.001
        assert np.linalg.norm(np.array(manager.backend.get_state_snapshot().tcp_pose_mm_deg[:3])-np.array(pose[:3]))<1
        # Same API must refuse a diagnostic if its guard is disabled.
        manager.backend.collision_guard_enabled=False
        frozen=manager.backend.get_state_snapshot().joints_deg
        with pytest.raises(RuntimeError,match='collision guard'):
            manager.execute_hover_test((4,6))
        assert manager.backend.get_state_snapshot().joints_deg==frozen
    finally:
        manager.cleanup()


def test_hover_ui_keeps_test_and_game_identity(monkeypatch):
    import pygame
    state=GameState(allow_mouse_move=True)
    state.api_client=Mock(room_id=None)
    hw=Mock(config=SimpleNamespace(),dry_run=True)
    hw.motion_worker=None
    handler=InputHandler(state,hw)
    handler.handle_keyboard(pygame.K_t)
    before=(state.current_fen,dict(state.piece_ids),dict(state.pick_test_piece_ids))
    handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(4,6))
    handler.handle_keyboard(pygame.K_h)
    hw.execute_hover_test.assert_called_once_with((4,6))
    hw.execute_pick_place_test.assert_not_called()
    assert before==(state.current_fen,state.piece_ids,state.pick_test_piece_ids)
