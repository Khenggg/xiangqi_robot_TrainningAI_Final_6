"""Recovery observes the controller automatically without manual stop approval."""
import ast
from copy import deepcopy
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.hardware.controlled_stop import ControlledStopCoordinator, StopRequest, StopResult
from src.hardware.hardware_manager import HardwareManager
from src.core.motion_worker import MotionWorker
from src.ui.input_handler import InputHandler


def main_tree():
    # Importing main.py would launch the UI and potentially initialize devices.
    return ast.parse(Path('main.py').read_text(encoding='utf-8-sig'))


def compile_branch(branch):
    isolated = ast.If(test=branch.test,
                      body=[node for node in branch.body if not isinstance(node, ast.Continue)],
                      orelse=[])
    return compile(ast.fix_missing_locations(ast.Module(body=[isolated], type_ignores=[])),
                   'main.py: actual event branch', 'exec')


@pytest.mark.parametrize('modifier', [0, pygame.KMOD_LCTRL, pygame.KMOD_RCTRL])
def test_plain_f8_pauses_but_ctrl_f8_has_no_recovery_dispatch(modifier):
    branches = [node for node in ast.walk(main_tree()) if isinstance(node, ast.If)
                and 'K_F8' in ast.unparse(node.test)]
    assert len(branches) == 1  # No second F8 binding hidden in exception recovery.
    hardware = SimpleNamespace(confirm_operator_stop=Mock())
    session_control = Mock()
    exec(compile_branch(branches[0]), dict(
        event=pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F8, mod=modifier),
        pygame=pygame, hw=hardware, session_control=session_control))
    hardware.confirm_operator_stop.assert_not_called()
    if modifier:
        session_control.request.assert_not_called()
    else:
        session_control.request.assert_called_once_with('pause')


@pytest.mark.parametrize('stop_state,running,expected', [
    ('unsafe', False, True), ('unsafe', True, False),
    ('safe', False, False), ('unfinished', False, False), ('absent', False, False),
])
def test_exception_f2_refreshes_controller_state_without_manual_approval(
        stop_state, running, expected):
    recovery = next(node for node in main_tree().body
                    if isinstance(node, ast.FunctionDef) and node.name == '_recover_shutdown_after_exception')
    branch = next(node for node in ast.walk(recovery) if isinstance(node, ast.If)
                  and 'item.key == pygame.K_F2' in ast.unparse(node.test))
    stop = None
    if stop_state != 'absent':
        stop = StopRequest('old uncertainty')
        if stop_state != 'unfinished':
            stop.finish(StopResult(stop_state == 'safe', False, 'test request'))
    hardware = SimpleNamespace(stop_coordinator=SimpleNamespace(request=stop),
                               motion_worker=SimpleNamespace(running=running),
                               refresh_stop_state=Mock(return_value=True))
    operator_worker = Mock()
    scope = dict(item=pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2),
                 pygame=pygame, hw=hardware, operator_worker=operator_worker,
                 _job_completed=Mock(), retry_requested=False)
    exec(compile_branch(branch), scope)
    assert scope['retry_requested']
    if expected:
        operator_worker.start.assert_called_once()
        operation, completed = operator_worker.start.call_args.args
        operation()
        hardware.refresh_stop_state.assert_called_once_with()
        assert completed is scope['_job_completed']
    else:
        operator_worker.start.assert_not_called()
        hardware.refresh_stop_state.assert_not_called()


@pytest.fixture
def shared_recovery(monkeypatch):
    from src.core.game_state import GameState
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *args: Mock(room_id=None))
    state = GameState()
    state.physical_sync_fault = state.snapshot_continue_required = True
    robot = SimpleNamespace(_gripper_pulse_active=False, send_controlled_stop=Mock(),
                            move_piece=Mock(), activate_physical_control=Mock())
    hardware = SimpleNamespace(robot=robot, simulation_runtime=None, dry_run=False,
        config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL', DRY_RUN=False),
        _piece_move_lock=threading.Lock(), motion_worker=None,
        backend=SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda: SimpleNamespace(
            connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state='IDLE', last_error=None))),
        verify_physical_board=Mock(return_value=False))
    coordinator = hardware.stop_coordinator = ControlledStopCoordinator(hardware)
    request = coordinator.request = StopRequest('uncertain old stop')
    request.finish(StopResult(False, False, 'reply unavailable'))
    observe = coordinator.observe_idle
    coordinator.observe_idle = Mock(side_effect=lambda: observe(timeout=.08))
    handler = InputHandler(state, hardware)
    handler._client_capabilities = Mock(return_value=dict(camera_enabled=True,
        simulation_enabled=True, viewer_enabled=True, robot_moves_enabled=True))
    yield SimpleNamespace(state=state, hw=hardware, handler=handler, coordinator=coordinator,
                          observe_idle=observe)
    state.close_journal()


def test_v_automatically_observes_idle_before_board_reconciliation(shared_recovery):
    r = shared_recovery
    r.handler.handle_keyboard(pygame.K_v)
    r.coordinator.observe_idle.assert_called_once_with()
    assert r.coordinator.request.result.safe
    r.hw.verify_physical_board.assert_called_once()
    r.hw.robot.send_controlled_stop.assert_not_called()
    r.hw.robot.move_piece.assert_not_called()
    r.hw.robot.activate_physical_control.assert_not_called()


def test_read_only_startup_stop_recovers_without_operator_approval_or_stop_ack(shared_recovery):
    r = shared_recovery
    request = r.coordinator.request
    assert not request.result.safe and not request.result.acknowledged
    assert r.coordinator.observe_idle() is None
    assert r.coordinator.request is request and request.result.safe
    assert not request.result.acknowledged
    assert r.hw.robot._gripper_pulse_active is False
    r.hw.robot.send_controlled_stop.assert_not_called()
    r.hw.robot.activate_physical_control.assert_not_called()


@pytest.mark.parametrize('temporary_receipt', [False, True])
def test_cleanup_refresh_discards_a_receipt_if_an_existing_stop_disappears(temporary_receipt):
    manager = HardwareManager.__new__(HardwareManager)
    receipt = object() if temporary_receipt else None
    coordinator = SimpleNamespace(request=object(), observe_idle=Mock(),
                                  discard_idle_observation=Mock())

    def observe():
        if temporary_receipt:
            # The old stop was cleared between the manager's initial check
            # and the observation, which therefore produced a scoped receipt.
            coordinator.request = None
        return receipt

    coordinator.observe_idle.side_effect = observe
    manager.stop_coordinator = coordinator
    manager.refresh_stop_state()
    coordinator.observe_idle.assert_called_once_with()
    if temporary_receipt:
        coordinator.discard_idle_observation.assert_called_once_with(receipt)
    else:
        coordinator.discard_idle_observation.assert_not_called()


def test_slow_telemetry_stream_can_repeat_a_sample_before_a_second_fresh_packet(shared_recovery):
    r = shared_recovery
    stamp = None
    calls = 0

    def measured():
        nonlocal stamp, calls
        calls += 1
        if stamp is None or calls >= 4:
            stamp = time.time()
        return SimpleNamespace(connected=True, joints_valid=True, measurement_timestamp=stamp,
                               motion_state='IDLE', last_error=None)

    r.hw.backend.get_state_snapshot.side_effect = measured
    assert r.observe_idle(timeout=.3) is None
    assert calls >= 4 and r.coordinator.request.result.safe
    r.hw.robot.send_controlled_stop.assert_not_called()


def test_unknown_dispatched_stop_is_not_promoted_to_safe_or_resent(shared_recovery):
    r = shared_recovery
    request = r.coordinator.request
    request.stop_dispatched = True
    r.handler.handle_keyboard(pygame.K_v)
    assert r.coordinator.request is request
    assert not request.result.safe and not request.result.acknowledged
    assert r.state.physical_sync_fault
    r.hw.verify_physical_board.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_not_called()
    r.hw.robot.move_piece.assert_not_called()
    r.hw.robot.activate_physical_control.assert_not_called()


def test_idle_motion_label_cannot_hide_controller_alarm(shared_recovery):
    r = shared_recovery
    r.hw.backend.get_state_snapshot.side_effect = lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(),
        motion_state='IDLE', last_error='Controller error: main=1, sub=29')
    r.handler.handle_keyboard(pygame.K_v)
    assert not r.coordinator.request.result.safe
    assert 'main=1' in r.state.status_message and 'sub=29' in r.state.status_message
    r.hw.verify_physical_board.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_not_called()


def test_new_stop_generation_during_existing_idle_check_invalidates_the_result(shared_recovery):
    r = shared_recovery
    request = r.coordinator.request
    snapshot = r.hw.backend.get_state_snapshot.side_effect
    changed = False

    def measured():
        nonlocal changed
        if not changed:
            changed = True
            assert r.coordinator.begin('new stop during idle observation') is request
        return snapshot()

    r.hw.backend.get_state_snapshot.side_effect = measured
    r.handler.handle_keyboard(pygame.K_v)
    assert changed
    assert r.coordinator.request is request and not request.result.safe
    assert r.state.physical_sync_fault
    r.hw.verify_physical_board.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_not_called()


@pytest.mark.parametrize('condition', ['moving', 'stale', 'duplicate', 'disconnected', 'worker', 'move_lock',
                                      'controller_fault', 'gripper'])
def test_automatic_recovery_cannot_bypass_controller_or_worker_state(shared_recovery, condition):
    r = shared_recovery
    stamp = time.time()
    if condition == 'worker':
        r.hw.motion_worker = SimpleNamespace(running=True, busy=True, _thread=None)
    elif condition == 'move_lock':
        r.hw._piece_move_lock.acquire()
    elif condition == 'gripper':
        r.hw.robot._gripper_pulse_active = True
    else:
        r.hw.backend.get_state_snapshot.side_effect = lambda: SimpleNamespace(
            connected=condition != 'disconnected', joints_valid=True,
            measurement_timestamp=stamp - 2 if condition == 'stale'
                else stamp if condition == 'duplicate' else time.time(),
            motion_state='MOVING' if condition == 'moving' else 'ERROR' if condition == 'controller_fault' else 'IDLE',
            last_error='Controller error: main=1, sub=29' if condition == 'controller_fault' else None)
    try:
        r.handler.handle_keyboard(pygame.K_v)
        assert not r.coordinator.request.result.safe
        assert r.state.physical_sync_fault
        r.hw.verify_physical_board.assert_not_called()
        r.hw.robot.send_controlled_stop.assert_not_called()
        r.hw.robot.move_piece.assert_not_called()
        if condition == 'gripper':
            assert r.hw.robot._gripper_pulse_active is True
        if condition == 'controller_fault':
            assert 'main=1' in r.state.status_message and 'sub=29' in r.state.status_message
            assert 'confirm the arm/gripper' not in r.state.status_message
    finally:
        if condition == 'move_lock':
            r.hw._piece_move_lock.release()


def test_unrelated_keys_do_not_refresh_controller_or_change_stop_result(shared_recovery):
    r = shared_recovery
    r.handler.handle_keyboard(pygame.K_F8)
    r.handler.handle_keyboard(pygame.K_F7)
    r.coordinator.observe_idle.assert_not_called()
    assert not r.coordinator.request.result.safe


@pytest.mark.parametrize('action', ['reset', 'surrender'])
def test_deferred_session_action_v_refreshes_idle_before_reconciliation(shared_recovery, action):
    r = shared_recovery
    r.handler.session_control = SimpleNamespace(action=action)
    r.state.pending_ai_move = {'move': ((0, 3), (0, 4)),
                               'expected_board': deepcopy(r.state.board), 'captured_piece': '.'}
    pending = r.state.pending_ai_move
    r.handler.handle_keyboard(pygame.K_v)
    r.coordinator.observe_idle.assert_called_once_with()
    assert r.coordinator.request.result.safe
    r.hw.verify_physical_board.assert_called()
    assert r.state.pending_ai_move is pending
    r.hw.robot.move_piece.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_not_called()


def test_gameplay_and_cleanup_never_dispatch_manual_stop_confirmation():
    for path in ('src/ui/input_handler.py', 'main.py'):
        tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                       and node.func.attr in {'confirm_operator_stop', '_confirm_stopped_for_operator'}
                       for node in ast.walk(tree)), path


@pytest.mark.parametrize('operator_retry,safe', [(True, False), (True, True), (False, False)])
def test_mode_disposal_refreshes_idle_without_manual_approval_in_startup_worker(operator_retry, safe):
    function = next(node for node in main_tree().body
                    if isinstance(node, ast.FunctionDef) and node.name == '_begin_mode_disposal')
    compiled = compile(ast.Module(body=[function], type_ignores=[]), 'main.py: mode disposal', 'exec')
    request = StopRequest('mode teardown stopped uncertainly')
    request.finish(StopResult(safe, False, 'mock stop result'))
    worker = MotionWorker()
    observed = []

    def refresh():
        assert threading.current_thread() is worker._thread
        observed.append('refresh')

    def dispose():
        assert threading.current_thread() is worker._thread
        observed.append('dispose')
        return True

    hardware = SimpleNamespace(stop_coordinator=SimpleNamespace(request=request),
                               cam_monitor=None, refresh_stop_state=Mock(side_effect=refresh))
    disposal = SimpleNamespace(run=Mock(side_effect=dispose))
    finished = Mock()
    scope = dict(mode_disposal=disposal, mode_switching=False, mode_switch_failed=operator_retry,
                 startup_worker=worker, hw=hardware, state=SimpleNamespace(set_status=Mock()),
                 _finish_mode_disposal=finished)
    exec(compiled, scope)
    try:
        scope['_begin_mode_disposal']()
        deadline = time.monotonic() + 2
        while worker.busy and time.monotonic() < deadline:
            worker.poll()
            time.sleep(.005)
        assert not worker.busy
        finished.assert_called_once_with(True, None)
        assert observed == (['refresh', 'dispose'] if operator_retry and not safe else ['dispose'])
        if operator_retry and not safe:
            hardware.refresh_stop_state.assert_called_once_with()
        else:
            hardware.refresh_stop_state.assert_not_called()
    finally:
        worker.close()
