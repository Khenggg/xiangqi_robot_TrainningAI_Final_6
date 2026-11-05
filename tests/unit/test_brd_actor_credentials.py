"""BRD A-03/A-08/A-10/A-12 without live network or robot construction."""
import ast
import re
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from src.core.game_state import GameState
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    return GameState()


@pytest.mark.parametrize('mode', ['HUMAN_VS_HUMAN', 'HUMAN_VS_ROBOT', None])
def test_self_play_rejects_other_or_unspecified_game_modes(state, mode):
    hw = SimpleNamespace(config=SimpleNamespace(GAME_MODE=mode, ROBOT_BACKEND='VIRTUAL'),
                         dry_run=True, is_robot_ready=True, execute_piece_move=Mock())
    ctrl = SelfPlayController(state, hw)
    assert not ctrl.start()
    assert not state.physical_sync_fault
    hw.execute_piece_move.assert_not_called()


def test_rvr_defaults_to_continuous_without_dispatching_in_start(state):
    hw = SimpleNamespace(config=SimpleNamespace(GAME_MODE='ROBOT_VS_ROBOT', ROBOT_BACKEND='VIRTUAL'),
                         dry_run=True, is_robot_ready=True, execute_piece_move=Mock())
    ctrl = SelfPlayController(state, hw)
    assert ctrl.start()
    assert ctrl.run_mode == 'continuous'
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('move,error', [(((0,0),(0,0)), None), (None, RuntimeError('engine unavailable'))])
def test_engine_failure_before_dispatch_is_not_physical_desynchronization(state, move, error):
    hw = SimpleNamespace(config=SimpleNamespace(GAME_MODE='ROBOT_VS_ROBOT', ROBOT_BACKEND='VIRTUAL'),
                         dry_run=True, is_robot_ready=True, execute_piece_move=Mock())
    ctrl = SelfPlayController(state, hw)
    ctrl.status = SelfPlayStatus.THINKING
    token = ctrl._current_token()
    ctrl._token = token
    ctrl._thread = Mock(is_alive=Mock(return_value=False))
    ctrl._result = (token, [row[:] for row in state.board], state.turn, move, error)
    ctrl.tick()
    assert ctrl.status == SelfPlayStatus.FAULTED
    assert not state.physical_sync_fault and not state.snapshot_continue_required
    assert state.pending_move is None and state.pending_ai_move is None
    hw.execute_piece_move.assert_not_called()


def test_spectator_credential_comes_from_environment(monkeypatch):
    monkeypatch.setenv('XIANGQI_SIMULATION_TOKEN', 'unit-test-token')
    assert runpy.run_path(str(Path('config.py').resolve()))['SIMULATION_TOKEN'] == 'unit-test-token'
    monkeypatch.delenv('XIANGQI_SIMULATION_TOKEN')
    assert runpy.run_path(str(Path('config.py').resolve()))['SIMULATION_TOKEN'] == ''


def test_tracked_config_snapshots_do_not_embed_spectator_credentials():
    paths = [Path('config.py'), Path('reports/camera-gpu-fix-20261013/baseline/config.py'),
             Path('reports/visual-preintegration-20261009/conflicts/config.py')]
    for path in paths:
        # Historical conflict evidence is text, not an importable Python module.
        assignments = '\n'.join(line for line in path.read_text(encoding='utf-8-sig').splitlines()
                                if re.match(r'^SIMULATION_TOKEN\s*=', line))
        for node in ast.walk(ast.parse(assignments)):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SIMULATION_TOKEN' for t in node.targets):
                assert not (isinstance(node.value, ast.Constant) and node.value.value)
