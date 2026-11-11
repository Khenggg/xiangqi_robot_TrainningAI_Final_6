"""Sustained closing and interruption tests; every output/RPC is a mock."""
from types import SimpleNamespace
import threading
from unittest.mock import Mock

import pytest

import config
from src.hardware.robot_VIP import FR5Robot, GripperCommandError, RobotCommandError
from src.hardware.rpc_transport import RpcOutcomeUnknown
from src.motion.stages import MotionStage


@pytest.fixture(autouse=True)
def isolated_holders(monkeypatch):
    monkeypatch.setattr(FR5Robot, '_gripper_hold_registry', set())
    monkeypatch.setattr(FR5Robot, '_gripper_holds_closing', False)
    monkeypatch.setattr('src.hardware.robot_VIP.time.sleep', lambda _seconds: None)


@pytest.fixture
def held_robot(monkeypatch):
    robot = FR5Robot(dry_run=True)
    outputs, calls = {0: 0, 1: 0}, []

    def write(output_id, status):
        calls.append((output_id, status))
        outputs[output_id] = status
        assert not (outputs[0] and outputs[1]), 'Both motor directions energized'
        return 0

    monkeypatch.setattr(robot, '_set_tool_do', write)
    monkeypatch.setattr(robot._motion_stop, 'wait', lambda _seconds: robot._motion_stop.is_set())
    robot.board_to_pose = Mock(side_effect=lambda col, row, z, **kw: [col, row, z, 180, 0, 0])
    robot.board_to_pose_bilinear = robot.board_to_pose
    robot.move_safe_pose = Mock(return_value=0)
    robot.movel_pose = Mock(return_value=0)
    return SimpleNamespace(robot=robot, outputs=outputs, calls=calls, write=write)


def test_close_stays_powered_after_initial_dwell_until_release(held_robot):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    assert r.outputs == {0: 0, 1: 1}
    assert r.robot._gripper_hold_active and not r.robot._gripper_pulse_active
    assert r.robot.gripper_command_known and r.robot.gripper_closed_estimate
    assert r.robot in FR5Robot._gripper_hold_registry
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN_MAX)
    assert r.outputs == {0: 0, 1: 0}
    assert not r.robot._gripper_hold_active
    assert r.robot not in FR5Robot._gripper_hold_registry
    opening = r.calls.index((0, 1))
    assert r.calls[opening - 2:opening] == [(0, 0), (1, 0)]


def test_pick_approaches_fully_open_and_lifts_with_continuous_close(held_robot):
    r = held_robot
    stages = []
    r.robot.move_safe_pose.side_effect = lambda *a, **kw: stages.append(('approach', dict(r.outputs))) or 0
    r.robot.movel_pose.side_effect = lambda pose: stages.append((pose[2], dict(r.outputs))) or 0
    r.robot.pick_at(4, 6)
    assert stages == [('approach', {0: 0, 1: 0}),
                      (config.PICK_Z, {0: 0, 1: 0}), (config.SAFE_Z, {0: 0, 1: 1})]
    assert [call for call in r.calls if call[1]] == [(0, 1), (1, 1)]
    assert r.robot._gripper_hold_active


@pytest.mark.parametrize('release', [config.GRIPPER_ACTION_OPEN_MAX,
                                    config.GRIPPER_ACTION_RELEASE,
                                    config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP])
def test_next_gripper_action_ends_hold_before_its_pulse(held_robot, release):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    r.calls.clear()
    r.robot.gripper_ctrl(release)
    assert r.calls[:2] == [(0, 0), (1, 0)]
    assert r.outputs == {0: 0, 1: 0}
    assert not r.robot._gripper_hold_active


def test_close_on_unknown_reply_attempts_off_and_does_not_report_known_grasp(held_robot, monkeypatch):
    r = held_robot

    def uncertain(output_id, status):
        r.write(output_id, status)
        if status:
            raise RpcOutcomeUnknown('ON reply lost')

    monkeypatch.setattr(r.robot, '_set_tool_do', uncertain)
    with pytest.raises(RpcOutcomeUnknown, match='ON reply lost'):
        r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    assert r.outputs == {0: 0, 1: 0}
    assert not r.robot._gripper_hold_active and not r.robot.gripper_command_known


def test_failed_off_keeps_uncertainty_and_registered_holder(held_robot, monkeypatch):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)

    def failed_off(output_id, status):
        if output_id == 1 and not status:
            raise RpcOutcomeUnknown('OFF reply lost')
        return r.write(output_id, status)

    monkeypatch.setattr(r.robot, '_set_tool_do', failed_off)
    with pytest.raises(GripperCommandError, match='both gripper outputs LOW'):
        r.robot.stop_gripper_hold()
    assert r.robot._gripper_hold_active and not r.robot.gripper_command_known
    assert r.robot in FR5Robot._gripper_hold_registry


@pytest.mark.parametrize('failure', ['lift', 'validity', 'stage_result'])
def test_stage_failure_cuts_hold_without_replaying_motion(held_robot, failure):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    if failure == 'validity':
        r.robot.dispatch_validity = Mock(side_effect=RobotCommandError('expired binding'))
        operation = Mock(return_value=0)
    else:
        operation = Mock(side_effect=RobotCommandError('lift failed') if failure == 'lift' else None,
                         return_value=112 if failure == 'stage_result' else 0)
    with pytest.raises(RobotCommandError):
        r.robot._run_stage(MotionStage.LIFT, operation)
    assert operation.call_count == (0 if failure == 'validity' else 1)
    assert r.outputs == {0: 0, 1: 0} and not r.robot._gripper_hold_active


def test_direct_pick_lift_failure_cuts_hold(held_robot):
    r = held_robot
    r.robot.movel_pose.side_effect = [0, RobotCommandError('lift failed')]
    with pytest.raises(RobotCommandError, match='lift failed'):
        r.robot.pick_at(4, 6)
    assert r.outputs == {0: 0, 1: 0} and not r.robot._gripper_hold_active
    assert not r.robot.gripper_command_known


def test_failed_move_keeps_typed_failure_when_hold_cleanup_also_fails(held_robot, monkeypatch):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    monkeypatch.setattr(r.robot, '_set_tool_do', Mock(side_effect=RpcOutcomeUnknown('OFF unknown')))
    r.robot._move_piece_sequence = Mock(side_effect=RobotCommandError('motion failed', 112))
    result = r.robot.move_piece(4, 6, 4, 5, False)
    assert not result.success
    assert result.metadata['gripper_output_unknown']
    assert 'OFF unknown' in result.metadata['gripper_cleanup_error']
    assert r.robot._gripper_hold_active and r.robot in FR5Robot._gripper_hold_registry


@pytest.mark.parametrize('stop_error', [False, True])
def test_independent_stop_cuts_hold_even_when_stop_motion_reply_is_unknown(held_robot, monkeypatch, stop_error):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    r.robot.dry = False
    r.robot.physical_motion_authorized = True
    order = []

    def stop():
        order.append('stop')
        if stop_error:
            raise RpcOutcomeUnknown('StopMotion unknown')
        return 0

    def off(output_id, status, smooth, block):
        order.append((output_id, status, smooth, block))
        return r.write(output_id, status)

    proxy = SimpleNamespace(StopMotion=Mock(side_effect=stop), SetToolDO=Mock(side_effect=off))
    factory = Mock(return_value=proxy)
    monkeypatch.setattr('src.hardware.rpc_transport.BoundedRPCProxy', factory)
    r.robot.latch_motion_stop()
    if stop_error:
        with pytest.raises(RpcOutcomeUnknown, match='StopMotion unknown'):
            r.robot.send_controlled_stop()
    else:
        assert r.robot.send_controlled_stop() == 0
    assert order == ['stop', (0, 0, 0, 0), (1, 0, 0, 0)]
    assert r.outputs == {0: 0, 1: 0} and not r.robot._gripper_hold_active
    proxy.StopMotion.assert_called_once()


def test_stop_motion_still_runs_if_hold_off_is_rejected(held_robot, monkeypatch):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    r.robot.dry = False
    r.robot.physical_motion_authorized = True
    proxy = SimpleNamespace(StopMotion=Mock(return_value=0), SetToolDO=Mock(return_value=112))
    monkeypatch.setattr('src.hardware.rpc_transport.BoundedRPCProxy', Mock(return_value=proxy))
    with pytest.raises(GripperCommandError):
        r.robot.send_controlled_stop()
    proxy.StopMotion.assert_called_once()
    assert proxy.SetToolDO.call_count == 2 and r.robot._gripper_hold_active


def test_disable_cuts_hold_before_disabling_controller(held_robot):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    r.robot.deactivate_physical_control()
    assert r.outputs == {0: 0, 1: 0} and not r.robot._gripper_hold_active


def test_exit_barrier_cuts_hold_and_blocks_new_output(held_robot):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    assert FR5Robot.stop_all_gripper_holds()
    assert r.outputs == {0: 0, 1: 0} and not FR5Robot._gripper_hold_registry
    newcomer = FR5Robot(dry_run=True)
    newcomer._set_tool_do = Mock(return_value=0)
    with pytest.raises(GripperCommandError, match='closing'):
        newcomer.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    assert not any(call.args[1] for call in newcomer._set_tool_do.call_args_list)


def test_exit_barrier_keeps_holder_if_off_not_confirmed(held_robot, monkeypatch):
    r = held_robot
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    monkeypatch.setattr(r.robot, '_set_tool_do', Mock(side_effect=RpcOutcomeUnknown('OFF unknown')))
    with pytest.raises(GripperCommandError, match='Cannot exit'):
        FR5Robot.stop_all_gripper_holds()
    assert r.robot in FR5Robot._gripper_hold_registry and r.robot._gripper_hold_active


def test_exit_during_open_pulse_is_registered_and_cuts_outputs(held_robot, monkeypatch):
    r = held_robot

    def wait(_seconds):
        assert r.robot in FR5Robot._gripper_hold_registry
        assert r.robot._gripper_pulse_active
        FR5Robot.stop_all_gripper_holds()
        return True

    monkeypatch.setattr(r.robot._motion_stop, 'wait', wait)
    with pytest.raises(GripperCommandError, match='interrupted'):
        r.robot.gripper_ctrl(config.GRIPPER_ACTION_OPEN_MAX)
    assert r.outputs == {0: 0, 1: 0} and not FR5Robot._gripper_hold_registry


def test_latched_stop_blocks_new_close_without_energizing_outputs(held_robot):
    r = held_robot
    r.robot.latch_motion_stop()
    with pytest.raises(RobotCommandError, match='controlled stop'):
        r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    assert r.calls == [] and not FR5Robot._gripper_hold_registry


def physical_holder(r, monkeypatch, stop_failure=None):
    r.robot.gripper_ctrl(config.GRIPPER_ACTION_CLOSE)
    r.robot.dry = False
    r.robot.connected = True
    r.robot.physical_motion_authorized = True
    order = []

    def stop():
        order.append('stop')
        if isinstance(stop_failure, BaseException):
            raise stop_failure
        return 0 if stop_failure is None else stop_failure

    def off(output_id, status, smooth, block):
        order.append((output_id, status))
        return r.write(output_id, status)

    proxy = SimpleNamespace(StopMotion=Mock(side_effect=stop), SetToolDO=Mock(side_effect=off))
    monkeypatch.setattr('src.hardware.rpc_transport.BoundedRPCProxy', Mock(return_value=proxy))
    return proxy, order


def test_shutdown_stops_actual_owned_motion_before_removing_hold(held_robot, monkeypatch):
    r = held_robot
    proxy, order = physical_holder(r, monkeypatch)
    assert r.robot.stop_gripper_for_shutdown() == 0
    assert order == ['stop', (0, 0), (1, 0)]
    assert r.robot._motion_stop.is_set()
    assert not r.robot._gripper_hold_active and not FR5Robot._gripper_hold_registry
    proxy.StopMotion.assert_called_once()


def test_known_motion_rejection_stops_then_cuts_hold_and_keeps_home_available(held_robot, monkeypatch):
    r = held_robot
    proxy, order = physical_holder(r, monkeypatch)
    with pytest.raises(RobotCommandError, match='LIFT failed'):
        r.robot._run_stage(MotionStage.LIFT, Mock(return_value=112))
    assert order == ['stop', (0, 0), (1, 0)]
    assert not r.robot._motion_stop.is_set()  # A successful stop does not force a new HOME latch.
    assert r.robot._gripper_stop_failure is None and not r.robot._gripper_hold_active
    proxy.StopMotion.assert_called_once()


def test_unknown_original_motion_latches_even_if_later_stop_succeeds(held_robot, monkeypatch):
    r = held_robot
    proxy, order = physical_holder(r, monkeypatch)
    with pytest.raises(RpcOutcomeUnknown, match='MoveCart unknown'):
        r.robot._run_stage(MotionStage.LIFT, Mock(side_effect=RpcOutcomeUnknown('MoveCart unknown')))
    assert order == ['stop', (0, 0), (1, 0)]
    assert r.robot._motion_stop.is_set() and not r.robot._gripper_hold_active


@pytest.mark.parametrize('stop_failure', [RpcOutcomeUnknown('StopMotion unknown'), 112])
def test_unknown_or_rejected_stop_cannot_be_hidden_by_off_ack_or_repeated_exit(
        held_robot, monkeypatch, stop_failure):
    r = held_robot
    proxy, order = physical_holder(r, monkeypatch, stop_failure)
    with pytest.raises((RpcOutcomeUnknown, RobotCommandError)):
        r.robot.stop_gripper_for_shutdown()
    assert order == ['stop', (0, 0), (1, 0)]
    assert r.outputs == {0: 0, 1: 0} and not r.robot._gripper_hold_active
    assert isinstance(r.robot._gripper_stop_failure, BaseException)
    assert r.robot in FR5Robot._gripper_hold_registry and r.robot._motion_stop.is_set()
    with pytest.raises(GripperCommandError, match='Cannot exit'):
        FR5Robot.stop_all_gripper_holds()
    with pytest.raises((RpcOutcomeUnknown, RobotCommandError)):
        r.robot.send_controlled_stop()
    proxy.StopMotion.assert_called_once()  # Neither path resends the unresolved stop.


def test_failed_move_exposes_unknown_stop_in_typed_metadata(held_robot, monkeypatch):
    r = held_robot
    proxy, order = physical_holder(r, monkeypatch, RpcOutcomeUnknown('StopMotion unknown'))
    r.robot._move_piece_sequence = Mock(side_effect=RobotCommandError('motion rejected', 112))
    result = r.robot.move_piece(4, 6, 4, 5, False)
    assert not result.success and result.metadata['controller_stop_unresolved']
    assert result.metadata['rpc_outcome_unknown']
    assert r.robot._motion_stop.is_set() and r.robot in FR5Robot._gripper_hold_registry
    proxy.StopMotion.assert_called_once()


def test_exit_waiting_on_inflight_stop_observes_its_failure_without_replay(held_robot, monkeypatch):
    r = held_robot
    proxy, _order = physical_holder(r, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    failures = []

    def stop():
        entered.set()
        assert release.wait(2)
        raise RpcOutcomeUnknown('StopMotion unknown')

    def worker():
        try:
            r.robot.stop_gripper_for_shutdown(latch=False)
        except Exception as exc:
            failures.append(exc)

    proxy.StopMotion.side_effect = stop
    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(1)
    assert r.robot in FR5Robot._gripper_hold_registry
    timer = threading.Timer(.05, release.set)
    timer.start()
    try:
        with pytest.raises(GripperCommandError, match='Cannot exit'):
            FR5Robot.stop_all_gripper_holds()
    finally:
        release.set()
        thread.join(2)
        timer.join(1)
    assert not thread.is_alive() and failures
    assert r.robot in FR5Robot._gripper_hold_registry
    proxy.StopMotion.assert_called_once()


def test_shutdown_with_no_output_does_not_latch_or_send_commands(held_robot):
    r = held_robot
    assert r.robot.stop_gripper_for_shutdown() == 0
    assert not r.robot._motion_stop.is_set() and not r.calls
