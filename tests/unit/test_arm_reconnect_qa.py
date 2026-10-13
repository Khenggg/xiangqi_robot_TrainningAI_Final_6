"""Failed startup -> recovered SDK -> measured arm, with zero actuation."""
import json
import socket
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.hardware import robot_VIP
from src.hardware.hardware_manager import HardwareManager
from src.hardware.simulation_adapter import BorrowedPhysicalStateSource


def packet(joints=None):
    return SimpleNamespace(jt_cur_pos=joints or [-89.465, -128.623, 106.877, -68.511, -89.496, 42.537],
        tl_cur_pos=[-104, 149, 348, 180, 0, -42], flange_cur_pos=[-104, 149, 348, 180, 0, -42],
        EmergencyStop=0, main_code=0, sub_code=0, motion_done=1)


def failed_manager(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DRY_RUN', False)
    sdk = SimpleNamespace(SDK_state=False, sock_cli_state_state=False, reconnect_flag=True,
                          robot_state_pkg=None)
    for name in ('Mode', 'RobotEnable', 'MoveJ', 'MoveL', 'MoveCart', 'SetToolDO', 'GetRobotTeachingPoint'):
        setattr(sdk, name, Mock(side_effect=AssertionError('Unexpected controller call: ' + name)))
    create = Mock(return_value=sdk)
    monkeypatch.setattr(robot_VIP, 'robot_sdk_core', SimpleNamespace(RPC=create))
    cfg = SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND='PHYSICAL', GAME_ONLY=False,
                          TELEMETRY_HOST='127.0.0.1', TELEMETRY_PORT=0)
    manager = HardwareManager(cfg, str(tmp_path))
    manager._init_robot()
    return manager, sdk, create


def recovered(sdk):
    sdk.SDK_state = True
    sdk.sock_cli_state_state = True
    sdk.reconnect_flag = False
    sdk.robot_state_pkg = packet()


def test_failed_startup_retains_raw_reader_without_granting_motion(monkeypatch, tmp_path):
    manager, sdk, create = failed_manager(monkeypatch, tmp_path)
    assert manager.backend is not None
    assert manager.board_pose_provider is None
    assert not manager.backend.get_state_snapshot().joints_valid
    recovered(sdk)
    snapshot = manager.backend.get_state_snapshot()
    assert snapshot.connected and snapshot.joints_valid
    assert snapshot.joints_deg == list(sdk.robot_state_pkg.jt_cur_pos)
    assert not manager.robot.connected and not manager.is_robot_ready
    assert not manager.robot.physical_motion_authorized
    create.assert_called_once()
    for name in ('Mode', 'RobotEnable', 'MoveJ', 'MoveL', 'MoveCart', 'SetToolDO', 'GetRobotTeachingPoint'):
        getattr(sdk, name).assert_not_called()


def test_recovery_needs_measured_packet_and_loss_invalidates_it(monkeypatch, tmp_path):
    manager, sdk, create = failed_manager(monkeypatch, tmp_path)
    assert manager.backend is not None
    sdk.SDK_state = True  # TCP connected alone does not make a measurement.
    assert not manager.backend.get_state_snapshot().joints_valid
    recovered(sdk)
    first = manager.backend.get_state_snapshot()
    assert first.joints_valid
    manager.backend._reader._last_stream_seen_monotonic -= 1
    stale = manager.backend.get_state_snapshot()
    assert not stale.joints_valid and stale.measurement_timestamp == first.measurement_timestamp
    sdk.SDK_state = False
    lost = manager.backend.get_state_snapshot()
    assert not lost.connected and not lost.joints_valid
    recovered(sdk)
    assert manager.backend.get_state_snapshot().joints_valid
    create.assert_called_once()


def test_raw_reader_never_opens_sdk_and_rejects_dry_robot():
    robot = SimpleNamespace(connected=False, dry=False, robot=SimpleNamespace(SDK_state=False), ip='unused')
    source = BorrowedPhysicalStateSource(robot)
    assert not source.get_state_snapshot().joints_valid
    robot.dry = True
    with pytest.raises(ValueError):
        BorrowedPhysicalStateSource(robot)


@pytest.mark.serial
def test_actual_websocket_stays_available_then_streams_recovered_arm(monkeypatch, tmp_path):
    from websockets.sync.client import connect
    from src.core import session_startup
    manager, sdk, create = failed_manager(monkeypatch, tmp_path)
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        manager.config.TELEMETRY_PORT = reserve.getsockname()[1]
    manager.initialize_all = Mock(return_value=manager)
    monkeypatch.setattr(session_startup, 'HardwareManager', lambda *_: manager)
    state = SimpleNamespace(set_board_observer=Mock(), sync_current_board=Mock(return_value=True))
    publisher = None
    try:
        _, publisher, _, _ = session_startup.build_session(manager.config,
            SimpleNamespace(no_viewer=True), str(tmp_path), state)
        assert manager.twin_bridge is not None
        with connect(f'ws://127.0.0.1:{manager.config.TELEMETRY_PORT}', open_timeout=2) as ws:
            first = json.loads(ws.recv(timeout=2))
            while first.get('type') != 'robot_state':
                first = json.loads(ws.recv(timeout=2))
            assert first['source'] == 'PHYSICAL' and not first['joints_valid']
            recovered(sdk)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                value = json.loads(ws.recv(timeout=2))
                if value.get('type') == 'robot_state' and value.get('joints_valid'):
                    break
            assert value['connected'] and value['joints_valid']
            assert value['joints'] == sdk.robot_state_pkg.jt_cur_pos
            state.set_board_observer.assert_called_once_with(manager.sync_committed_board)
            assert not manager.is_robot_ready
            create.assert_called_once()
    finally:
        if manager.twin_bridge:
            manager.twin_bridge.close()
        if publisher:
            publisher.stop()


def test_uncalibrated_viewer_autoconnects_when_arm_telemetry_is_available(monkeypatch):
    from src.core.launch_options import ViewerServer
    from urllib.parse import parse_qs, urlparse
    viewer = ViewerServer.__new__(ViewerServer)
    viewer.thread, viewer.url = Mock(), 'http://127.0.0.1:8088/robot-3d-viewer/'
    opened = Mock()
    monkeypatch.setattr('src.core.launch_options.webbrowser.open', opened)
    viewer.start(8765, unavailable_reason='Uncalibrated board', telemetry_available=True)
    query = parse_qs(urlparse(opened.call_args.args[0]).query)
    assert query['autoconnect'] == ['1']
    assert query['mirror_error'] == ['Uncalibrated board']


def test_session_passes_arm_availability_to_viewer(monkeypatch, tmp_path):
    from src.core import session_startup
    cfg = SimpleNamespace(GAME_ONLY=False, TELEMETRY_HOST='127.0.0.1', TELEMETRY_PORT=8765)
    bridge = SimpleNamespace(board_sync_available=False)
    manager = SimpleNamespace(initialize_all=Mock(), setup_digital_twin=Mock(return_value=bridge),
                              simulation_error='SDK not connected')
    manager.initialize_all.return_value = manager
    viewer, publisher = Mock(), Mock()
    monkeypatch.setattr(session_startup, 'HardwareManager', lambda *_: manager)
    monkeypatch.setattr(session_startup, 'TelemetryPublisher', lambda **_: publisher)
    monkeypatch.setattr(session_startup.launch_options, 'check_viewer_assets', Mock())
    monkeypatch.setattr(session_startup.launch_options, 'ViewerServer', lambda *_: viewer)
    session_startup.build_session(cfg, SimpleNamespace(no_viewer=False, viewer_port=8088),
                                tmp_path, SimpleNamespace())
    publisher.start.assert_called_once()
    assert viewer.start.call_args.kwargs['telemetry_available'] is True
