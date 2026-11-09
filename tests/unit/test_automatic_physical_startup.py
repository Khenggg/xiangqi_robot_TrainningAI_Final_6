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


@pytest.mark.parametrize("flag", ["recovery_required", "mode_change_pending", "physical_sync_fault",
                                  "move_sync_error", "game_over", "pick_test_mode", "emergency_mode",
                                  "pending_move", "pending_ai_move", "pending_test_motion",
                                  "visual_capture_checkpoint", "visual_pick_retry"])
def test_fault_or_pending_motion_cancels_without_rearming(flag):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    setattr(state, flag, True)
    startup.tick()
    setattr(state, flag, None)
    startup.tick()
    hw.motion_worker.start.assert_not_called()
    assert startup.finished


@pytest.mark.parametrize("reason", ["stop", "stopped", "closing", "surrender", "virtual", "disabled", "dry", "manual"])
def test_no_automatic_enable_for_retired_or_ineligible_session(reason):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    if reason == "stop": hw.stop_coordinator.generation = 1
    if reason == "stopped": hw.stop_coordinator.blocked = True
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


@pytest.mark.parametrize("result,error", [(None, RuntimeError("camera mismatch")), (False, None)])
def test_failed_enable_is_reported_without_automatic_retry(result, error):
    startup, state, hw = setup_startup()
    startup.baseline_checked = True
    startup.tick()
    _, completed = hw.motion_worker.start.call_args.args
    completed(result, error)
    startup.tick()
    hw.motion_worker.start.assert_called_once()
    assert "F9/F10" in state.set_status.call_args.args[0]


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
