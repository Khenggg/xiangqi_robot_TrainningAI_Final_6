"""Exit bypasses hung general cleanup after any held gripper output is off."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.serial
def test_confirmation_available_after_partial_display_cleanup(monkeypatch):
    import pygame
    from src.ui import exit_confirmation
    pygame.quit()
    monkeypatch.setattr(exit_confirmation, "_confirm_without_window", lambda: True)
    assert exit_confirmation.confirm_exit() is True


@pytest.mark.serial
@pytest.mark.parametrize("key, expected", [(13, True), (121, True), (27, False), (110, False)])
def test_keyboard_confirmation(monkeypatch, key, expected):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import pygame
    from src.ui.exit_confirmation import confirm_exit
    pygame.init()
    pygame.display.set_mode((640, 360))
    try:
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
        assert confirm_exit() is expected
    finally:
        pygame.quit()


@pytest.mark.serial
@pytest.mark.parametrize("position, expected", [((230, 398), True), ((410, 398), False)])
def test_mouse_confirmation_after_window_close(monkeypatch, position, expected):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    import pygame
    from src.ui.exit_confirmation import confirm_exit
    pygame.init()
    pygame.display.set_mode((640, 720))
    try:
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position))
        assert confirm_exit() is expected
    finally:
        pygame.quit()


def test_confirmed_exit_bypasses_blocked_threads_and_cleanup_preserves_journal(tmp_path):
    journal = tmp_path / "unfinished-session.txt"
    journal.write_text("PREPARED; pending physical move", encoding="utf-8")
    cleanup_marker = tmp_path / "cleanup-was-run"
    script = """
import atexit, pathlib, sys, threading
from src.ui.exit_confirmation import exit_application
atexit.register(lambda: pathlib.Path(sys.argv[1]).write_text('must not run'))
threading.Thread(target=threading.Event().wait, daemon=False).start()
exit_application()
raise AssertionError('confirmed exit returned')
"""
    result = subprocess.run([sys.executable, "-c", script, str(cleanup_marker)],
                            cwd=Path(__file__).resolve().parents[2],
                            env=dict(os.environ, DRY_RUN="1", ROBOT_BACKEND="VIRTUAL"),
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    assert not cleanup_marker.exists()
    assert journal.read_text(encoding="utf-8") == "PREPARED; pending physical move"


def test_exit_turns_off_registered_holds_before_terminating(monkeypatch):
    from src.ui import exit_confirmation
    calls = []
    stop_holds = Mock(side_effect=lambda: calls.append('holds_off'))
    driver = SimpleNamespace(FR5Robot=SimpleNamespace(stop_all_gripper_holds=stop_holds))
    monkeypatch.setitem(sys.modules, 'src.hardware.robot_VIP', driver)
    terminate = Mock(side_effect=lambda code: calls.append(('exit', code)))
    monkeypatch.setattr(exit_confirmation.os, '_exit', terminate)
    exit_confirmation.exit_application()
    assert calls == ['holds_off', ('exit', 0)]
    stop_holds.assert_called_once_with()
    terminate.assert_called_once_with(0)


def test_exit_does_not_terminate_when_registered_hold_off_fails(monkeypatch):
    from src.ui import exit_confirmation
    stop_holds = Mock(side_effect=RuntimeError('Tool DO OFF outcome unknown'))
    driver = SimpleNamespace(FR5Robot=SimpleNamespace(stop_all_gripper_holds=stop_holds))
    monkeypatch.setitem(sys.modules, 'src.hardware.robot_VIP', driver)
    terminate = Mock()
    monkeypatch.setattr(exit_confirmation.os, '_exit', terminate)
    with pytest.raises(RuntimeError, match='Tool DO OFF outcome unknown'):
        exit_confirmation.exit_application()
    stop_holds.assert_called_once_with()
    terminate.assert_not_called()


def test_exit_without_loaded_driver_does_not_import_or_initialize_hardware(monkeypatch):
    import builtins
    from src.ui import exit_confirmation
    monkeypatch.delitem(sys.modules, 'src.hardware.robot_VIP', raising=False)
    original_import = builtins.__import__

    def prohibit_driver_import(name, *args, **kwargs):
        if name.endswith('robot_VIP'):
            raise AssertionError('Exit must not import a new physical driver')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', prohibit_driver_import)
    terminate = Mock()
    monkeypatch.setattr(exit_confirmation.os, '_exit', terminate)
    exit_confirmation.exit_application()
    terminate.assert_called_once_with(0)
