"""CLI and local viewer lifecycle. Importing this module starts nothing."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser
import json
import logging
import time
from src.core.project_logging import event
from urllib.parse import unquote, urlsplit, urlencode


def parse_options(argv=None):
    parser = argparse.ArgumentParser(description="Xiangqi game and FR3 viewer")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--virtual", action="store_true", help="Disable simulation: game only, no hardware")
    modes.add_argument("--physical", action="store_true", help="Camera + real FR3, initially read-only")
    parser.add_argument("--no-viewer", action="store_true", help="Do not serve/open the 3D viewer")
    parser.add_argument("--viewer-port", type=int, default=8088)
    parser.add_argument("--telemetry-port", type=int, default=8765)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--log-dir", default="logs", help="Directory for per-session logs")
    args = parser.parse_args(argv)
    if any(not 1 <= p <= 65535 for p in (args.viewer_port, args.telemetry_port)):
        parser.error("Ports must be between 1 and 65535")
    if args.viewer_port == args.telemetry_port and not (args.virtual or args.no_viewer):
        parser.error("Viewer and telemetry require different ports")
    return args


def configure_runtime(config, options):
    config.GAME_ONLY = options.virtual
    config.ROBOT_BACKEND = "PHYSICAL" if options.physical else "VIRTUAL"
    config.DRY_RUN = not options.physical
    config.TELEMETRY_PORT = options.telemetry_port


def check_viewer_assets(repo):
    """Fail early with installation guidance for the local module graph."""
    root = Path(repo).resolve()
    required = (
        "robot-3d-viewer/index.html", "robot-3d-viewer/main.mjs",
        "node_modules/three/build/three.module.js",
        "node_modules/three/build/three.core.js",
        "node_modules/three/examples/jsm/controls/OrbitControls.js",
        "node_modules/three/examples/jsm/loaders/STLLoader.js",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Viewer thiếu tài nguyên: " + ", ".join(missing)
            + ". Chạy SETUP_WINDOWS.bat (hoặc npm ci tại thư mục repo); "
              "nếu thiếu index.html/main.mjs, kiểm tra lại checkout."
        )


class ViewerServer:
    def __init__(self, repo, port):
        root = Path(repo).resolve()
        three_root = (root / "node_modules" / "three").resolve()

        class Handler(SimpleHTTPRequestHandler):
            # Windows registry MIME associations may differ between machines.
            # ES modules require a JavaScript MIME type, including imported .js.
            extensions_map = {
                **SimpleHTTPRequestHandler.extensions_map,
                ".mjs": "text/javascript; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }

            def end_headers(self):
                # Local source changes must be revalidated on the next launch.
                # Otherwise the browser can keep an old module with new HTML.
                self.send_header("Cache-Control", "no-cache")
                super().end_headers()

            def translate_path(self, path):
                decoded = unquote(urlsplit(path).path)
                if decoded.startswith("/vendor/three/"):
                    return str((three_root / decoded.removeprefix("/vendor/three/")).resolve())
                return super().translate_path(path)

            def do_POST(self):
                if urlsplit(self.path).path != "/robot-3d-viewer/diagnostics":
                    self.send_error(404)
                    return
                expected_origin = f"http://127.0.0.1:{self.server.server_port}"
                if self.headers.get("Origin") not in (None, expected_origin):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 8192:
                        self.send_error(413)
                        return
                    self.connection.settimeout(2)
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise ValueError("Diagnostic must be an object")
                    with self.server.diagnostic_lock:
                        now = time.monotonic()
                        if now - self.server.diagnostic_window >= 60:
                            self.server.diagnostic_window, self.server.diagnostic_count = now, 0
                        self.server.diagnostic_count += 1
                        if self.server.diagnostic_count > 30:
                            self.send_error(429)
                            return
                    event("viewer.browser_error", str(data.get("message", "Lỗi viewer"))[:1000],
                          level=logging.ERROR, code="VIEWER_FAILED", source="browser",
                          browser_source=str(data.get("source", ""))[:500],
                          stack=str(data.get("stack", ""))[:4000])
                    self.send_response(204)
                    self.end_headers()
                except (ValueError, TimeoutError):
                    self.send_error(400)

            def send_head(self):
                target = Path(self.translate_path(self.path)).resolve()
                allowed = [root / "robot-3d-viewer", root / "shared"]
                if unquote(urlsplit(self.path).path).startswith("/vendor/three/"):
                    allowed = [three_root / "build", three_root / "examples" / "jsm"]
                    if target.suffix != ".js":
                        self.send_error(403)
                        return
                if not any(target.is_relative_to(folder) for folder in allowed):
                    self.send_error(403)
                    return
                return super().send_head()

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(root)))
        self.server.diagnostic_lock = threading.Lock()
        self.server.diagnostic_window = time.monotonic()
        self.server.diagnostic_count = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}/robot-3d-viewer/"

    def start(self, telemetry_port, unavailable_reason=None):
        self.thread.start()
        query = {"ws": f"ws://127.0.0.1:{telemetry_port}", "autoconnect": "1"}
        if unavailable_reason:
            query.update(autoconnect="0", mirror_error=str(unavailable_reason))
        url = f"{self.url}?{urlencode(query)}"
        print(f"[VIEWER] {url}")
        webbrowser.open(url)

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=2)
        self.server.server_close()
