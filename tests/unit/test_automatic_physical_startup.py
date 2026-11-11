from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.automatic_physical_startup import AutomaticPhysicalStartup


def setup_startup():
    state = SimpleNamespace(set_status=Mock())
    hardware = SimpleNamespace(
        config=SimpleNamespace(AUTO_ENABLE_PHYSICAL_ON_STARTUP=True),
        profile=SimpleNamespace(physical_robot_enabled=True), dry_run=False,
        stop_coordinator=SimpleNamespace(generation=0, blocked=False),
        session_control=SimpleNamespace(action=None), is_robot_ready=False,
        motion_worker=SimpleNamespace(busy=False, start=Mock(return_value=True)),
        activate_physical_game=Mock(return_value=True),
    )
    startup = AutomaticPhysicalStartup(state, hardware)
    return startup, state, hardware


def test_enable_waits_for_baseline_then_delegates_to_existing_checks_once():
    startup, state, hw = setup_startup()
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    startup.baseline_checked = True
    startup.tick()
    startup.tick()
    hw.motion_worker.start.assert_called_once()
    operation, completed = hw.motion_worker.start.call_args.args
    hw.activate_physical_game.assert_not_called()
    result = operation()
    hw.activate_physical_game.assert_called_once_with(
        state, commissioned=True, expected_stop_generation=0, startup_guard=startup.ensure_active)
    completed(result, None)
    assert startup.finished


@pytest.mark.parametrize("flag", ["snapshot_continue_required", "manual_override_active", "ai_thinking"])
def test_initial_board_pause_can_clear_before_single_attempt(flag):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    setattr(state, flag, True)
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    setattr(state, flag, False)
    startup.tick()
    hw.motion_worker.start.assert_called_once()


@pytest.mark.parametrize("flag", ["mode_change_pending", "game_over"])
def test_fault_or_pending_motion_cancels_without_rearming(flag):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    setattr(state, flag, True)
    startup.tick()
    setattr(state, flag, None)
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    assert startup.finished


@pytest.mark.parametrize("flag", ["recovery_required", "physical_sync_fault", "move_sync_error",
                                  "pick_test_mode", "pick_test_fault", "pick_test_resume_required",
                                  "emergency_mode", "pending_move", "pending_ai_move",
                                  "pending_test_motion", "visual_capture_checkpoint", "visual_pick_retry"])
def test_initial_recovery_waits_and_can_resume_after_verified_state_clear(flag):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    setattr(state, flag, True)
    startup.tick()
    assert not startup.finished and not startup.cancelled
    assert startup.last_wait_reason == flag
    hw.motion_worker.start.assert_not_called()
    setattr(state, flag, None)
    startup.tick()
    hw.motion_worker.start.assert_called_once()


def test_wait_reason_is_logged_once_until_the_prerequisite_changes(monkeypatch):
    events = Mock()
    monkeypatch.setattr('src.core.automatic_physical_startup.event', events)
    startup, state, hw = setup_startup()
    state.recovery_required = state.physical_sync_fault = True
    for _ in range(5):
        startup.tick()
    assert events.call_count == 1
    assert events.call_args.args[0] == 'physical.auto_enable_waiting'
    assert events.call_args.kwargs['reason'] == 'recovery_required'
    assert events.call_args.kwargs['waiting_flags'] == ['recovery_required', 'physical_sync_fault']
    state.recovery_required = False
    startup.tick()
    assert events.call_count == 2
    assert events.call_args.kwargs['reason'] == 'physical_sync_fault'


def test_completed_unverified_stop_is_not_auto_enabled_even_if_blocked_is_false():
    import threading
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    done = threading.Event()
    done.set()
    hw.stop_coordinator.request = SimpleNamespace(done=done, result=SimpleNamespace(safe=False))
    hw.stop_coordinator.safe_for_release = Mock(return_value=False)
    startup.tick()
    assert startup.last_wait_reason == 'stop_unverified'
    assert not startup.finished
    hw.motion_worker.start.assert_not_called()


def test_verified_stop_is_checked_again_by_scheduled_enable_guard():
    import threading
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    done = threading.Event()
    done.set()
    hw.stop_coordinator.request = SimpleNamespace(done=done, result=SimpleNamespace(safe=True))
    hw.stop_coordinator.safe_for_release = Mock(return_value=True)
    startup.tick()
    hw.stop_coordinator.safe_for_release.return_value = False
    with pytest.raises(RuntimeError, match='stop_evidence_incomplete'):
        startup.ensure_active()


def test_stop_generation_is_frozen_before_worker_dispatch():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    operation, _ = hw.motion_worker.start.call_args.args
    hw.stop_coordinator.generation = 1
    operation()
    assert hw.activate_physical_game.call_args.kwargs['expected_stop_generation'] == 0
    with pytest.raises(RuntimeError, match='newer stop'):
        startup.ensure_active()


def test_recovery_flag_set_after_submission_is_rechecked_before_enable():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    state.recovery_required = True
    with pytest.raises(RuntimeError, match='recovery_required'):
        startup.ensure_active()


def test_cancel_during_worker_is_terminal_after_its_error_callback():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    _, completed = hw.motion_worker.start.call_args.args
    startup.cancel()
    completed(None, RuntimeError('Automatic enable cancelled'))
    assert startup.finished and startup.cancelled
    startup.tick()
    hw.motion_worker.start.assert_called_once()


def test_cancelled_startup_cannot_be_revived_by_finished_flag_alone():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.cancel()
    startup.finished = False
    startup.tick()
    assert startup.finished
    hw.motion_worker.start.assert_not_called()


@pytest.mark.parametrize('kind', ['rpc', 'wrapped_rpc', 'socket'])
def test_unknown_enable_result_never_automatically_replays(kind):
    from src.hardware.rpc_transport import RpcOutcomeUnknown
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    _, completed = hw.motion_worker.start.call_args.args
    error = RpcOutcomeUnknown('Reply lost') if kind != 'socket' else OSError('Connection lost')
    if kind == 'wrapped_rpc':
        wrapped = RuntimeError('Enable failed')
        wrapped.__cause__ = error
        error = wrapped
    completed(None, error)
    startup.tick()
    assert startup.finished and startup.cancelled
    hw.motion_worker.start.assert_called_once()
    assert 'Automatic retry blocked' in state.set_status.call_args.args[0]


@pytest.mark.parametrize("reason", ["closing", "surrender", "virtual", "disabled", "dry", "manual"])
def test_no_automatic_enable_for_retired_or_ineligible_session(reason):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    if reason == "closing": hw._closing = True
    if reason == "surrender": hw.session_control.action = "surrender"
    if reason == "virtual": hw.profile.physical_robot_enabled = False
    if reason == "disabled": hw.config.AUTO_ENABLE_PHYSICAL_ON_STARTUP = False
    if reason == "dry": hw.dry_run = True
    if reason == "manual": startup.cancel()
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    assert startup.finished


def test_busy_or_rejected_worker_submission_does_not_consume_attempt():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    hw.motion_worker.busy = True
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    hw.motion_worker.busy = False
    hw.motion_worker.start.return_value = False
    startup.tick()
    assert not startup.finished
    hw.motion_worker.start.return_value = True
    startup.tick()
    assert startup.finished


def test_stop_in_progress_delays_the_attempt_instead_of_retiring_it():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    hw.stop_coordinator.blocked = True
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    assert not startup.finished
    hw.stop_coordinator.blocked = False
    hw.stop_coordinator.generation = 3
    startup.tick()
    hw.motion_worker.start.assert_called_once()
    operation, _ = hw.motion_worker.start.call_args.args
    operation()
    assert hw.activate_physical_game.call_args.kwargs["expected_stop_generation"] == 3


@pytest.mark.parametrize("result,error", [(None, RuntimeError("camera mismatch")), (False, None)])
def test_failed_enable_retries_instead_of_asking_for_a_key(result, error):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    _, completed = hw.motion_worker.start.call_args.args
    completed(result, error)
    assert not startup.finished
    assert "Retrying" in state.set_status.call_args.args[0]
    startup.tick()
    assert hw.motion_worker.start.call_count == 2


def test_failed_enable_stops_retrying_after_the_attempt_cap():
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    for _ in range(startup.MAX_ATTEMPTS):
        startup.finished = False
        startup.tick()
        _, completed = hw.motion_worker.start.call_args.args
        completed(False, None)
    assert startup.finished
    startup.tick()
    assert hw.motion_worker.start.call_count == startup.MAX_ATTEMPTS


@pytest.mark.parametrize("reason", ["stop", "cancel"])
def test_scheduled_enable_rechecks_stop_and_manual_cancel_before_activation(reason):
    from src.hardware.hardware_manager import HardwareManager
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    # Use the real entry gate; no controller, camera or SDK is needed to reject.
    hw.activate_physical_game = lambda *args, **kwargs: HardwareManager.activate_physical_game(hw, *args, **kwargs)
    startup.tick()
    operation, _ = hw.motion_worker.start.call_args.args
    if reason == "stop":
        hw.stop_coordinator.generation = 1
        hw.stop_coordinator.blocked = True
    else:
        startup.cancel()
    with pytest.raises(RuntimeError, match="cancelled"):
        operation()


@pytest.mark.parametrize("reason", ["stop", "cancel"])
def test_stop_or_cancel_during_board_verification_prevents_servo_enable(reason):
    from src.hardware.hardware_manager import HardwareManager
    startup, state, hw = setup_startup()
    for name in ("ai_thinking", "physical_sync_fault", "recovery_required", "mode_change_pending", "move_sync_error"):
        setattr(state, name, False)
    state.pending_move = state.pending_test_motion = None
    state.sync_current_board = Mock()
    state.board = [["."] * 9 for _ in range(10)]
    hw.config.ROBOT_BACKEND = "PHYSICAL"
    hw.robot = SimpleNamespace(connected=True, teaching_points_error=None, activate_physical_control=Mock())
    hw._piece_move_lock = SimpleNamespace(locked=lambda: False)
    hw.physical_telemetry_ready = lambda **kwargs: True

    def verify(board):
        if reason == "stop": hw.stop_coordinator.generation = 1
        else: startup.cancel()
        return True

    hw.verify_physical_board = verify
    with pytest.raises(RuntimeError, match="cancelled"):
        HardwareManager.activate_physical_game(
            hw, state, commissioned=True, expected_stop_generation=0, startup_guard=startup.ensure_active)
    hw.robot.activate_physical_control.assert_not_called()
