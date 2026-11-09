"""Developer-only offline acceptance; run with a relocated capsule's interpreter."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys
import urllib.request
import subprocess
import time
import queue


def check_packaged_black_client(root):
    """Real room + bundled child GUI, no executor/camera/controller ownership."""
    from src.core.pvp_room import LocalRoomHost
    from src.core import xiangqi
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    subprocess.run([sys.executable, '-B', '-m', 'src.ui.pvp_client', '--help'],
                   cwd=root / 'app', env=environment, check=True, timeout=15)
    child_code = '''
import sys,time,pygame
from src.ui.pvp_client import ClientApp
app=ClientApp(sys.argv[1])
try:
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.poll()
        if app.client.connected and app.model.snapshot:
            assert app.model.board[0][0]=='b_R'
            app.draw();pygame.display.flip()
            token=app.client.send_move((0,3),(0,4),app.model.snapshot['revision'],app.model.snapshot['epoch'])
            assert token
            time.sleep(.5)
            print('PACKAGED BLACK CLIENT HANDSHAKE/STATE/GUI/REQUEST PASS',flush=True)
            break
        time.sleep(.02)
    else:raise RuntimeError('Black client did not receive host board')
finally:
    if app.client:app.client.close()
    pygame.quit()
'''
    room = LocalRoomHost()
    child = None
    try:
        room.publish(dict(board=xiangqi.get_board(),turn='b',revision=0,epoch=1,
                          busy=False,blocked=None,game_over=False,winner=None,status='capsule acceptance'))
        child = subprocess.Popen([sys.executable, '-u', '-B', '-c', child_code, room.code],
                                 cwd=root / 'app', env=environment)
        deadline = time.monotonic() + 25
        request = None
        while time.monotonic() < deadline:
            try:
                message = room.events.get(timeout=.2)
            except queue.Empty:
                if child.poll() is not None:
                    break
                continue
            if message.get('type') == 'request':
                request = message['packet']
                break
        assert request and request['src'] == [0,3] and request['dst'] == [0,4], request
        assert request['session'] == room.session and request['revision'] == 0
        assert child.wait(timeout=10) == 0
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        room.close()
    print('[OK] actual packaged Black subprocess / localhost state and request', flush=True)


def main():
    root = Path(sys.argv[1]).resolve()
    assert Path(sys.executable).resolve() == root / 'runtime/python.exe'
    spec = importlib.util.spec_from_file_location('capsule_entry', root / 'launcher.py')
    capsule = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capsule)
    # The caller verifies ZIP SHA256 before extraction; builder already ran full
    # per-file hashing. Exercise the same fast preflight as an operator launch.
    capsule.verify_release(root)
    capsule.prepare_environment(root)
    capsule.self_check(root, smoke=True)
    results = {'isolated_preflight_and_models': True}
    with capsule.offline_probe():
        from src.core import xiangqi
        from src.ai.moonfish_engine import MoonfishEngine
        engine = MoonfishEngine(str(root / 'app/moonfish/moonfish_ucci.py'))
        try:
            engine.start()
            board = xiangqi.get_board()
            move = engine.pick_best_move(board, 'r', movetime_ms=200, depth=1)
            assert move in xiangqi.find_all_valid_moves('r', board), move
        finally:
            engine.stop()
        results['legal_local_engine_move'] = True
        from src.simulation.runtime import VirtualXiangqiSimulation
        simulation = VirtualXiangqiSimulation()
        try:
            assert len(simulation.world.pieces) == 32
        finally:
            simulation.stop()
        results['real_virtual_world_32_pieces'] = True

    # Bind only loopback; fetch real JS/WASM through the existing app server.
    from src.core.launch_options import ViewerServer
    viewer = ViewerServer(root / 'app', 0)
    viewer.thread.start()  # No webbrowser.open or telemetry/controller.
    try:
        base = f'http://127.0.0.1:{viewer.server.server_port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for path, mime in (
            ('/robot-3d-viewer/', 'text/html'),
            ('/vendor/three/build/three.module.js', 'javascript'),
            ('/robot-3d-viewer/vendor/occt-import-js/occt-import-js.wasm', 'application/wasm'),
        ):
            with opener.open(base + path, timeout=10) as response:
                assert response.status == 200 and mime in response.headers['Content-Type']
                assert response.read()  # Drain large WASM responses before closing the socket.
    finally:
        viewer.close()
    results['loopback_viewer_js_wasm'] = True
    check_packaged_black_client(root)
    results['packaged_black_subprocess_room_gui_request'] = True

    # Real application boot/menu/shutdown without a camera, robot or visible window.
    import pygame
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    os.environ['SDL_AUDIODRIVER'] = 'dummy'
    original_get = pygame.event.get
    from src.ui import exit_confirmation
    original_confirm = exit_confirmation.confirm_exit
    original_exit = exit_confirmation.exit_application
    # Exercise the current real dialog with Enter, but keep the probe process
    # alive to record evidence instead of calling the production os._exit.
    def record_confirmed_exit():
        raise SystemExit(0)
    exit_confirmation.exit_application = record_confirmed_exit
    frames = 0
    quit_sent = False

    def events(*args, **kwargs):
        nonlocal frames, quit_sent
        frames += 1
        if frames > 20:
            raise RuntimeError('Application did not close after QUIT')
        if frames >= 3:
            pygame.image.save(pygame.display.get_surface(), str(root / 'state/main-home-window.png'))
            if not quit_sent:
                quit_sent = True
                return [pygame.event.Event(pygame.QUIT)]
            return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)]
        return original_get(*args, **kwargs)

    pygame.event.get = events
    sys.argv = [str(root / 'app/main.py'), '--board-only', '--no-viewer']
    try:
        with capsule.offline_probe():
            try:
                runpy.run_path(sys.argv[0], run_name='__main__')
            except SystemExit as result:
                assert result.code in (None, 0), result.code
    finally:
        pygame.event.get = original_get
        exit_confirmation.confirm_exit = original_confirm
        exit_confirmation.exit_application = original_exit
    assert frames >= 3
    results['actual_app_menu_shutdown'] = True
    (root / 'state/acceptance.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('RELOCATED CAPSULE ACCEPTANCE PASSED', results, flush=True)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='replace')
    main()
