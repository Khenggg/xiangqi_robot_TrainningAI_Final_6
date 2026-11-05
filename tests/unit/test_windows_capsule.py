"""Portable release boundaries; never open hardware or network."""
import hashlib
import json
from pathlib import Path
import socket
import zipfile

import pytest

from tools.capsule import build, launcher


def release_fixture(root):
    files = {}
    for relative in launcher.REQUIRED:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'asset')
        files[relative] = {'size': 5, 'sha256': hashlib.sha256(b'asset').hexdigest()}
    (root / 'manifest.json').write_text(json.dumps({'files': files}))


def test_capsule_rejects_missing_runtime_before_start(tmp_path):
    release_fixture(tmp_path)
    (tmp_path / 'runtime/python312.dll').unlink()
    with pytest.raises(RuntimeError, match='missing/damaged'):
        launcher.verify_release(tmp_path)


def test_full_check_detects_same_size_corruption(tmp_path):
    release_fixture(tmp_path)
    (tmp_path / 'app/models/best.pt').write_bytes(b'wrong')
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        launcher.verify_release(tmp_path, full=True)


def test_manifest_cannot_escape_capsule(tmp_path):
    release_fixture(tmp_path)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    manifest['files']['../outside'] = {'size': 0, 'sha256': ''}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Invalid release path'):
        launcher.verify_release(tmp_path, full=True)


@pytest.mark.parametrize('change', [
    {'mode': 'AUTO_ENABLE'}, {'camera_index': True}, {'camera_index': -1},
    {'camera_index': 21}, {'robot_ip': 'example.com'}, {'skip_safety': True},
])
def test_settings_reject_invalid_or_actuation_fields(tmp_path, change):
    settings = {'mode': 'SIMULATION', 'camera_index': 2, 'robot_ip': '192.168.58.2'}
    settings.update(change)
    (tmp_path / 'settings.json').write_text(json.dumps(settings))
    with pytest.raises(ValueError):
        launcher.read_settings(tmp_path)


def test_mutable_session_files_do_not_invalidate_release(tmp_path):
    release_fixture(tmp_path)
    (tmp_path / 'app/data/runtime').mkdir(parents=True)
    journal = tmp_path / 'app/data/runtime/physical.sqlite3'
    journal.write_bytes(b'operator session must be retained')
    launcher.verify_release(tmp_path, full=True)
    assert journal.read_bytes() == b'operator session must be retained'


def test_source_allowlist_excludes_secrets_sessions_and_venvs(tmp_path, monkeypatch):
    names = ['src/core/game_state.py', 'main.py', 'config.py', 'assets/a.png',
             'calibration/physical_teaching_points_user0.json', '.env', 'data/runtime/a.sqlite3',
             '.venv312/pyvenv.cfg', 'logs/run.log', 'reports/x.md', 'SETUP_WINDOWS.bat']
    monkeypatch.setattr(build.subprocess, 'check_output', lambda *a, **k: '\0'.join(names).encode())
    assert set(build.tracked_source(tmp_path)) == set(names[:5])


def test_corrupt_download_cache_is_not_trusted(tmp_path, monkeypatch):
    asset = tmp_path / 'archive.zip'
    asset.write_bytes(b'bad')
    import io
    monkeypatch.setattr(build.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'good'))
    build.download('https://test.invalid/asset', asset, hashlib.sha256(b'good').hexdigest())
    assert asset.read_bytes() == b'good'


def test_valid_download_cache_skips_network(tmp_path, monkeypatch):
    asset = tmp_path / 'archive.zip'
    asset.write_bytes(b'good')
    def network_forbidden(*a, **k):
        raise AssertionError('cached asset must not be downloaded')
    monkeypatch.setattr(build.urllib.request, 'urlopen', network_forbidden)
    build.download('https://test.invalid/asset', asset, hashlib.sha256(b'good').hexdigest())


def test_zip_traversal_fails_before_extraction(tmp_path):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('../escape', b'bad')
    with pytest.raises(ValueError, match='Invalid release path'):
        build.extract_zip(archive, tmp_path / 'destination')
    assert not (tmp_path / 'escape').exists()


def test_offline_probe_blocks_and_restores_socket_connect():
    original = socket.socket.connect
    with launcher.offline_probe():
        with socket.socket() as client:
            with pytest.raises(RuntimeError, match='Network access prohibited'):
                client.connect(('127.0.0.1', 1))
    assert socket.socket.connect is original


def test_piece_font_uses_bundled_glyphs_when_available(monkeypatch):
    from src.ui import board_renderer
    monkeypatch.setattr(board_renderer.os.path, 'isfile', lambda path: path.endswith('NotoSerifCJKsc-Regular.otf'))
    seen = []
    monkeypatch.setattr(board_renderer.pygame.font, 'Font', lambda path, size: seen.append((path, size)))
    board_renderer.piece_symbol_font(38)
    assert seen[0][0].endswith('NotoSerifCJKsc-Regular.otf')


def test_piece_font_retains_developer_fallback(monkeypatch):
    from src.ui import board_renderer
    monkeypatch.setattr(board_renderer.os.path, 'isfile', lambda path: False)
    seen = []
    monkeypatch.setattr(board_renderer.pygame.font, 'SysFont', lambda name, size, **kw: seen.append((name, size)))
    board_renderer.piece_symbol_font(38)
    assert seen == [('simsun', 38)]


def test_moving_used_capsule_rebuilds_absolute_mesh_paths(tmp_path, monkeypatch):
    from src.simulation.physics import urdf_resolver
    import shutil
    first = tmp_path / 'first'
    mesh = first / 'robot-3d-viewer/assets/fr3_v6'
    mesh.mkdir(parents=True)
    (mesh / 'fairino3_v6.urdf').write_text(
        '<mesh filename="package://fairino_description/meshes/fairino3_v6/base.stl"/>')
    monkeypatch.setattr(urdf_resolver, '__file__', str(first / 'src/simulation/physics/urdf_resolver.py'))
    old = urdf_resolver.get_simulation_ready_fr3_urdf()
    assert first.as_posix() in old.read_text()
    second = tmp_path / 'copied capsule'
    shutil.copytree(first, second)
    monkeypatch.setattr(urdf_resolver, '__file__', str(second / 'src/simulation/physics/urdf_resolver.py'))
    current = urdf_resolver.get_simulation_ready_fr3_urdf()
    assert second.as_posix() in current.read_text()
    assert first.as_posix() not in current.read_text()


def test_windows_unicode_mesh_cache_contains_data_only(tmp_path, monkeypatch):
    from src.simulation.physics import urdf_resolver
    if urdf_resolver.os.name != 'nt':
        pytest.skip('Windows native-path behavior')
    assets = tmp_path / 'm\u00e1y s\u1ef1 ki\u1ec7n'
    assets.mkdir()
    (assets / 'base.stl').write_bytes(b'mesh')
    (assets / 'secret.env').write_bytes(b'excluded')
    (assets / 'robot.dll').write_bytes(b'excluded')
    monkeypatch.setattr(urdf_resolver, '_short_ascii_path', lambda value: None)
    monkeypatch.setattr(urdf_resolver.tempfile, 'gettempdir', lambda: str(tmp_path))
    result = urdf_resolver.native_mesh_directory(assets)
    assert str(result).isascii()
    assert (result / 'base.stl').read_bytes() == b'mesh'
    assert not (result / 'secret.env').exists() and not (result / 'robot.dll').exists()
    assert urdf_resolver.native_mesh_directory(assets) == result
