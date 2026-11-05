"""App-local entrypoint. Standard library only until release validation succeeds."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import time
import traceback

REQUIRED = (
    'runtime/python.exe', 'runtime/python312.dll', 'runtime/python312.zip',
    'runtime/python312._pth', 'app/main.py', 'app/config.py',
    'runtime/python3.dll', 'runtime/msvcp140.dll', 'runtime/msvcp140_1.dll',
    'runtime/vcruntime140.dll', 'runtime/vcruntime140_1.dll',
    'app/moonfish/moonfish_ucci.py', 'app/models/best.pt',
    'app/models/cchess/pose_4_v6.onnx', 'app/models/cchess/layout_nano_v3.onnx',
    'app/calibration/physical_teaching_points_user0.json',
    'app/node_modules/three/build/three.module.js',
    'app/assets/fonts/NotoSerifCJKsc-Regular.otf',
)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Invalid release path: {relative}')
    return path


def verify_release(root, *, full=False):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest['files']
    for relative in REQUIRED:
        if relative not in files:
            raise RuntimeError(f'Capsule incomplete: manifest missing {relative}')
    checks = files.items() if full else ((name, files[name]) for name in REQUIRED)
    for relative, entry in checks:
        path = contained(root, relative)
        if not path.is_file() or path.stat().st_size != entry['size']:
            raise RuntimeError(f'Capsule missing/damaged: {relative}. Extract the complete ZIP again.')
        if full and sha256(path) != entry['sha256']:
            raise RuntimeError(f'Capsule checksum mismatch: {relative}. Extract the complete ZIP again.')
    return manifest


def read_settings(root):
    value = json.loads((root / 'settings.json').read_text(encoding='utf-8-sig'))
    if set(value) - {'mode', 'camera_index', 'robot_ip'}:
        raise ValueError('settings.json supports only mode, camera_index and robot_ip')
    if value.get('mode') not in {'SIMULATION', 'BOARD_ONLY', 'PHYSICAL'}:
        raise ValueError('mode must be SIMULATION, BOARD_ONLY or PHYSICAL')
    index = value.get('camera_index')
    if type(index) is not int or not 0 <= index <= 20:
        raise ValueError('camera_index must be an integer from 0 to 20')
    ipaddress.IPv4Address(value['robot_ip'])
    return value


def prepare_environment(root, settings):
    # Ignore developer-machine settings and credentials. No pip/npm or downloads.
    for key in list(os.environ):
        if key.startswith(('PYTHON', 'XIANGQI_')) or key in {
                'GAME_MODE', 'ROBOT_BACKEND', 'DRY_RUN', 'VIDEO_INDEX', 'VISION_DEVICE'}:
            os.environ.pop(key, None)
    state = root / 'state'
    state.mkdir(exist_ok=True)
    os.environ.update({
        'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
        'VISION_DEVICE': 'cpu', 'CUDA_VISIBLE_DEVICES': '-1',
        'YOLO_CONFIG_DIR': str(state / 'ultralytics'), 'YOLO_AUTOINSTALL': 'false',
        'YOLO_OFFLINE': 'true', 'MPLCONFIGDIR': str(state / 'matplotlib'),
        'HF_HUB_OFFLINE': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
        'VIDEO_INDEX': str(settings['camera_index']),
    })
    app = root / 'app'
    os.chdir(app)
    sys.path.insert(0, str(app))
    import config
    config.ENGINE_TYPE = 'LOCAL'
    config.SIMULATION_TOKEN = ''
    config.ROBOT_IP = settings['robot_ip']
    config.VIDEO_SOURCE = settings['camera_index']
    config.VISION_DEVICE = 'cpu'
    return config


@contextmanager
def offline_probe():
    """Prove checks need no Internet and cannot open camera/controller sockets."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def reject(*args, **kwargs):
        raise RuntimeError('Network access prohibited during capsule self-check')

    socket.socket.connect = reject
    socket.socket.connect_ex = reject
    try:
        yield
    finally:
        socket.socket.connect = original
        socket.socket.connect_ex = original_ex


def self_check(root, *, smoke=False):
    import importlib
    import importlib.metadata
    import platform
    if platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise RuntimeError('This capsule requires Windows x64')
    modules = ('numpy', 'cv2', 'pygame', 'requests', 'torch', 'torchvision',
               'ultralytics', 'onnxruntime', 'pybullet', 'websockets', 'PIL')
    with offline_probe():
        for name in modules:
            module = importlib.import_module(name)
            if not Path(module.__file__).resolve().is_relative_to(root / 'runtime'):
                raise RuntimeError(f'Non-portable import: {name}: {module.__file__}')
            print(f'[OK] {name}')
        from src.core.launch_options import check_viewer_assets
        check_viewer_assets(root / 'app')
        from src.ai.moonfish_engine import MoonfishEngine
        engine = MoonfishEngine(str(root / 'app/moonfish/moonfish_ucci.py'))
        try:
            engine.start()
            if not engine._ready:
                raise RuntimeError('Bundled Moonfish handshake failed')
        finally:
            engine.stop()
        print('[OK] local Moonfish subprocess')
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        for name in ('pose_4_v6.onnx', 'layout_nano_v3.onnx'):
            ort.InferenceSession(str(root / 'app/models/cchess' / name),
                                 sess_options=opts, providers=['CPUExecutionProvider'])
        print('[OK] both ONNX models / CPU')
        import numpy as np
        from ultralytics import YOLO
        model = YOLO(str(root / 'app/models/best.pt'))
        model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device='cpu', verbose=False)
        print('[OK] packaged YOLO weights / CPU inference')
        import pybullet as bullet
        client = bullet.connect(bullet.DIRECT)
        try:
            bullet.setGravity(0, 0, -9.81, physicsClientId=client)
            bullet.stepSimulation(physicsClientId=client)
        finally:
            bullet.disconnect(client)
        print('[OK] PyBullet DIRECT')
        if smoke:
            os.environ['SDL_VIDEODRIVER'] = 'dummy'
            os.environ['SDL_AUDIODRIVER'] = 'dummy'
            import pygame
            from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT
            pygame.init()
            try:
                screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
                renderer = BoardRenderer(screen)
                renderer.draw_home_screen()
                assert all(metric is not None for metric in renderer.piece_font.metrics('將帥馬車炮'))
                pygame.display.flip()
                pygame.image.save(screen, str(root / 'state/ui-smoke.png'))
            finally:
                pygame.quit()
            print('[OK] Pygame display/font/renderer initialization (headless)')


def main(argv=None, *, root=None):
    parser = argparse.ArgumentParser(description='Xiangqi portable capsule')
    parser.add_argument('--check', action='store_true', help='Full offline integrity/model check; no hardware')
    parser.add_argument('--smoke', action='store_true', help='Also initialize a headless Pygame renderer')
    args = parser.parse_args(argv)
    root = Path(root or Path(__file__).resolve().parent).resolve()
    sys.dont_write_bytecode = True
    try:
        if os.name != 'nt':
            raise RuntimeError('This release requires Windows 10/11 x64')
        # Isolated interpreter must be this capsule, never PATH Python.
        if Path(sys.executable).resolve() != root / 'runtime/python.exe':
            raise RuntimeError('Open START.bat; do not run this file with system Python')
        manifest = verify_release(root, full=args.check or args.smoke)
        settings = read_settings(root)
        prepare_environment(root, settings)
        print(f"Xiangqi capsule | {manifest['source']['head'][:12]} | CPU offline")
        if args.check or args.smoke:
            self_check(root, smoke=args.smoke)
            print('CAPSULE CHECK PASSED (no physical hardware accessed)')
            return 0
        option = {'SIMULATION': '--simulation', 'BOARD_ONLY': '--board-only', 'PHYSICAL': '--physical'}
        sys.argv = [str(root / 'app/main.py'), option[settings['mode']]]
        runpy.run_path(sys.argv[0], run_name='__main__')
        return 0
    except Exception:
        detail = traceback.format_exc()
        log = root / 'state' / f'launcher-error-{time.strftime("%Y%m%d-%H%M%S")}.log'
        try:
            log.parent.mkdir(exist_ok=True)
            log.write_text(detail, encoding='utf-8')
        except OSError:
            print('Cannot write logs. Extract capsule to a writable local folder.')
        print(detail)
        print(f'Cannot start capsule. See: {log}\nDo not run SETUP on the event PC; contact the team or extract the complete ZIP again.')
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
