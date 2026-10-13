"""Real main.py/Pygame F8 -> F6 event routing; all devices and HTTP mocked."""
import atexit
import inspect
import json
import os
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import pygame
import config
from src.core.motion_worker import MotionWorker
from src.ui.board_renderer import BoardRenderer

calls, callbacks, checkpoints = [], [], []
created = []
def post(url, **kw):
    calls.append((url.rsplit('/api/', 1)[-1], kw['json']))
    if url.endswith('/matches'):
        created.append(len(created)+1)
        data = {'roomId': created[-1]}
    else:
        data = {}
    return SimpleNamespace(status_code=200, json=lambda: {'success': True, 'data': data})

hw = SimpleNamespace(config=config, dry_run=False, is_robot_ready=True, simulation_runtime=None,
    motion_worker=MotionWorker(), cam_monitor=SimpleNamespace(update_display=lambda: -1),
    capture_baseline_if_needed=Mock(return_value=True), verify_physical_board=Mock(return_value=True),
    execute_piece_move=Mock(side_effect=AssertionError('No motion authorized in this probe')),
    difficulty_availability=Mock(return_value=dict.fromkeys(['easy','medium','hard','impossible'],True)),
    select_difficulty=Mock(return_value=(True, 'Mock engine ready')), robot=None, backend=None,
    cleanup=Mock(), poll_board_observation=Mock(return_value=None))
phase = 0
deadline = time.monotonic()+15
def events():
    global phase
    assert time.monotonic()<deadline, f'GUI lifecycle stalled at phase {phase}'
    g = inspect.currentframe().f_back.f_globals
    if phase == 0:
        phase = 1
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(0,0), button=1)]
    if phase == 1 and g.get('difficulty_menu_active'):
        phase = 2
        return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)]
    ctrl = g.get('self_play')
    manager = g.get('hw')
    if manager is None or manager.motion_worker.busy or ctrl is None:
        return []
    if phase == 2 and ctrl.status.value == 'ready' and len(calls)>=2:
        checkpoints.append({'phase':'initial-ready', 'fen': g['state'].current_fen})
        phase = 3
        return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8)]
    if phase == 3 and ctrl.status.value in ('ended','idle') and len(calls)>=3:
        checkpoints.append({'phase':'stopped', 'fen':g['state'].current_fen})
        phase = 4
        return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6)]
    if phase == 4 and ctrl.status.value == 'ready' and len(calls)>=5:
        checkpoints.append({'phase':'resumed-ready', 'fen':g['state'].current_fen})
        phase = 5
        return [pygame.event.Event(pygame.QUIT)]
    return []

with patch.object(sys,'argv',['main.py','--physical','--no-viewer','--log-dir',str(ROOT/'reports/reliability-fixes-20261012/session-gui-logs')]), \
     patch.object(config,'SIMULATION_TOKEN','mock-token'), \
     patch.object(config,'SIMULATION_API_URL','https://unused.test'), \
     patch.object(config,'DEBUG_DASHBOARD',False,create=True), \
     patch.object(config,'AUTO_MOVE_CONFIRM_ENABLED',False), \
     patch('src.api.simulation_client.requests.post',post), \
     patch('src.core.session_startup.build_session',lambda *a:(hw,Mock(),None,None)), \
     patch.object(BoardRenderer,'home_action_from_pixel',lambda *a:'self_play'), \
     patch.object(pygame.event,'get',events), \
     patch.object(atexit,'register',lambda cb:callbacks.append(cb)):
    try:
        app = runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
        assert phase == 5
        assert created == [1,2]
        assert [u for u,p in calls] == ['simulation/matches','simulation/matches/1/fen',
            'simulation/matches/1/end','simulation/matches','simulation/matches/2/fen']
        assert calls[1][1] == calls[4][1]
        hw.execute_piece_move.assert_not_called()
        assert app['state'].move_history == []
    finally:
        for cb in reversed(callbacks): cb()
        hw.motion_worker.close()
        pygame.quit()

(ROOT/'reports/reliability-fixes-20261012/session-gui-evidence.json').write_text(
    json.dumps({'status':'PASS','scope':'headless Pygame event routing with mocked camera/robot/HTTP',
                'checkpoints':checkpoints,'api_calls':calls,'physical_commands':0},ensure_ascii=False,indent=2), encoding='utf-8')
print('PASS: real main.py routed startup -> F8 stop -> F6 resume; 2 rooms, equal FEN, 0 robot commands')
