"""Connection/calibration boundaries with real adapters and mocked controller only."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.hardware import robot_VIP, simulation_adapter
from src.hardware.hardware_manager import HardwareManager


def make_robot(monkeypatch, fault=None):
    monkeypatch.setattr(config, 'DRY_RUN', False)
    corners = [(-207, 219), (-202, 547), (165, 546), (162, 222)]
    points = {}
    for i, (x, y) in enumerate(corners, 1):
        points[f'R{i}'] = [x, y, 220, -180, 0, -43] + [0]*6 + [0, 1, 100, 100, 0, 0, 0, 0]
    if fault == 'mixed':
        points['R4'][13] = 2  # Incompatible user frame mismatch.
    elif fault == 'r4_user0':
        points['R4'][13] = 0  # Live controller R4 user=0 with R1-R3 user=1.
    elif fault == 'missing_metadata':
        points['R4'] = points['R4'][:12]
    elif fault == 'missing_point':
        del points['R4']
    sdk = SimpleNamespace(SDK_state=True)
    sdk.GetRobotTeachingPoint = Mock(side_effect=lambda name: (0, points[name]) if name in points else (1, None))
    sdk.Mode = Mock(side_effect=AssertionError('Unexpected Mode'))
    sdk.RobotEnable = Mock(side_effect=AssertionError('Unexpected RobotEnable'))
    sdk.SetToolDO = Mock(side_effect=AssertionError('Unexpected gripper command'))
    monkeypatch.setattr(robot_VIP, 'robot_sdk_core', SimpleNamespace(RPC=Mock(return_value=sdk)))
    return robot_VIP.FR5Robot(), sdk, points


@pytest.mark.parametrize('fault', ['mixed', 'missing_metadata', 'missing_point'])
def test_calibration_error_keeps_connection_and_blocks_all_actuation(monkeypatch, fault):
    robot, sdk, _ = make_robot(monkeypatch, fault)
    assert robot.connect()
    assert robot.connected and robot.robot is sdk
    assert robot.teaching_points_error
    assert not robot.physical_motion_authorized
    assert robot.teaching_points == {}  # No partial/stale target coordinates.
    with pytest.raises(robot_VIP.RobotCommandError, match='R1-R4'):
        robot.activate_physical_control(commissioned=True)
    robot.physical_motion_authorized = True
    with pytest.raises(robot_VIP.RobotCommandError, match='R1-R4'):
        robot._require_actuation()
    sdk.Mode.assert_not_called()
    sdk.RobotEnable.assert_not_called()
    sdk.SetToolDO.assert_not_called()


def test_r4_user_zero_compatible_with_user_one(monkeypatch):
    robot, sdk, _ = make_robot(monkeypatch, 'r4_user0')
    assert robot.connect()
    assert robot.teaching_points_error is None
    assert (robot.tool_num, robot.user_num) == (0, 1)
    assert robot._validated_corners().shape == (4, 3)
    assert not robot.physical_motion_authorized
    sdk.RobotEnable.assert_not_called()


def test_valid_connection_loads_taught_frames_without_enabling(monkeypatch):
    robot, sdk, _ = make_robot(monkeypatch)
    assert robot.connect()
    assert robot.teaching_points_error is None
    assert (robot.tool_num, robot.user_num) == (0, 1)
    assert robot._validated_corners().shape == (4, 3)
    assert not robot.physical_motion_authorized
    sdk.RobotEnable.assert_not_called()


def test_actual_sdk_failure_remains_connection_failure(monkeypatch):
    robot, sdk, _ = make_robot(monkeypatch)
    sdk.SDK_state = False
    with pytest.raises(robot_VIP.RobotCommandError, match='SDK not connected'):
        robot.connect()
    assert not robot.connected
    sdk.GetRobotTeachingPoint.assert_not_called()


def test_dry_connect_preserves_existing_geometry_without_sdk(monkeypatch):
    robot, sdk, _ = make_robot(monkeypatch)
    robot.dry = True
    geometry = {'R1': {'pose': [0, 0, 220, 180, 0, 0]}}
    robot.teaching_points = geometry
    assert robot.connect()
    assert robot.teaching_points is geometry
    robot_VIP.robot_sdk_core.RPC.assert_not_called()


def test_reconnect_reloads_and_clears_calibration_error(monkeypatch):
    robot, sdk, points = make_robot(monkeypatch, 'mixed')
    assert robot.connect()
    assert robot.teaching_points_error
    points['R4'][13] = 1
    assert robot.connect()
    assert robot.teaching_points_error is None
    assert not robot.physical_motion_authorized


def test_uncalibrated_manager_keeps_raw_arm_relay(monkeypatch, tmp_path):
    robot, sdk, _ = make_robot(monkeypatch, 'mixed')
    manager = HardwareManager(SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND='PHYSICAL'), str(tmp_path))
    manager.robot = robot
    snapshot = object()
    backend = SimpleNamespace(ip=robot.ip, get_state_snapshot=Mock(return_value=snapshot))
    monkeypatch.setattr(simulation_adapter, 'BorrowedPhysicalStateSource', Mock(return_value=backend))
    provider = Mock(side_effect=AssertionError('Unverified board was calibrated'))
    monkeypatch.setattr(simulation_adapter, 'physical_board_provider', provider)
    manager._init_robot()
    assert robot.connected
    assert manager.backend is backend
    assert manager.board_pose_provider is None
    assert 'R1-R4' in manager.simulation_error
    publisher = Mock()
    relay = manager.setup_digital_twin(publisher, start=False)
    try:
        assert relay.board_sync_available
        assert relay.poll_once() is snapshot
        publisher.update_from_snapshot.assert_called_once_with(snapshot)
        provider.assert_not_called()
        assert not manager.is_robot_ready
        sdk.RobotEnable.assert_not_called()
    finally:
        relay.close()


def test_uncalibrated_relay_syncs_human_move_and_command_animation(monkeypatch, tmp_path):
    from src.domain.game_move import MoveActor, MoveContext

    robot, sdk, _ = make_robot(monkeypatch, 'mixed')
    manager = HardwareManager(SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND='PHYSICAL'), str(tmp_path))
    manager.robot = robot
    snapshot = SimpleNamespace(connected=False, joints_valid=False)
    backend = SimpleNamespace(ip=robot.ip, get_state_snapshot=Mock(return_value=snapshot))
    monkeypatch.setattr(simulation_adapter, 'BorrowedPhysicalStateSource', Mock(return_value=backend))
    manager._init_robot()
    publisher = Mock()
    relay = manager.setup_digital_twin(publisher, start=False)
    try:
        assert robot.motion_listener == relay.animate_command_gripper
        move = MoveContext(
            piece_id='red_cannon_0',
            src=(7, 1),
            dst=(7, 4),
            actor=MoveActor.HUMAN,
        )
        assert relay.reconcile_human_move(move)
        assert relay._cells[(7, 4)] == 'red_cannon_0'
        assert (7, 1) not in relay._cells
        assert manager.sync_committed_board(dict(relay._cells))

        robot_move = MoveContext(
            piece_id='black_knight_0',
            src=(0, 1),
            dst=(2, 2),
            actor=MoveActor.ROBOT,
        )
        relay.begin_command_animation(robot_move)
        relay.animate_command_gripper('gripper', True)
        assert relay.world.get_attached_piece().piece_id == 'black_knight_0'
        relay.animate_command_gripper('gripper', False)
        assert relay.world.get_attached_piece() is None
        relay.finish_command_animation()
        assert relay.reconcile_new_game()
        assert len(relay._cells) == 32
        assert relay._cells[(7, 1)] == 'red_cannon_0'
    finally:
        relay.close()


@pytest.mark.serial
def test_session_streams_raw_arm_over_actual_websocket_with_invalid_board(monkeypatch, tmp_path):
    import json
    import socket
    import time
    from websockets.sync.client import connect
    from src.core import session_startup
    from src.hardware.backends.base import RobotStateSnapshot

    robot, sdk, _ = make_robot(monkeypatch, 'mixed')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    cfg = SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND='PHYSICAL', GAME_ONLY=False,
                          TELEMETRY_HOST='127.0.0.1', TELEMETRY_PORT=port)
    manager = HardwareManager(cfg, str(tmp_path))
    manager.robot = robot
    joints = [-89.465, -128.623, 106.877, -68.511, -89.496, 42.537]
    def read_snapshot():
        now = time.time()
        return RobotStateSnapshot('FR3', True, 'IDLE', joints,
            [-104.282, 149.626, 348.136, 179.848, .545, -42.002],
            [-104.282, 149.626, 348.136, 179.848, .545, -42.002],
            False, now, measurement_timestamp=now)
    backend = SimpleNamespace(ip=robot.ip, get_state_snapshot=read_snapshot)
    monkeypatch.setattr(simulation_adapter, 'BorrowedPhysicalStateSource', lambda _: backend)
    manager._init_robot()
    manager.initialize_all = Mock(return_value=manager)  # Camera/engine intentionally absent.
    monkeypatch.setattr(session_startup, 'HardwareManager', lambda *_: manager)
    state = SimpleNamespace(set_board_observer=Mock(), sync_current_board=Mock(return_value=True))
    publisher = None
    try:
        _, publisher, viewer, reason = session_startup.build_session(
            cfg, SimpleNamespace(no_viewer=True), str(tmp_path), state)
        assert viewer is None and 'R1-R4' in reason
        state.set_board_observer.assert_called_once_with(manager.sync_committed_board)
        state.sync_current_board.assert_called_once()
        with connect(f'ws://127.0.0.1:{port}', open_timeout=3) as ws:
            packet = json.loads(ws.recv(timeout=3))
            while packet.get('type') != 'robot_state':
                packet = json.loads(ws.recv(timeout=3))
            assert packet['type'] == 'robot_state'
            assert packet['source'] == 'PHYSICAL'
            assert packet['connected'] and packet['joints_valid']
            assert packet['joints'] == joints
            assert packet['tcp'][2] == 348.136
        assert not robot.physical_motion_authorized
        sdk.Mode.assert_not_called()
        sdk.RobotEnable.assert_not_called()
        sdk.SetToolDO.assert_not_called()
    finally:
        if manager.twin_bridge:
            manager.twin_bridge.close()
        if publisher:
            publisher.stop()

