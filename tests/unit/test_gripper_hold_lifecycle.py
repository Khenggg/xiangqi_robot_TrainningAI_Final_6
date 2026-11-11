"""Shutdown must stop arm motion before cutting held CLOSE and other resources."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.hardware.controlled_stop import ControlledStopCoordinator, StopRequest, StopResult
from src.hardware.hardware_manager import HardwareManager as SharedHardwareManager
from src.hardware.home_chess_recovery import check_home_chess, return_to_home_chess
from src.modes.vsc_v3.hardware.hardware_manager import HardwareManager as PrivateHardwareManager
from src.hardware.robot_VIP import FR5Robot, GripperCommandError
from src.modes.vsc_v3_session import VscV3Session


@pytest.mark.parametrize('manager_type', [SharedHardwareManager, PrivateHardwareManager])
@pytest.mark.parametrize('failure', [None, 'camera', 'hold', 'stop'])
def test_cleanup_stops_arm_and_close_hold_before_other_resources(manager_type, failure):
    events = []
    manager = manager_type.__new__(manager_type)

    def operation(name):
        def run():
            events.append(name)
            if failure == name:
                raise RuntimeError(f'{name} shutdown failed')
            if name == 'hold':
                robot._gripper_hold_active = False
        return run

    robot = SimpleNamespace(_gripper_hold_active=True, _gripper_pulse_active=False,
        physical_motion_authorized=True, _activation_owned=False, connected=True,
        latch_motion_stop=Mock(side_effect=operation('latch')),
        send_controlled_stop=Mock(side_effect=lambda **kwargs: send_stop()),
        stop_gripper_hold=Mock(side_effect=operation('hold')),
        _set_gripper_safe_idle=Mock(side_effect=operation('gripper_idle')),
        deactivate_physical_control=Mock(side_effect=operation('disable')),
        robot=SimpleNamespace(CloseRPC=Mock(side_effect=operation('sdk'))))

    def send_stop():
        events.append('stop')
        if failure == 'stop':
            raise RuntimeError('stop shutdown failed')
        return 0

    def shutdown():
        events.append('shutdown')
        send_stop()
        robot.stop_gripper_hold()

    robot.stop_gripper_for_shutdown = Mock(side_effect=shutdown)
    manager.robot = robot
    manager.dry_run = False
    manager.simulation_runtime = None
    manager.backend = SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state='IDLE', last_error=None)))
    manager._piece_move_lock = threading.Lock()
    manager.motion_worker = SimpleNamespace(running=False, close=Mock(side_effect=operation('worker')))
    manager.cam_monitor = SimpleNamespace(stop=Mock(side_effect=operation('camera')))
    manager.cap = SimpleNamespace(release=Mock(side_effect=operation('capture')))
    manager.close_simulation = Mock(side_effect=operation('mirror'))
    manager.stop_coordinator = ControlledStopCoordinator(manager)
    if failure:
        with pytest.raises(RuntimeError):
            manager.cleanup()
    else:
        manager.cleanup()
    if manager_type is SharedHardwareManager:
        request = manager.stop_coordinator.request
        assert request is not None and request.done.wait(2)
        request.thread.join(2)
        assert events[0] == 'latch' and events[1] == 'stop'
        robot.stop_gripper_for_shutdown.assert_not_called()
    else:
        assert events[0] == 'shutdown' and events[1] == 'stop'
        robot.stop_gripper_for_shutdown.assert_called_once_with()
    if failure in {'hold', 'stop'}:
        assert robot._gripper_hold_active is True
        manager.cam_monitor.stop.assert_not_called()
        robot.deactivate_physical_control.assert_not_called()
        robot.robot.CloseRPC.assert_not_called()
    else:
        assert robot._gripper_hold_active is False
        assert events.index('stop') < events.index('hold')
        assert events.index('hold') < events.index('camera')
        if 'disable' in events:
            assert events.index('hold') < events.index('disable')


def hardware_with_hold():
    robot = SimpleNamespace(_gripper_hold_active=True, _gripper_pulse_active=False,
        physical_motion_authorized=False, _activation_owned=False,
        latch_motion_stop=Mock(), send_controlled_stop=Mock())
    return SimpleNamespace(robot=robot, dry_run=False, simulation_runtime=None,
        motion_worker=None, _piece_move_lock=threading.Lock(),
        backend=SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda: SimpleNamespace(
            connected=True, joints_valid=True, measurement_timestamp=time.time(),
            motion_state='IDLE', last_error=None))))


@pytest.mark.parametrize('manager_type', [SharedHardwareManager, PrivateHardwareManager])
def test_retained_stop_failure_blocks_cleanup_even_after_outputs_are_off(manager_type):
    manager = manager_type.__new__(manager_type)
    failure = RuntimeError('Previous StopMotion outcome is unknown')
    robot = SimpleNamespace(_gripper_hold_active=False, _gripper_pulse_active=False,
        _gripper_stop_failure=failure, physical_motion_authorized=True, _activation_owned=False,
        connected=True, stop_gripper_for_shutdown=Mock(side_effect=failure),
        stop_gripper_hold=Mock(return_value=0),
        deactivate_physical_control=Mock(), _set_gripper_safe_idle=Mock(),
        robot=SimpleNamespace(CloseRPC=Mock()))
    manager.robot = robot
    manager.dry_run = False
    manager.backend = None
    manager.motion_worker = None
    manager._piece_move_lock = threading.Lock()
    manager.cam_monitor = SimpleNamespace(stop=Mock())
    manager.cap = SimpleNamespace(release=Mock())
    manager.close_simulation = Mock()
    manager.stop_coordinator = SimpleNamespace(request=None)
    manager.request_controlled_stop = Mock(side_effect=AssertionError('An unknown stop must not be replayed'))
    with pytest.raises(RuntimeError):
        manager.cleanup()
    manager.cam_monitor.stop.assert_not_called()
    manager.cap.release.assert_not_called()
    manager.request_controlled_stop.assert_not_called()
    robot.deactivate_physical_control.assert_not_called()
    robot.robot.CloseRPC.assert_not_called()


@pytest.mark.parametrize('off_failure', [False, True])
def test_shared_cleanup_retries_only_off_and_keeps_unknown_arm_stop_latched(off_failure):
    manager = SharedHardwareManager.__new__(SharedHardwareManager)
    failure = RuntimeError('Previous StopMotion outcome is unknown')
    robot = SimpleNamespace(_gripper_hold_active=True, _gripper_pulse_active=False,
        _gripper_stop_failure=failure, send_controlled_stop=Mock(),
        deactivate_physical_control=Mock(), robot=SimpleNamespace(CloseRPC=Mock()))

    def off():
        if off_failure:
            raise RuntimeError('Held output OFF still unacknowledged')
        robot._gripper_hold_active = False
        return 0

    robot.stop_gripper_hold = Mock(side_effect=off)
    manager.robot = robot
    manager.cam_monitor = SimpleNamespace(stop=Mock())
    manager.request_controlled_stop = Mock()
    with pytest.raises(RuntimeError):
        manager.cleanup()
    robot.stop_gripper_hold.assert_called_once_with()
    assert robot._gripper_hold_active is off_failure
    assert robot._gripper_stop_failure is failure
    robot.send_controlled_stop.assert_not_called()
    manager.request_controlled_stop.assert_not_called()
    manager.cam_monitor.stop.assert_not_called()
    robot.deactivate_physical_control.assert_not_called()
    robot.robot.CloseRPC.assert_not_called()


def test_hold_output_is_not_idle_evidence_even_when_arm_telemetry_is_idle():
    hardware = hardware_with_hold()
    coordinator = ControlledStopCoordinator(hardware)
    with pytest.raises(RuntimeError, match='Gripper close output is still active'):
        coordinator.observe_idle(timeout=.04)
    assert coordinator.request is None
    request = coordinator.request = StopRequest('completed arm stop')
    request.finish(StopResult(True, True, 'arm stopped'))
    assert not coordinator.safe_for_release()
    request.finish(StopResult(False, True, 'awaiting output stop'))
    assert not coordinator.refresh_acknowledged_stop()
    assert 'gripper output' in coordinator.last_settle_diagnostic.lower()
    hardware.backend.get_state_snapshot.assert_not_called()
    assert hardware.robot._gripper_hold_active is True
    hardware.robot.send_controlled_stop.assert_not_called()


@pytest.mark.parametrize('off_failure', [False, True])
def test_controlled_stop_cuts_existing_hold_before_declaring_idle(off_failure):
    hardware = hardware_with_hold()

    def stop_hold():
        if off_failure:
            raise RuntimeError('held output OFF not acknowledged')
        hardware.robot._gripper_hold_active = False

    hardware.robot.stop_gripper_hold = Mock(side_effect=stop_hold)
    coordinator = ControlledStopCoordinator(hardware)
    request = coordinator.begin('cancel game with held output', timeout=.1)
    assert request.done.wait(2)
    request.thread.join(2)
    hardware.robot.stop_gripper_hold.assert_called_once_with()
    assert request.result.safe is not off_failure
    assert hardware.robot._gripper_hold_active is off_failure
    if off_failure:
        assert 'held output OFF not acknowledged' in request.result.reason
    hardware.robot.send_controlled_stop.assert_not_called()  # Read-only ownership was not acquired.


@pytest.mark.parametrize('active_hold', [False, True])
def test_retained_unknown_stop_is_not_replayed_or_recovered_from_idle_telemetry(active_hold):
    hardware = hardware_with_hold()
    robot = hardware.robot
    robot.physical_motion_authorized = True
    robot._gripper_hold_active = active_hold
    robot._gripper_stop_failure = RuntimeError('Previous StopMotion outcome is unknown')
    robot.stop_gripper_hold = Mock(side_effect=lambda: setattr(robot, '_gripper_hold_active', False))
    coordinator = ControlledStopCoordinator(hardware)
    request = coordinator.begin('another pause after unknown stop', timeout=.1)
    assert request.done.wait(2)
    request.thread.join(2)
    assert not request.result.safe and not request.result.acknowledged
    assert 'unknown' in request.result.reason
    robot.send_controlled_stop.assert_not_called()
    robot.stop_gripper_hold.assert_called_once_with()
    assert robot._gripper_hold_active is False
    with pytest.raises(RuntimeError, match='unknown'):
        coordinator.observe_idle(timeout=.08)
    assert not request.result.safe and not coordinator.safe_for_release()
    hardware.backend.get_state_snapshot.assert_not_called()


@pytest.mark.parametrize('operation', [check_home_chess, return_to_home_chess])
def test_home_recovery_does_not_move_while_close_output_is_held(operation):
    robot = SimpleNamespace(dry=False, connected=True, physical_motion_authorized=True,
        _disable_outcome_unknown=False, _gripper_pulse_active=False, _gripper_hold_active=True,
        read_teaching_point=Mock(), movel_pose=Mock(), movej_joint=Mock(), _require_actuation=Mock())
    result = operation(robot, is_current=lambda: True)
    assert not result.at_home and not result.commanded
    assert 'Gripper close output is still active' in result.reason
    robot.read_teaching_point.assert_not_called()
    robot.movel_pose.assert_not_called()
    robot.movej_joint.assert_not_called()
    robot._require_actuation.assert_not_called()


def test_empty_hold_registry_requires_no_driver_command_or_transport(monkeypatch):
    from src.hardware import rpc_transport
    monkeypatch.setattr(FR5Robot, '_gripper_hold_registry', set())
    monkeypatch.setattr(FR5Robot, '_gripper_holds_closing', False)
    shutdown = Mock()
    transport = Mock()
    monkeypatch.setattr(FR5Robot, 'stop_gripper_for_shutdown', shutdown)
    monkeypatch.setattr(rpc_transport, 'BoundedRPCProxy', transport)
    assert FR5Robot.stop_all_gripper_holds() is True
    assert FR5Robot._gripper_holds_closing is True
    shutdown.assert_not_called()
    transport.assert_not_called()


@pytest.mark.parametrize('off_failure', [False, True])
def test_exit_registry_stops_all_holders_even_when_one_off_fails(monkeypatch, off_failure):
    events = []
    holders = [Mock(), Mock()]
    for index, holder in enumerate(holders):
        holder.latch_motion_stop.side_effect = lambda i=index: events.append(('latch', i))

        def off(*, latch=True, i=index):
            events.append(('off', i))
            if off_failure and i == 0:
                raise RuntimeError('DO OFF not acknowledged')

        holder.stop_gripper_for_shutdown.side_effect = off
    monkeypatch.setattr(FR5Robot, '_gripper_hold_registry', set(holders))
    monkeypatch.setattr(FR5Robot, '_gripper_holds_closing', False)
    if off_failure:
        with pytest.raises(GripperCommandError, match='DO OFF not acknowledged'):
            FR5Robot.stop_all_gripper_holds()
    else:
        assert FR5Robot.stop_all_gripper_holds() is True
    assert len(events) == 4
    assert {kind for kind, _ in events[:2]} == {'latch'}
    assert {kind for kind, _ in events[2:]} == {'off'}
    for holder in holders:
        holder.latch_motion_stop.assert_called_once_with()
        holder.stop_gripper_for_shutdown.assert_called_once_with()


@pytest.mark.parametrize('active_output', ['hold', 'pulse', None])
def test_private_session_cuts_active_output_before_retaining_a_hung_worker(active_output):
    session = VscV3Session.__new__(VscV3Session)
    session._closed = False
    events = []
    worker = SimpleNamespace(join=Mock(), is_alive=Mock(return_value=True))
    session.input = SimpleNamespace(_motion_thread=worker)
    session.state = SimpleNamespace(ai_thread=None)
    robot = SimpleNamespace(_gripper_hold_active=active_output == 'hold',
        _gripper_pulse_active=active_output == 'pulse',
        latch_motion_stop=Mock(),
        stop_gripper_for_shutdown=Mock(side_effect=lambda: events.append('shutdown')),
        stop_gripper_hold=Mock())
    session.hw = SimpleNamespace(robot=robot, cleanup=Mock())
    session.showcase = SimpleNamespace(close=Mock())
    with pytest.raises(RuntimeError, match='worker still owns session resources'):
        session.close()
    worker.join.assert_called_once_with(5)
    assert events == ([] if active_output is None else ['shutdown'])
    if active_output is not None:
        robot.stop_gripper_for_shutdown.assert_called_once_with()
    else:
        robot.stop_gripper_for_shutdown.assert_not_called()
    robot.stop_gripper_hold.assert_not_called()
    session.hw.cleanup.assert_not_called()
    session.showcase.close.assert_not_called()
    assert not session._closed
