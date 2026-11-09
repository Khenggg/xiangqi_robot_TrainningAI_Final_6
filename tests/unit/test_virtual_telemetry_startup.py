"""Owned loopback listeners exercise startup without SDK, camera or robot use."""
import errno
from contextlib import ExitStack
import json
import socket
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen
from unittest.mock import Mock

import pytest
from websockets.sync.client import connect

from src.core import session_startup
from src.hardware.backends.base import RobotStateSnapshot
from src.hardware.telemetry_publisher import TelemetryPublisher


@pytest.fixture
def startup_environment(tmp_path, monkeypatch):
    """Keep the real publisher/HTTP viewer, replace device and journal owners."""
    (tmp_path / "robot-3d-viewer").mkdir()
    (tmp_path / "robot-3d-viewer/index.html").write_text("viewer", encoding="utf-8")
    browser = Mock()
    monkeypatch.setattr("src.core.launch_options.webbrowser.open", browser)
    monkeypatch.setattr(session_startup.launch_options, "check_viewer_assets", Mock())
    created = []

    class Manager:
        def __init__(self, config, root):
            self.profile = config.SESSION_PROFILE
            self.simulation_error = None
            self.backend = SimpleNamespace(telemetry_publisher=None)
            self.simulation_runtime = (SimpleNamespace(telemetry=None, backend=self.backend)
                                       if self.profile.execution_environment == "VIRTUAL" else None)
            self.telemetry = None
            self.bridge = None
            self.cleanup = Mock()
            self.command_handler = Mock()
            created.append(self)

        def initialize_all(self):
            return self

        def viewer_command_context(self):
            return None

        def setup_digital_twin(self, telemetry):
            self.telemetry = telemetry
            self.backend.telemetry_publisher = telemetry
            if self.simulation_runtime is not None:
                self.simulation_runtime.telemetry = telemetry
            self.bridge = SimpleNamespace(telemetry=telemetry, board_sync_available=True)
            telemetry.source = self.profile.execution_environment
            telemetry.simulation_profile = {"name": "detailed", "speed_factor": .2}
            telemetry.register_command_handler(self.command_handler)
            telemetry.broadcast_custom({"type": "board_placement", "placement_version": 9,
                                        "marker": "owned-new-session"})
            telemetry.update_world_state({"type": "world_state", "pieces": [], "marker": "owned-world"})
            telemetry.update_from_snapshot(snapshot([1., -45., 90., -45., -90., 0.]))
            return self.bridge

        def sync_committed_board(self, cells):
            return True

    monkeypatch.setattr(session_startup, "HardwareManager", Manager)
    state = SimpleNamespace(set_board_observer=Mock(), sync_current_board=Mock(return_value=True),
                            start_projection_worker=Mock(), close_projection_worker=Mock(),
                            api_client=SimpleNamespace(close=Mock()))
    options = SimpleNamespace(no_viewer=False, viewer_port=0, simulation_profile=None, log_dir="logs")
    return tmp_path, state, options, created, browser


def snapshot(joints):
    return RobotStateSnapshot("FR3", True, "IDLE", joints, [0.] * 6,
                              [0.] * 6, False, time.time(), flange_pose_source="MOCK")


def config(port):
    return SimpleNamespace(GAME_MODE="HUMAN_VS_ROBOT", ROBOT_BACKEND="VIRTUAL",
                           DRY_RUN=True, GAME_ONLY=False,
                           TELEMETRY_HOST="127.0.0.1", TELEMETRY_PORT=port)


@pytest.mark.parametrize("viewer_busy", [False, True])
def test_busy_virtual_port_gets_owned_live_stream_and_actual_viewer_url(startup_environment, monkeypatch, viewer_busy):
    root, state, options, created, browser = startup_environment
    server_threads = []

    class ObservedPublisher(TelemetryPublisher):
        def start(self):
            try:
                return super().start()
            finally:
                server_threads.append(self._server_thread)

    monkeypatch.setattr(session_startup, "TelemetryPublisher", ObservedPublisher)
    with ExitStack() as owners:
        occupied = owners.enter_context(socket.socket())
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        requested_port = occupied.getsockname()[1]
        if viewer_busy:
            occupied_http = owners.enter_context(socket.socket())
            occupied_http.bind(("127.0.0.1", 0))
            occupied_http.listen(1)
            options.viewer_port = occupied_http.getsockname()[1]
        hw = telemetry = viewer = None
        try:
            hw, telemetry, viewer, reason = session_startup.build_session(
                config(requested_port), options, root, state, mode="SIMULATION")
            assert telemetry is not None, "A virtual game must retain its live arm stream"
            assert telemetry.port not in (0, requested_port)
            assert hw.telemetry is telemetry and hw.bridge.telemetry is telemetry
            assert hw.backend.telemetry_publisher is telemetry
            assert hw.simulation_runtime.telemetry is telemetry
            assert telemetry._command_handlers == [hw.command_handler]
            assert len(server_threads) == 2 and server_threads[0] is not server_threads[1]
            assert not server_threads[0].is_alive()
            assert reason is None
            assert len(created) == 1
            launched = parse_qs(urlsplit(browser.call_args.args[0]).query)
            launched_url = urlsplit(browser.call_args.args[0])
            assert launched_url.port == viewer.server.server_port
            if viewer_busy:
                assert launched_url.port != options.viewer_port
                assert occupied_http.getsockname()[1] == options.viewer_port
            with urlopen(browser.call_args.args[0], timeout=2) as page:
                assert page.read() == b"viewer"
            assert launched["ws"] == [f"ws://127.0.0.1:{telemetry.port}"]
            assert launched["autoconnect"] == ["1"]
            # The existing listener is still owned by this test; it was never reused.
            assert occupied.getsockname()[1] == requested_port
            with connect(launched["ws"][0], open_timeout=2) as ws:
                initial = [json.loads(ws.recv(timeout=2)) for _ in range(3)]
                robot = next(packet for packet in initial if packet["type"] == "robot_state")
                assert robot["joints"][0] == 1. and robot["source"] == "VIRTUAL"
                assert robot["simulation_profile"]["name"] == "detailed"
                assert any(packet.get("marker") == "owned-new-session" for packet in initial)
                assert any(packet.get("marker") == "owned-world" for packet in initial)
                telemetry.update_from_snapshot(snapshot([9., -45., 90., -45., -90., 0.]))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    packet = json.loads(ws.recv(timeout=2))
                    if packet.get("type") == "robot_state" and packet["joints"][0] == 9.:
                        break
                else:
                    pytest.fail("Fallback stream did not publish new authoritative joints")
        finally:
            if hw is not None:
                port = telemetry.port if telemetry is not None else None
                session_startup.rollback_session(hw, telemetry, viewer, state)
                if telemetry is not None:
                    assert not telemetry._server_thread.is_alive()
                    assert not telemetry._heartbeat_thread.is_alive()
                    with socket.socket() as released:
                        released.bind(("127.0.0.1", port))


def test_busy_physical_port_preserves_unavailable_stream_policy(startup_environment):
    root, state, options, created, browser = startup_environment
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        hw, telemetry, viewer, reason = session_startup.build_session(
            config(occupied.getsockname()[1]), options, root, state, mode="PHYSICAL")
        try:
            assert telemetry is None and "WebSocket unavailable" in reason
            assert hw.backend.telemetry_publisher is not None  # Existing physical mirror policy.
            assert hw.bridge.telemetry is None and hw.telemetry is None
            assert parse_qs(urlsplit(browser.call_args.args[0]).query)["autoconnect"] == ["0"]
        finally:
            session_startup.rollback_session(hw, telemetry, viewer, state)


@pytest.mark.parametrize("cause", [None, OSError(errno.EACCES, "permission denied")])
def test_non_binding_failure_does_not_retry_arbitrary_virtual_errors(startup_environment, monkeypatch, cause):
    root, state, options, created, browser = startup_environment
    error = RuntimeError("WebSocket dependency unavailable")
    error.__cause__ = cause
    start = Mock(side_effect=error)
    monkeypatch.setattr(TelemetryPublisher, "start", start)
    hw, telemetry, viewer, reason = session_startup.build_session(
        config(8765), options, root, state, mode="SIMULATION")
    try:
        assert telemetry is None and "dependency unavailable" in reason
        assert start.call_count == 1
    finally:
        session_startup.rollback_session(hw, telemetry, viewer, state)


def test_failed_ephemeral_retry_rolls_back_instead_of_returning_static_virtual_scene(startup_environment, monkeypatch):
    root, state, options, created, browser = startup_environment
    conflict = RuntimeError("requested address busy")
    conflict.__cause__ = OSError(errno.EADDRINUSE, "owned test address busy")
    start = Mock(side_effect=[conflict, RuntimeError("ephemeral bind failed")])
    stop = Mock()
    monkeypatch.setattr(TelemetryPublisher, "start", start)
    monkeypatch.setattr(TelemetryPublisher, "stop", stop)
    with pytest.raises(RuntimeError, match="ephemeral bind failed"):
        session_startup.build_session(config(8765), options, root, state, mode="SIMULATION")
    assert start.call_count == 2 and stop.call_count == 2
    created[0].cleanup.assert_called_once()
    state.close_projection_worker.assert_called_once()
    state.api_client.close.assert_called_once()
    browser.assert_not_called()
