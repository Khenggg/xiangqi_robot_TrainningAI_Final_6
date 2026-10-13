"""HTTP startup boundary: exercise the actual server under bad OS MIME mappings."""
import mimetypes
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from src.core.launch_options import ViewerServer, check_viewer_assets


def test_modules_ignore_non_javascript_windows_mime_mapping(tmp_path, monkeypatch):
    mimetypes.init()
    monkeypatch.setitem(mimetypes.types_map, ".mjs", "application/octet-stream")
    monkeypatch.setitem(mimetypes.types_map, ".js", "text/plain")
    for name in ("robot-3d-viewer/main.mjs", "robot-3d-viewer/live_state.mjs",
                 "node_modules/three/build/three.module.js"):
        asset = tmp_path / name
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text("export {};", encoding="utf-8")
    server = ViewerServer(tmp_path, 0)
    server.thread.start()
    origin = server.url.removesuffix("robot-3d-viewer/")
    try:
        for path in ("robot-3d-viewer/main.mjs", "robot-3d-viewer/live_state.mjs?reload=1",
                     "vendor/three/build/three.module.js"):
            with urlopen(origin + path, timeout=3) as response:
                assert response.status == 200
                assert response.headers.get_content_type() == "text/javascript"
                assert response.headers["Cache-Control"] == "no-cache"
                assert response.read() == b"export {};"
        with pytest.raises(HTTPError) as error:
            urlopen(origin + "robot-3d-viewer/missing.mjs", timeout=3)
        assert error.value.code == 404
    finally:
        server.close()


def test_missing_three_has_actionable_setup_error(tmp_path):
    viewer = tmp_path / "robot-3d-viewer"
    viewer.mkdir()
    for name in ("index.html", "main.mjs"):
        (viewer / name).write_text("viewer")
    with pytest.raises(FileNotFoundError, match="npm ci") as error:
        check_viewer_assets(tmp_path)
    assert "node_modules/three/build/three.module.js" in str(error.value)


def test_complete_viewer_assets_pass_without_opening_devices(tmp_path):
    for name in ("robot-3d-viewer/index.html", "robot-3d-viewer/main.mjs",
                 "node_modules/three/build/three.module.js", "node_modules/three/build/three.core.js",
                 "node_modules/three/examples/jsm/controls/OrbitControls.js",
                 "node_modules/three/examples/jsm/loaders/STLLoader.js"):
        asset = tmp_path / name
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text("asset")
    before = set(threading.enumerate())
    check_viewer_assets(tmp_path)
    assert set(threading.enumerate()) == before
