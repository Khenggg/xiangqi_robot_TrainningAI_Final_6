"""F2 teardown and reconnect regressions; no native windows, camera, or SDK."""
import ast
import logging
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
from xmlrpc.client import Fault

import pytest
import config
from src.core.motion_worker import MotionWorker
from src.hardware import robot_VIP
from src.hardware.hardware_manager import HardwareManager
from src.vision.camera_monitor import CameraMonitor


def mixed_frame_robot(monkeypatch):
    points = {name: [x, y, 220., 180., 0., 0.] + [0.] * 6 + [0, user]
              for name, x, y, user in [('R1', -200., 500., 1), ('R2', -200., 180., 1),
                                        ('R3', 160., 180., 1), ('R4', 160., 500., 0)]}
    sdk = SimpleNamespace(SDK_state=True,
        GetRobotTeachingPoint=Mock(side_effect=lambda name: (0, points[name]) if name in points else (1, None)),
        GetWObjCoordWithID=Mock(return_value=(0, [0.] * 6)),
        GetActualWObjNum=Mock(return_value=(0, 0)), GetCurWObjCoord=Mock(return_value=(0, [0.] * 6)),
        Mode=Mock(return_value=0), RobotEnable=Mock(return_value=0),
        MoveCart=Mock(), MoveJ=Mock(), SetToolDO=Mock())
    monkeypatch.setattr(config, 'ALLOW_IDENTITY_WOBJ_AS_BASE', True)
    monkeypatch.setattr(robot_VIP, 'robot_sdk_core', SimpleNamespace(RPC=Mock(return_value=sdk)))
    return robot_VIP.FR5Robot(dry_run=False), sdk, points


def test_restart_reads_taught_frame_by_id_when_controller_now_uses_base(monkeypatch):
    robot, sdk, points = mixed_frame_robot(monkeypatch)
    assert robot.connect()
    assert robot.teaching_points_error is None
    sdk.GetWObjCoordWithID.assert_called_once_with(1)
    sdk.GetCurWObjCoord.assert_not_called()
    assert robot.identity_wobj_id == 1 and robot.wobj_identity_as_base
    assert {p['user'] for p in robot.teaching_points.values()} == {0}
    assert {p[13] for p in points.values()} == {0, 1}  # Controller data is untouched.
    assert not robot.physical_motion_authorized
    assert robot.activate_physical_control(commissioned=True)
    sdk.RobotEnable.assert_called_once_with(1)  # Fake SDK only, no move/grip command.
    sdk.MoveCart.assert_not_called()
    sdk.MoveJ.assert_not_called()
    sdk.SetToolDO.assert_not_called()


@pytest.mark.parametrize('reply', [
    (0, [10., 0., 0., 0., 0., 0.]), (0, [float('nan')] * 6),
    (0, [0.] * 5), (1, None), (0, None),
])
def test_identity_of_active_base_never_proves_another_frame(monkeypatch, reply):
    robot, sdk, _ = mixed_frame_robot(monkeypatch)
    sdk.GetWObjCoordWithID.return_value = reply
    assert robot.connect()
    assert robot.teaching_points_error
    assert not robot.wobj_identity_as_base
    with pytest.raises(robot_VIP.RobotCommandError):
        robot.activate_physical_control(commissioned=True)
    sdk.RobotEnable.assert_not_called()


def test_reload_discards_identity_proof_from_previous_connection(monkeypatch):
    robot, sdk, points = mixed_frame_robot(monkeypatch)
    assert robot.connect() and robot.wobj_identity_as_base
    for data in points.values():
        data[13] = 0
    robot._load_teaching_points()
    assert not robot.wobj_identity_as_base and robot.identity_wobj_id is None
    with pytest.raises(robot_VIP.RobotCommandError, match='HOMECHESS'):
        robot._verify_waypoint_frame([0.] * 12 + [0, 1], 'HOMECHESS')


def test_old_firmware_missing_method_reads_selected_frame_without_changing_it(monkeypatch):
    robot, sdk, _ = mixed_frame_robot(monkeypatch)
    sdk.GetWObjCoordWithID.side_effect = Fault(-506, "Method 'GetWObjCoordWithID' not defined")
    sdk.GetActualWObjNum.return_value = (0, 1)
    assert robot.connect()
    assert robot.teaching_points_error is None and robot.wobj_identity_as_base
    sdk.GetCurWObjCoord.assert_called_once()
    assert sdk.GetActualWObjNum.call_count == 2
    sdk.Mode.assert_not_called()
    sdk.RobotEnable.assert_not_called()
    sdk.MoveCart.assert_not_called()
    sdk.SetToolDO.assert_not_called()


def test_old_firmware_enable_retry_refreshes_metadata_after_operator_selects_frame(monkeypatch):
    robot, sdk, _ = mixed_frame_robot(monkeypatch)
    sdk.GetWObjCoordWithID.side_effect = Fault(-506, "Method 'GetWObjCoordWithID' not defined")
    assert robot.connect()
    assert 'Select User/WObj 1' in robot.teaching_points_error
    sdk.RobotEnable.assert_not_called()
    sdk.GetCurWObjCoord.assert_not_called()  # User 0 is not proof of frame 1.
    sdk.GetActualWObjNum.return_value = (0, 1)  # Operator selection, no SDK write.
    manager = HardwareManager.__new__(HardwareManager)
    manager.config = SimpleNamespace(ROBOT_BACKEND='PHYSICAL')
    manager.robot, manager.dry_run, manager.stop_coordinator = robot, False, None
    manager.simulation_runtime = None
    manager.backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(),
        motion_state='IDLE', last_error=None))
    manager.profile = SimpleNamespace(physical_robot_enabled=True)
    manager._piece_move_lock = threading.Lock()
    manager.physical_telemetry_ready = Mock(return_value=True)
    manager.verify_physical_board = Mock(return_value=True)
    state = SimpleNamespace(ai_thinking=False, pending_move=None, physical_sync_fault=False,
        pending_test_motion=None, recovery_required=False, mode_change_pending=False,
        move_sync_error=None, board=[], sync_current_board=Mock(return_value=True))
    assert manager.activate_physical_game(state, commissioned=True)
    assert robot.teaching_points_error is None and robot.wobj_identity_as_base
    sdk.GetWObjCoordWithID.assert_called_once_with(1)  # Unsupported capability is remembered.
    robot_VIP.robot_sdk_core.RPC.assert_called_once()  # Same read-only SDK connection.
    sdk.RobotEnable.assert_called_once_with(1)
    manager.physical_telemetry_ready.assert_called_once_with(require_idle=True)
    sdk.MoveCart.assert_not_called()
    sdk.SetToolDO.assert_not_called()


@pytest.mark.parametrize('error', [Fault(-500, 'Controller error'), RuntimeError('reply unavailable')])
def test_real_frame_query_errors_never_use_unsupported_method_fallback(monkeypatch, error):
    robot, sdk, _ = mixed_frame_robot(monkeypatch)
    sdk.GetWObjCoordWithID.side_effect = error
    sdk.GetActualWObjNum.return_value = (0, 1)
    assert robot.connect()
    assert robot.teaching_points_error and not robot.wobj_identity_as_base
    sdk.GetCurWObjCoord.assert_not_called()
    sdk.RobotEnable.assert_not_called()


def test_legacy_fallback_rejects_frame_changed_while_reading(monkeypatch):
    robot, sdk, _ = mixed_frame_robot(monkeypatch)
    sdk.GetWObjCoordWithID.side_effect = Fault(-506, "Method 'GetWObjCoordWithID' not defined")
    sdk.GetActualWObjNum.side_effect = [(0, 1), (0, 0)]
    assert robot.connect()
    assert robot.teaching_points_error and not robot.wobj_identity_as_base
    sdk.RobotEnable.assert_not_called()


def camera_with_owned_window(monkeypatch):
    camera = CameraMonitor(SimpleNamespace(release=Mock()), device_preference='cpu')
    camera._display_thread_id = threading.get_ident()
    camera._display_open = True
    calls = []
    def destroy(name):
        calls.append(threading.get_ident())
        assert calls[-1] == camera._display_thread_id, 'HighGUI called outside its GUI owner'
    monkeypatch.setattr('src.vision.camera_monitor.cv2.destroyWindow', destroy)
    return camera, calls


def test_background_camera_stop_defers_native_window_close_to_gui(monkeypatch):
    camera, calls = camera_with_owned_window(monkeypatch)
    errors = []
    def stop():
        try:
            camera.stop()
        except Exception as exc:
            errors.append(exc)
    worker = threading.Thread(target=stop)
    worker.start()
    worker.join(1)
    assert not worker.is_alive() and not errors
    assert calls == []
    camera.cap.release.assert_called_once()
    camera.close_display()
    camera.close_display()
    assert calls == [threading.get_ident()]


def main_functions(*names):
    path = Path(__file__).resolve().parents[2] / 'main.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    selected = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in names]
    return compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec')


def test_actual_f2_disposal_returns_to_menu_with_gui_owned_window(monkeypatch):
    camera, native_calls = camera_with_owned_window(monkeypatch)
    worker = MotionWorker()
    state = SimpleNamespace(pending_move=None, pending_ai_move=None, pending_test_motion=None,
        visual_capture_checkpoint=None, pick_test_resume_required=False,
        game_over=False, set_status=Mock(), publish_match_end=Mock(),
        close_projection_worker=Mock(), close_journal=Mock(), api_client=SimpleNamespace(close=Mock()))
    hw = SimpleNamespace(cam_monitor=camera, dry_run=False,
        stop_coordinator=SimpleNamespace(safe_for_release=lambda **_: True), cleanup=camera.stop)
    namespace = dict(state=state, hw=hw, self_play=None, telemetry=None, viewer_server=None,
        debug_dashboard=None, mode_disposal=None, mode_switching=False, mode_switch_failed=False,
        startup_worker=worker, quit_requested=False, home_screen_active=False,
        threading=threading, logging=logging, log_event=Mock(),
        GameState=Mock(return_value=object()), pygame=SimpleNamespace(display=SimpleNamespace(set_caption=Mock())))
    exec(main_functions('_begin_mode_disposal', '_finish_mode_disposal'), namespace)
    try:
        namespace['_begin_mode_disposal']()
        deadline = time.monotonic() + 2
        while worker.busy and time.monotonic() < deadline:
            worker.poll()
            time.sleep(.005)
        assert namespace['home_screen_active']
        assert not namespace['mode_switching'] and not namespace['mode_switch_failed']
        assert namespace['hw'] is None
        assert native_calls == [threading.get_ident()]
        state.close_journal.assert_called_once_with(clean=True)
    finally:
        worker.close(2)


def test_automatic_enable_failure_is_reported_with_the_actual_reason():
    from src.core.automatic_physical_startup import AutomaticPhysicalStartup

    state = SimpleNamespace(set_status=Mock())
    hw = SimpleNamespace(
        config=SimpleNamespace(AUTO_ENABLE_PHYSICAL_ON_STARTUP=True),
        profile=SimpleNamespace(physical_robot_enabled=True), dry_run=False,
        stop_coordinator=SimpleNamespace(generation=0, blocked=False),
        session_control=SimpleNamespace(action=None), is_robot_ready=False,
        motion_worker=SimpleNamespace(busy=False, start=Mock(return_value=True)),
        activate_physical_game=Mock(return_value=True))
    startup = AutomaticPhysicalStartup(state, hw)
    startup.baseline_checked = True
    startup.tick()
    _, completed = hw.motion_worker.start.call_args.args
    error = RuntimeError('R1-R4 frame could not be verified')
    completed(None, error)
    assert str(error) in state.set_status.call_args.args[0]
    assert not startup.finished
