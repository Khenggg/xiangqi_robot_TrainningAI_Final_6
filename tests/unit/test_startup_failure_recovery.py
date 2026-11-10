"""Run the real GUI entrypoint with device startup failures and operator retries."""
import atexit
import os
from pathlib import Path
import runpy
import sys
import time
import json
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest
import config
from src.api.simulation_client import TuongKyDaiSuClient
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.ui.board_renderer import BoardRenderer


@pytest.mark.parametrize("component,reason", [
    ("ai", "Engine startup failed"),
    ("robot", "Controller startup failed"),
    ("camera", "Camera startup blocked: Cannot read camera index 1. Close Windows Camera."),
])
def test_failed_startup_keeps_gui_open_and_allows_explicit_retry(tmp_path, monkeypatch, component, reason, launcher_exit):
    # Register old values for restoration after configure_runtime changes them.
    for name in ("DRY_RUN", "ROBOT_BACKEND", "GAME_ONLY", "TELEMETRY_PORT", "GAME_MODE"):
        monkeypatch.setattr(config, name, getattr(config, name, None), raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--physical", "--log-dir", str(tmp_path / "logs")])
    monkeypatch.setattr(sys, "path", list(sys.path))
    callbacks = []
    monkeypatch.setattr(atexit, "register", lambda function, *args, **kwargs: callbacks.append(function))
    for name in ("ai", "robot", "camera"):
        monkeypatch.setattr(HardwareManager, "_init_" + name,
                            Mock(side_effect=RuntimeError(reason) if name == component else None))
    cleanup = Mock()
    monkeypatch.setattr(HardwareManager, "cleanup", cleanup)
    connect = Mock(side_effect=AssertionError("No physical connection in this test"))
    monkeypatch.setattr(FR5Robot, "connect", connect)
    monkeypatch.setattr(TuongKyDaiSuClient, "end_match", Mock())
    messages = []
    attempts = [0]
    deadline = time.monotonic() + 5
    def events():
        assert time.monotonic() < deadline, 'Startup did not become recoverable'
        displayed_error = messages and reason in messages[-1]
        if attempts[0] == 0 or (attempts[0] < 2 and displayed_error and cleanup.call_count == attempts[0]):
            attempts[0] += 1
            return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)]
        if attempts[0] == 2 and cleanup.call_count == 2 and displayed_error:
            return [pygame.event.Event(pygame.QUIT)]
        return []
    monkeypatch.setattr(pygame.event, 'get', events)
    original = BoardRenderer.draw_home_screen

    def draw_home(self, message=""):
        messages.append(message)
        return original(self, message)

    monkeypatch.setattr(BoardRenderer, "draw_home_screen", draw_home)
    try:
        app = runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
        assert app["home_screen_active"] and not app["difficulty_menu_active"]
        assert app["hw"] is None and app["telemetry"] is None and app["viewer_server"] is None
        assert len(messages) >= 3 and sum(reason in message for message in messages) >= 2
        assert "STARTUP_FAILED" in app["startup_message"]
        assert cleanup.call_count == 2  # Both failed attempts release partial startup.
        connect.assert_not_called()
        pygame.image.save(app["screen"], str(tmp_path / "startup-error.png"))
    finally:
        for callback in reversed(callbacks):
            callback()
        pygame.quit()
    records = list((tmp_path / "logs").glob("*/run.log"))
    assert len(records) == 1
    log = records[0].read_text(encoding="utf-8")
    assert "APP_UNHANDLED" not in log
    events_path = records[0].with_name('events.jsonl')
    events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()]
    assert sum(record['event'] == 'startup.blocked' for record in events) == 2

