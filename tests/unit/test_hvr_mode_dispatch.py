"""Exercise the real launcher dispatch without booting SDL or any device."""
import ast
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock
import sys

import pytest


@pytest.mark.parametrize('mode', ['HUMAN_VS_ROBOT', 'HUMAN_VS_HUMAN_ROBOT'])
def test_only_hvr_dispatches_to_scoped_donor_runtime(monkeypatch, mode):
    from src.core import session_startup
    module = ModuleType('src.modes.vsc_v3_session')
    session = SimpleNamespace(initialize=Mock())
    module.VscV3Session = Mock(return_value=session)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    build = Mock()
    monkeypatch.setattr(session_startup, 'build_session', build)
    config = SimpleNamespace(GAME_MODE=mode, RECALIBRATE_CAMERA=False, CAMERA_CALIBRATION_MANUAL_ONLY=False)
    worker = SimpleNamespace(start=Mock(return_value=True))
    namespace = dict(config=config, startup_worker=worker, launch_options=object(),
                     _BASE_DIR='test-root', state=object(), startup_cancelled=object(),
                     _finish_startup=Mock(), _finish_vsc_startup=Mock(), log_event=Mock(),
                     vsc_retained_session=None)
    source = ast.parse((Path(__file__).resolve().parents[2] / 'main.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == '_launch_session_mode')
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), namespace)
    before = vars(config).copy()
    assert namespace['_launch_session_mode']('PHYSICAL')
    operation, callback = worker.start.call_args.args
    operation()
    assert vars(config) == before
    if mode == 'HUMAN_VS_ROBOT':
        module.VscV3Session.assert_called_once()
        session.initialize.assert_called_once()
        build.assert_not_called()
        assert callback is namespace['_finish_vsc_startup']
    else:
        module.VscV3Session.assert_not_called()
        build.assert_called_once()
        assert callback is namespace['_finish_startup']


@pytest.mark.serial
def test_actual_menu_routes_hvr_to_private_loop_and_cleans_up(monkeypatch, tmp_path):
    import atexit
    import inspect
    import runpy
    import time
    import config
    import pygame
    from src.core import session_startup
    from src.modes import vsc_v3_session
    from src.ui.board_renderer import HOME_VS_ROBOT_RECT, SCREEN_WIDTH, SCREEN_HEIGHT
    from src.ui.game_window import fitted_rect
    for name, value in vars(config).copy().items():
        if name.isupper(): monkeypatch.setattr(config, name, value)
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER', 'dummy')
    monkeypatch.setattr(sys, 'argv', ['main.py', '--board-only', '--log-dir', str(tmp_path/'logs')])
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(atexit, 'register', lambda *args: None)
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *args: Mock(token=None, room_id=None))
    monkeypatch.setattr('src.ui.exit_confirmation.confirm_exit', lambda: True)
    monkeypatch.setattr('src.ui.exit_confirmation.exit_application', lambda: None)
    build = Mock(side_effect=AssertionError('HVR must not use shared build_session'))
    monkeypatch.setattr(session_startup, 'build_session', build)
    session = SimpleNamespace(activate=Mock(), draw=Mock(), tick=Mock(), close=Mock(),
                              wants_home=False, handle_event=Mock())
    session.initialize = Mock(return_value=session)
    factory = Mock(return_value=session)
    monkeypatch.setattr(vsc_v3_session, 'VscV3Session', factory)
    clicked = False
    deadline = time.monotonic() + 20
    def events():
        nonlocal clicked
        assert time.monotonic() < deadline, 'HVR menu dispatch did not finish'
        scope = inspect.currentframe().f_back.f_globals
        if scope.get('vsc_session') is session:
            return [pygame.event.Event(pygame.QUIT)]
        if not clicked and scope.get('home_screen_active') and not scope['startup_worker'].busy:
            clicked = True
            rect = fitted_rect((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.display.get_surface().get_size())
            x, y = HOME_VS_ROBOT_RECT.center
            return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(
                round(rect.x + x*rect.width/SCREEN_WIDTH), round(rect.y + y*rect.height/SCREEN_HEIGHT)))]
        return []
    monkeypatch.setattr(pygame.event, 'get', events)
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'), run_name='__main__')
    factory.assert_called_once()
    session.initialize.assert_called_once()
    session.activate.assert_called_once()
    session.draw.assert_called()
    session.close.assert_called_once()
    build.assert_not_called()


def test_retained_startup_owner_blocks_every_new_mode_until_close_succeeds():
    owner = SimpleNamespace(close=Mock())
    worker = SimpleNamespace(busy=False, start=Mock(return_value=True))
    namespace = dict(vsc_retained_session=None, startup_worker=worker,
                     config=SimpleNamespace(GAME_MODE='HUMAN_VS_HUMAN_ROBOT'),
                     log_event=Mock(), logging=SimpleNamespace(ERROR=40))
    source = ast.parse((Path(__file__).resolve().parents[2]/'main.py').read_text(encoding='utf-8-sig'))
    names = {'_retain_vsc_startup', '_retry_retained_vsc', '_launch_session_mode', '_retire_vsc_session'}
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'main.py', 'exec'), namespace)
    namespace['_retain_vsc_startup'](owner, RuntimeError('SDK still open'))
    assert namespace['vsc_retained_session'] is owner
    assert namespace['_launch_session_mode']('PHYSICAL')
    operation, callback = worker.start.call_args.args
    assert operation == owner.close
    callback(None, RuntimeError('close still failed'))
    assert namespace['vsc_retained_session'] is owner
    callback(None, None)
    assert namespace['vsc_retained_session'] is None
    namespace.update(vsc_session=owner, vsc_retiring=False)
    worker.start.reset_mock()
    namespace['_retire_vsc_session']()
    _, retiring_callback = worker.start.call_args.args
    retiring_callback(None, RuntimeError('close failed'))
    assert namespace['vsc_session'] is None
    assert namespace['vsc_retained_session'] is owner
    worker.start.assert_called_once()  # No automatic retry/game loop after partial close.
