"""BRD A-03/A-08/A-10/A-12 without live network or robot construction."""
import ast
import re
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from src.core.game_state import GameState


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    return GameState()


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
