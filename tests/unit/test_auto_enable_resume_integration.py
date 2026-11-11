"""Real journal/camera-resume boundaries; every physical operation is mocked."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.automatic_physical_startup import AutomaticPhysicalStartup
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.ui.input_handler import InputHandler


RECOVERY_FLAGS = ('recovery_required', 'physical_sync_fault',
                  'manual_override_active', 'snapshot_continue_required')


@pytest.fixture
def restarted_session(monkeypatch, tmp_path):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',
                        lambda *args, **kwargs: Mock(room_id=None))
    previous = GameState()
    previous.attach_journal(tmp_path, 'PHYSICAL', 'HUMAN_VS_HUMAN_ROBOT', fresh_start=True)
    previous.recovery_required = previous.physical_sync_fault = True
    previous.persist_checkpoint('RECOVERY_REQUIRED')
    previous.close_journal()

    state = GameState()
    state.attach_journal(tmp_path, 'PHYSICAL', 'HUMAN_VS_HUMAN_ROBOT', fresh_start=True)
    assert all(getattr(state, flag) is True for flag in RECOVERY_FLAGS)
    worker = MotionWorker()
    hw = SimpleNamespace(
        profile=SimpleNamespace(physical_robot_enabled=True, game_mode='HUMAN_VS_HUMAN_ROBOT'),
        dry_run=False,
        config=SimpleNamespace(AUTO_ENABLE_PHYSICAL_ON_STARTUP=True, ROBOT_BACKEND='PHYSICAL'),
        motion_worker=worker, is_robot_ready=False, simulation_runtime=None,
        stop_coordinator=SimpleNamespace(blocked=False, generation=0, request=None,
                                         safe_for_release=Mock(return_value=True)),
        session_control=SimpleNamespace(action=None),
        robot=SimpleNamespace(_gripper_pulse_active=False),
        physical_telemetry_ready=Mock(return_value=True),
        yolo_detector=Mock(), cam_monitor=Mock(), board_reconciler=object(),
        verify_physical_board=Mock(return_value=True),
        capture_baseline_if_needed=Mock(return_value=True))

    def activate(candidate, *, commissioned, expected_stop_generation, startup_guard):
        assert candidate is state and commissioned is True
        assert not any(getattr(state, flag) for flag in RECOVERY_FLAGS)
        assert expected_stop_generation == hw.stop_coordinator.generation
        startup_guard()
        hw.is_robot_ready = True
        return True

    hw.activate_physical_game = Mock(side_effect=activate)
    startup = AutomaticPhysicalStartup(state, hw)
    startup.baseline_checked = True
    hw.automatic_startup = startup
    handler = InputHandler.__new__(InputHandler)
    handler.state, handler.hw = state, hw
    handler._board_stability_monitor = Mock()
    try:
        yield SimpleNamespace(state=state, hw=hw, startup=startup, handler=handler)
    finally:
        worker.close(timeout=2)
        worker.poll()
        state.close_journal()


def resume_camera(session):
    assert session.handler.resume_automatic_scanning() is True
    assert not any(getattr(session.state, flag) for flag in RECOVERY_FLAGS)


def settle(session):
    deadline = time.monotonic() + 2
    while session.hw.motion_worker.busy and time.monotonic() < deadline:
        session.hw.motion_worker.poll()
        time.sleep(.005)
    assert not session.hw.motion_worker.busy


def test_interrupted_journal_waits_then_actual_camera_resume_enables_exactly_once(restarted_session):
    session = restarted_session
    session.startup.tick()
    assert not session.startup.finished and not session.startup.cancelled
    session.hw.activate_physical_game.assert_not_called()
    resume_camera(session)
    session.startup.tick()
    settle(session)
    session.startup.tick()
    session.hw.activate_physical_game.assert_called_once()
    assert session.startup.finished and session.hw.is_robot_ready


def test_failed_camera_identity_verification_keeps_enable_waiting(restarted_session):
    session = restarted_session
    session.startup.tick()
    session.hw.verify_physical_board.return_value = False
    assert session.handler.resume_automatic_scanning() is False
    for _ in range(3):
        session.startup.tick()
    session.hw.activate_physical_game.assert_not_called()
    assert session.state.recovery_required and session.state.physical_sync_fault


def test_resume_checkpoint_failure_never_enables(restarted_session, monkeypatch):
    session = restarted_session
    session.startup.tick()
    persist = session.state.persist_checkpoint

    def fail_resume(phase):
        if phase == 'OPERATOR_RESUMED_ROBOT_PVP_CAMERA':
            raise OSError('Synthetic storage failure')
        return persist(phase)

    monkeypatch.setattr(session.state, 'persist_checkpoint', fail_resume)
    assert session.handler.resume_automatic_scanning() is False
    assert session.state.physical_sync_fault
    assert session.state.manual_override_active and session.state.snapshot_continue_required
    for _ in range(3):
        session.startup.tick()
    session.hw.activate_physical_game.assert_not_called()


def test_new_pending_move_after_camera_resume_never_enables(restarted_session):
    session = restarted_session
    resume_camera(session)
    session.state.pending_move = object()
    try:
        for _ in range(3):
            session.startup.tick()
        session.hw.activate_physical_game.assert_not_called()
    finally:
        session.state.pending_move = None


@pytest.mark.parametrize('completed', [False, True])
def test_new_unverified_stop_after_camera_resume_never_enables(restarted_session, completed):
    session = restarted_session
    resume_camera(session)
    done = threading.Event()
    if completed:
        done.set()
    stop = session.hw.stop_coordinator
    stop.generation = 1
    stop.blocked = not completed  # Current user contract: done does not mean verified.
    stop.request = SimpleNamespace(done=done, result=SimpleNamespace(safe=False, acknowledged=False))
    stop.safe_for_release.return_value = False
    for _ in range(3):
        session.startup.tick()
    settle(session)
    session.hw.activate_physical_game.assert_not_called()


@pytest.mark.parametrize('flag', ['mode_change_pending', 'game_over'])
def test_terminal_session_cancellation_does_not_rearm_after_flag_clears(restarted_session, flag):
    session = restarted_session
    resume_camera(session)
    setattr(session.state, flag, True)
    session.startup.tick()
    assert session.startup.finished and session.startup.cancelled
    setattr(session.state, flag, False)
    session.startup.tick()
    session.hw.activate_physical_game.assert_not_called()
