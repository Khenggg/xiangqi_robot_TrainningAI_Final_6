"""Exercise queued spectator lifecycle with real controller and mocked HTTP."""
import threading
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api.simulation_client import TuongKyDaiSuClient
from src.core.game_state import GameState


@pytest.fixture
def spectator(monkeypatch):
    calls = []
    rooms = []
    def post(url, **kwargs):
        calls.append((url, kwargs['json']))
        if url.endswith('/matches'):
            rooms.append(len(rooms) + 1)
            data = {'roomId': rooms[-1]}
        else:
            data = {}
        return SimpleNamespace(status_code=200, json=lambda: {'success': True, 'data': data})
    monkeypatch.setattr('src.api.simulation_client.requests.post', post)
    client = TuongKyDaiSuClient('https://unused.test', 'mock-token')
    yield client, calls
    client.close(2)


def drain(client):
    # Bounded wait rather than an unbounded Queue.join on a failing worker.
    finished = threading.Event()
    assert client._submit(finished.set)
    assert finished.wait(2)


def controller(monkeypatch, client):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: client)
    state = GameState()
    settled = threading.Event()
    settled.set()
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL', GAME_MODE='HUMAN_VS_ROBOT'), dry_run=False,
                         request_controlled_stop=lambda *a,**kw: SimpleNamespace(done=settled,result=SimpleNamespace(safe=True)),
                         stop_coordinator=SimpleNamespace(safe_for_release=lambda **kw:True),
                         simulation_runtime=None, is_robot_ready=True, cam_monitor=object(),
                         verify_physical_board=Mock(return_value=True),
                         capture_baseline_if_needed=Mock(return_value=True),
                         execute_piece_move=Mock())
    return SimpleNamespace(state=state, hw=hw)


def test_repeated_ensure_opens_one_room_with_current_fen(spectator):
    api, calls = spectator
    assert api.ensure_match(initial_fen='current-fen')
    assert api.ensure_match(initial_fen='current-fen')
    drain(api)
    assert [(u.rsplit('/', 1)[-1], p) for u, p in calls] == [
        ('matches', {'redPlayerName': 'Người chơi Đỏ', 'blackPlayerName': 'Robot AI'}),
        ('fen', {'fen': 'current-fen'}),
    ]


def test_failed_create_can_be_retried_without_sending_fen_to_old_room(spectator, monkeypatch):
    api, calls = spectator
    original_create = api._create_match
    monkeypatch.setattr(api, '_create_match', Mock(return_value=None))
    assert api.ensure_match(initial_fen='fen')
    drain(api)
    assert not api.send_move_update_board('dropped')
    monkeypatch.setattr(api, '_create_match', original_create)
    assert api.ensure_match(initial_fen='fen')
    drain(api)
    assert len(calls) == 2 and calls[-1][1] == {'fen': 'fen'}


def test_closed_room_rejects_new_fen_and_duplicate_end(spectator):
    api, calls = spectator
    assert api.create_match()
    assert api.end_match()
    assert not api.end_match()
    assert not api.send_move_update_board('after-end')
    drain(api)
    assert len(calls) == 2


def test_older_failed_create_cannot_cancel_newer_queued_session(spectator, monkeypatch):
    api, calls = spectator
    entered, release = threading.Event(), threading.Event()
    original = api._create_match
    def first_fails(*args):
        entered.set()
        assert release.wait(2)
        return None
    monkeypatch.setattr(api, '_create_match', first_fails)
    try:
        assert api.ensure_match()
        assert entered.wait(1)
        assert api.end_match()
        assert api.ensure_match(initial_fen='new-session')
        monkeypatch.setattr(api, '_create_match', original)
        release.set()
        drain(api)
        assert api.send_move_update_board('next-move')
        drain(api)
        assert [p['fen'] for u, p in calls if u.endswith('/fen')] == ['new-session', 'next-move']
    finally:
        release.set()


def test_failed_end_never_routes_resumed_board_to_old_room(spectator, monkeypatch):
    api, calls = spectator
    assert api.create_match()
    drain(api)
    monkeypatch.setattr(api, '_end_match', Mock())  # simulate timeout retaining old room_id
    assert api.end_match()
    assert api.ensure_match(initial_fen='resumed-board')
    drain(api)
    assert calls[-1][0].endswith('/2/fen')


def test_queue_full_does_not_change_session_state_and_close_rejects_ensure(spectator):
    api, calls = spectator
    # Freeze worker creation for a deterministic full queue, without HTTP.
    api._worker = Mock()
    for _ in range(api._jobs.maxsize):
        api._jobs.put_nowait((lambda: None, ()))
    assert not api.ensure_match()
    assert api._match_requested is None
    api._jobs.get_nowait()
    api._jobs.task_done()
    assert api.ensure_match()
    assert not api.end_match()  # failed enqueue must leave the desired room open
    assert api._match_requested is True
    api.close()
    assert not api.ensure_match()
    assert calls == []


@pytest.mark.parametrize('mode', ['HUMAN_VS_ROBOT', 'HUMAN_VS_HUMAN_ROBOT'])
def test_main_startup_uses_single_room_for_each_mode(spectator, monkeypatch, mode):
    # Execute the actual helper in isolation; importing main launches the UI loop.
    # This is a wiring test, not a GUI or physical acceptance test.
    api, calls = spectator
    ctrl = controller(monkeypatch, api)
    source = Path(__file__).resolve().parents[2] / 'main.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_start_selected_game')
    env = dict(hw=ctrl.hw, state=ctrl.state,
               config=SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND='PHYSICAL', GAME_MODE=mode))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), env)
    env['_start_selected_game']()
    drain(api)
    assert sum(u.endswith('/matches') for u, _ in calls) == 1
    # Room creation already acknowledges the standard starting FEN; resending
    # that unchanged board is rejected by the remote server.
    assert len(calls) == 1
    assert api._last_fen_ack == (str(api.room_id), ctrl.state.current_fen)

