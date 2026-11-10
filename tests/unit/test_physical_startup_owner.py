from unittest.mock import Mock

import pytest

from src.hardware.physical_startup import PhysicalStartupOwner, PhysicalStartupPolicy


def test_owner_runs_physical_stages_once_and_returns_typed_readiness():
    robot_handle, camera_handle = object(), object()
    robot = Mock(return_value=robot_handle)
    camera = Mock(return_value=camera_handle)
    calibration, board, baseline = Mock(return_value=True), Mock(return_value=True), Mock(return_value=True)
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))

    result = owner.start(telemetry=Mock(return_value=True), robot=robot, camera=camera, calibrate=calibration,
                         verify_board=board, capture_baseline=baseline,
                         enable_gate=Mock(return_value=True))

    assert result.robot_connected and result.camera_ready and result.calibration_ready
    assert result.board_verified and result.baseline_captured
    assert result.enable_ready
    assert result.blocked_reason is None
    robot.assert_called_once_with()
    camera.assert_called_once_with()
    calibration.assert_called_once_with(robot_handle, camera_handle)
    board.assert_called_once_with(robot_handle, camera_handle)
    baseline.assert_called_once_with(camera_handle)


def test_camera_failure_blocks_required_mode_and_closes_opened_robot():
    robot, camera, close = Mock(return_value="robot"), Mock(side_effect=RuntimeError("camera missing")), Mock()
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))

    result = owner.start(telemetry=Mock(return_value=True), robot=robot, camera=camera, close_resource=close,
                         calibrate=Mock(), verify_board=Mock(), capture_baseline=Mock())

    assert result.robot_connected
    assert not result.camera_ready
    assert result.blocked_reason == "camera missing"
    close.assert_called_once_with("robot")


def test_camera_optional_policy_can_complete_without_camera_but_cannot_enable():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=False))
    result = owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"),
                         camera=Mock(side_effect=RuntimeError("camera missing")),
                         calibrate=Mock(), verify_board=Mock(), capture_baseline=Mock())

    assert result.robot_connected and result.robot_telemetry_fresh
    assert not result.camera_ready and result.ready and not result.enable_ready
    assert result.blocked_reason is None


def test_camera_unavailable_is_fail_closed_even_if_policy_is_misconfigured_optional():
    camera, verify, baseline = Mock(side_effect=RuntimeError("camera missing")), Mock(), Mock()
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))

    result = owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"), camera=camera,
                         calibrate=Mock(), verify_board=verify, capture_baseline=baseline)

    assert result.robot_connected and not result.camera_ready
    assert not result.ready
    assert result.blocked_reason == "camera missing"
    verify.assert_not_called()
    baseline.assert_not_called()


def test_cleanup_failure_is_reported_in_readiness_instead_of_hidden():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    close = Mock(side_effect=RuntimeError("SDK still owns session"))

    result = owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"),
                         camera=Mock(side_effect=RuntimeError("camera missing")),
                         close_resource=close, calibrate=Mock(),
                         verify_board=Mock(), capture_baseline=Mock())

    assert "camera missing" in result.blocked_reason
    assert "cleanup failed: SDK still owns session" in result.blocked_reason
    close.assert_called_once_with("robot")
    assert owner.resources == [("robot", "robot")]


def test_owner_can_retry_cleanup_of_retained_resources():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    close = Mock(side_effect=[RuntimeError("busy"), None])

    owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"),
                camera=Mock(side_effect=RuntimeError("camera missing")),
                close_resource=close, calibrate=Mock(),
                verify_board=Mock(), capture_baseline=Mock())

    assert owner.resources == [("robot", "robot")]
    assert owner.cleanup(close_resource=close) is True
    assert owner.resources == []
    assert close.call_args_list == [(("robot",),), (("robot",),)]


def test_resource_owner_acquires_named_handle_once_and_closes_once():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    handle, factory, close = object(), Mock(return_value=None), Mock()
    factory.return_value = handle

    first = owner.acquire("camera", factory, close)
    second = owner.acquire("camera", factory, close)

    assert first is second is handle
    factory.assert_called_once_with()
    owner.cleanup()
    close.assert_called_once_with(handle)
    assert owner.resources == []


def test_resource_owner_closes_in_reverse_acquisition_order_and_retains_failed_handle():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    robot, camera = object(), object()
    closed = []

    owner.acquire("robot", Mock(return_value=robot), lambda handle: closed.append(handle))
    owner.acquire("camera", Mock(return_value=camera),
                  lambda handle: (_ for _ in ()).throw(RuntimeError("capture busy")))
    with pytest.raises(RuntimeError, match="capture busy"):
        owner.cleanup()

    assert closed == [robot]
    assert owner.resources == [("camera", camera)]


def test_hardware_manager_stops_reader_before_owner_releases_devices():
    from types import SimpleNamespace
    from src.hardware.hardware_manager import HardwareManager

    events = []
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    robot, capture = SimpleNamespace(connected=True, robot=object()), object()
    owner.acquire("robot", Mock(return_value=robot), lambda _: events.append("robot close"))
    owner.acquire("camera", Mock(return_value=capture), lambda _: events.append("camera release"))
    manager = HardwareManager.__new__(HardwareManager)
    manager._closing = False
    manager._calibration_capture_stop = manager._calibration_capture_thread = None
    manager.stop_coordinator = None
    manager.robot, manager.dry_run = robot, False
    manager.backend = manager.game_state = None
    manager.motion_worker = SimpleNamespace(running=False, close=lambda: events.append("worker stop"))
    manager._piece_move_lock = SimpleNamespace(locked=lambda: False)
    manager._cleanup_closed_steps = set()
    manager.pvp_controller = None
    manager.close_simulation = lambda: events.append("mirror stop")
    manager.cam_monitor = SimpleNamespace(stop=lambda: events.append("reader stop"))
    manager.cap = capture
    manager.ai_ctrl = manager.engine = None
    manager.physical_startup_owner = owner

    manager.cleanup()

    assert events.index("reader stop") < events.index("camera release") < events.index("robot close")


def test_startup_contract_has_no_enable_or_motion_callback():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    result = owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"), camera=Mock(return_value="camera"),
                         calibrate=Mock(return_value=True), verify_board=Mock(return_value=True),
                         capture_baseline=Mock(return_value=True),
                         enable_gate=Mock(return_value=True))

    assert result.ready
    assert result.enable_ready
    assert not hasattr(owner, "enable")


def test_telemetry_callback_is_mandatory_for_physical_readiness():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    result = owner.start(robot=Mock(return_value="robot"), camera=Mock(return_value="camera"),
                         calibrate=Mock(return_value=True), verify_board=Mock(return_value=True),
                         capture_baseline=Mock(return_value=True))

    assert result.failed_stage == "robot_telemetry"
    assert not result.ready
    assert "Fresh robot telemetry" in result.blocked_reason


def test_enable_gate_reports_authority_eligibility_without_actuating():
    gate = Mock(return_value=True)
    activate = Mock()
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    result = owner.start(telemetry=Mock(return_value=True), robot=Mock(return_value="robot"), camera=Mock(return_value="camera"),
                         calibrate=Mock(return_value=True),
                         verify_board=Mock(return_value=True), capture_baseline=Mock(return_value=True),
                         enable_gate=gate)

    assert result.ready and result.enable_ready
    gate.assert_called_once()
    activate.assert_not_called()


def test_owner_rejects_second_start_while_it_still_owns_resources():
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))
    robot, camera = Mock(return_value="robot"), Mock(return_value="camera")
    kwargs = dict(robot=robot, camera=camera, telemetry=Mock(return_value=True), calibrate=Mock(return_value=True),
                  verify_board=Mock(return_value=True), capture_baseline=Mock(return_value=True))
    assert owner.start(**kwargs).ready

    with pytest.raises(RuntimeError, match="already owns physical resources"):
        owner.start(**kwargs)
    robot.assert_called_once_with()
    camera.assert_called_once_with()


@pytest.mark.parametrize("failed_stage,expected", [
    ("robot_connect", "robot_connect"),
    ("camera_open", "camera_open"),
    ("camera_calibration", "camera_calibration"),
    ("board_verification", "board_verification"),
    ("baseline_capture", "baseline_capture"),
])
def test_failure_reports_exact_stage_and_rolls_back_acquired_handles(failed_stage, expected):
    robot_handle, camera_handle = object(), object()
    callbacks = {
        "robot_connect": Mock(return_value=robot_handle),
        "camera_open": Mock(return_value=camera_handle),
        "camera_calibration": Mock(return_value=True),
        "board_verification": Mock(return_value=True),
        "baseline_capture": Mock(return_value=True),
    }
    callbacks[failed_stage] = Mock(side_effect=RuntimeError(f"{failed_stage} failed"))
    close = Mock()
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))

    result = owner.start(telemetry=Mock(return_value=True), robot=callbacks["robot_connect"], camera=callbacks["camera_open"],
                         calibrate=callbacks["camera_calibration"],
                         verify_board=callbacks["board_verification"],
                         capture_baseline=callbacks["baseline_capture"], close_resource=close)

    assert result.failed_stage == expected
    assert not result.ready
    expected_closed = [] if expected == "robot_connect" else [robot_handle]
    if expected in ("camera_calibration", "board_verification", "baseline_capture"):
        expected_closed = [camera_handle, robot_handle]
    assert [call.args[0] for call in close.call_args_list] == expected_closed


def test_stale_robot_telemetry_blocks_startup_and_closes_resources():
    robot_handle, camera_handle = object(), object()
    close = Mock()
    owner = PhysicalStartupOwner(PhysicalStartupPolicy(camera_required=True))

    result = owner.start(telemetry=Mock(return_value=False), robot=Mock(return_value=robot_handle),
                         camera=Mock(return_value=camera_handle),
                         calibrate=Mock(return_value=True), verify_board=Mock(return_value=True),
                         capture_baseline=Mock(return_value=True), close_resource=close)

    assert result.failed_stage == "robot_telemetry"
    assert result.robot_connected and not result.ready
    assert [call.args[0] for call in close.call_args_list] == [robot_handle]
