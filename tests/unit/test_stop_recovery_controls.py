"""Removing Ctrl+F8 retains explicit, measured stop recovery through V/F2."""
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
def test_exception_f2_requests_read_only_confirmation_only_for_completed_unsafe_stop(
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
                               confirm_operator_stop=Mock(return_value=True))
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
        hardware.confirm_operator_stop.assert_called_once_with(approved=True)
        assert completed is scope['_job_completed']
    else:
        operator_worker.start.assert_not_called()
        hardware.confirm_operator_stop.assert_not_called()


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
            connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state='IDLE'))),
        verify_physical_board=Mock(return_value=False))
    coordinator = hardware.stop_coordinator = ControlledStopCoordinator(hardware)
    request = coordinator.request = StopRequest('uncertain old stop')
    request.finish(StopResult(False, False, 'reply unavailable'))
    hardware.confirm_operator_stop = Mock(side_effect=lambda **kwargs:
        coordinator.confirm_operator_stop(timeout=.08, **kwargs))
    handler = InputHandler(state, hardware)
    handler._client_capabilities = Mock(return_value=dict(camera_enabled=True,
        simulation_enabled=True, viewer_enabled=True, robot_moves_enabled=True))
    yield SimpleNamespace(state=state, hw=hardware, handler=handler, coordinator=coordinator)
    state.close_journal()


def test_operator_v_runs_measured_confirmation_before_board_reconciliation(shared_recovery):
    r = shared_recovery
    r.handler.handle_keyboard(pygame.K_v)
    r.hw.confirm_operator_stop.assert_called_once_with(approved=True)
    assert r.coordinator.request.result.safe
    r.hw.verify_physical_board.assert_called_once()
    r.hw.robot.send_controlled_stop.assert_not_called()
    r.hw.robot.move_piece.assert_not_called()
    r.hw.robot.activate_physical_control.assert_not_called()


@pytest.mark.parametrize('condition', ['moving', 'stale', 'duplicate', 'disconnected', 'worker', 'move_lock'])
def test_operator_v_cannot_bypass_missing_idle_or_worker_evidence(shared_recovery, condition):
    r = shared_recovery
    stamp = time.time()
    if condition == 'worker':
        r.hw.motion_worker = SimpleNamespace(running=True, busy=True, _thread=None)
    elif condition == 'move_lock':
        r.hw._piece_move_lock.acquire()
    else:
        r.hw.backend.get_state_snapshot.side_effect = lambda: SimpleNamespace(
            connected=condition != 'disconnected', joints_valid=True,
            measurement_timestamp=stamp - 2 if condition == 'stale'
                else stamp if condition == 'duplicate' else time.time(),
            motion_state='MOVING' if condition == 'moving' else 'IDLE')
    try:
        assert not r.handler._confirm_stopped_for_operator()
        assert not r.coordinator.request.result.safe
        assert r.state.physical_sync_fault
        r.hw.verify_physical_board.assert_not_called()
        r.hw.robot.send_controlled_stop.assert_not_called()
        r.hw.robot.move_piece.assert_not_called()
    finally:
        if condition == 'move_lock':
            r.hw._piece_move_lock.release()


def test_normal_keys_do_not_implicitly_approve_stop_recovery(shared_recovery):
    r = shared_recovery
    r.handler.handle_keyboard(pygame.K_F8)
    r.handler.handle_keyboard(pygame.K_F7)
    r.hw.confirm_operator_stop.assert_not_called()
    assert not r.coordinator.request.result.safe


@pytest.mark.parametrize('action', ['reset', 'surrender'])
def test_deferred_session_action_v_can_confirm_unsafe_stop_before_reconciliation(shared_recovery, action):
    r = shared_recovery
    r.handler.session_control = SimpleNamespace(action=action)
    r.state.pending_ai_move = {'move': ((0, 3), (0, 4)),
                               'expected_board': deepcopy(r.state.board), 'captured_piece': '.'}
    pending = r.state.pending_ai_move
    r.handler.handle_keyboard(pygame.K_v)
    r.hw.confirm_operator_stop.assert_called_once_with(approved=True)
    assert r.coordinator.request.result.safe
    r.hw.verify_physical_board.assert_called()
    assert r.state.pending_ai_move is pending
    r.hw.robot.move_piece.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_not_called()


def test_only_explicit_board_or_test_reconciliation_calls_operator_confirmation():
    tree = ast.parse(Path('src/ui/input_handler.py').read_text(encoding='utf-8-sig'))
    callers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == '_confirm_stopped_for_operator' for call in ast.walk(node)):
            callers.append(node.name)
    assert set(callers) == {'_reconcile_pick_test', '_reconcile_physical_sync_fault'}


@pytest.mark.parametrize('operator_retry,safe', [(True, False), (True, True), (False, False)])
def test_mode_disposal_only_confirms_on_explicit_retry_and_runs_in_startup_worker(operator_retry, safe):
    function = next(node for node in main_tree().body
                    if isinstance(node, ast.FunctionDef) and node.name == '_begin_mode_disposal')
    compiled = compile(ast.Module(body=[function], type_ignores=[]), 'main.py: mode disposal', 'exec')
    request = StopRequest('mode teardown stopped uncertainly')
    request.finish(StopResult(safe, False, 'mock stop result'))
    worker = MotionWorker()
    observed = []

    def confirm(*, approved):
        assert approved
        assert threading.current_thread() is worker._thread
        observed.append('confirm')

    def dispose():
        assert threading.current_thread() is worker._thread
        observed.append('dispose')
        return True

    hardware = SimpleNamespace(stop_coordinator=SimpleNamespace(request=request),
                               cam_monitor=None, confirm_operator_stop=Mock(side_effect=confirm))
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
        assert observed == (['confirm', 'dispose'] if operator_retry and not safe else ['dispose'])
        if operator_retry and not safe:
            hardware.confirm_operator_stop.assert_called_once_with(approved=True)
        else:
            hardware.confirm_operator_stop.assert_not_called()
    finally:
        worker.close()
