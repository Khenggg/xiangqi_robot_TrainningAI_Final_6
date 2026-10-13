import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
import runpy
import inspect
import webbrowser
from urllib.request import urlopen
import pygame

root = 'D:/OJT/_simple_launch_sync_20261005'
sys.path.insert(0, root)
only_game = '--virtual' in sys.argv
sys.argv = [root + '/main.py', '--viewer-port', '8097', '--telemetry-port', '8897'] + (['--virtual'] if only_game else [])
webbrowser.open = lambda url: print('[SMOKE BROWSER]', url)
count = 0
passed = False

def events():
    global count, passed
    count += 1
    if count == 1:
        return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)]
    if count == 2:
        return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1)]
    app = inspect.currentframe().f_back.f_globals
    hw, state = app['hw'], app['state']
    assert hw.is_robot_ready
    assert state.allow_mouse_move and not hw.robot.physical_motion_authorized if hasattr(hw.robot, 'physical_motion_authorized') else state.allow_mouse_move
    assert state.process_human_move((4, 6), (4, 5), 'r_P') is True
    if only_game:
        assert hw.simulation_runtime is None and hw.cam_monitor is None
        assert app['viewer_server'] is None
        from src.core.ai_execution import execute_ai_move
        assert execute_ai_move(state, hw, ((0, 3), (0, 4)), dry_run=True)
    else:
        assert hw.twin_bridge._cells == state.piece_ids
        viewer = app['viewer_server']
        for path in ('robot-3d-viewer/', 'shared/physical_geometry.json', 'robot-3d-viewer/assets/fr3_v6/Assieme_pinza_dita_parallele.stp'):
            with urlopen('http://127.0.0.1:8097/' + path) as response:
                assert response.status == 200
                assert response.read()
    print('[SMOKE PASS]', 'game-only' if only_game else 'simulation + viewer + piece sync')
    passed = True
    return [pygame.event.Event(pygame.QUIT)]

pygame.event.get = events
runpy.run_path(root + '/main.py', run_name='__main__')
assert passed, 'Startup smoke did not finish'
