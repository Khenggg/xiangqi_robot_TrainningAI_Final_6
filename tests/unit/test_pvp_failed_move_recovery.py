"""Operator V reconciles failed PvP moves without a previous StopMotion RPC."""
from copy import deepcopy
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

import config
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.core.robot_pvp import ROBOT_PVP_MODE, RobotPvPController
from src.core.session_profile import make_profile
from src.domain.game_move import MoveActor
from src.hardware.controlled_stop import ControlledStopCoordinator
from src.hardware.hardware_manager import HardwareManager
from src.ui.input_handler import InputHandler


def finish_ui_job(hw):
    deadline = time.monotonic() + 4
    while hw.motion_worker.busy and time.monotonic() < deadline:
        hw.motion_worker.poll()
        time.sleep(.005)
    assert not hw.motion_worker.busy


@pytest.fixture
def failed_pvp(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'GAME_MODE', ROBOT_PVP_MODE)
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',
                        lambda *args: Mock(token=None, room_id=None))
    state = GameState()
    state.session_profile = make_profile(ROBOT_PVP_MODE, 'PHYSICAL')
    state.attach_journal(tmp_path, 'PHYSICAL', ROBOT_PVP_MODE, fresh_start=True)
    robot = SimpleNamespace(connected=True, physical_motion_authorized=True,
        _activation_owned=False, _gripper_pulse_active=False,
        latch_motion_stop=Mock(), send_controlled_stop=Mock(return_value=0),
        go_to_home_chess=Mock(), gripper_ctrl=Mock(), activate_physical_control=Mock())
    observations = dict(condition='idle', timestamp=None)

    def snapshot():
        condition = observations['condition']
        stamp = observations['timestamp']
        return SimpleNamespace(connected=condition != 'disconnected', joints_valid=condition != 'invalid',
            measurement_timestamp=(time.time() - 2 if condition == 'stale'
                                   else stamp if condition == 'duplicate' else time.time()),
            motion_state='MOVING' if condition == 'moving' else 'ERROR' if condition == 'fault' else 'IDLE',
            last_error='Controller fault main=1 sub=29' if condition == 'fault' else None)

    hardware = SimpleNamespace(profile=state.session_profile, game_state=state,
        dry_run=False, simulation_runtime=None, robot=robot, is_robot_ready=True,
        config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL', DRY_RUN=False),
        motion_worker=MotionWorker(), _piece_move_lock=threading.Lock(),
        backend=SimpleNamespace(get_state_snapshot=Mock(side_effect=snapshot)),
        capture_baseline_if_needed=Mock(return_value=True),
        yolo_detector=SimpleNamespace(), cam_monitor=SimpleNamespace())
    coordinator = hardware.stop_coordinator = ControlledStopCoordinator(hardware)
    observe = getattr(coordinator, 'observe_operator_idle', None)
    if callable(observe):
        coordinator.observe_operator_idle = lambda **kwargs: observe(timeout=.2, **kwargs)
    hardware.confirm_operator_stop = lambda **kwargs: coordinator.confirm_operator_stop(timeout=.15, **kwargs)
    hardware.physical_telemetry_ready = lambda **kwargs: HardwareManager.physical_telemetry_ready(hardware, **kwargs)
    hardware.physical_recovery_block_reason = lambda: HardwareManager.physical_recovery_block_reason(hardware)
    physical = {'board': deepcopy(state.board)}

    def verify(board, **kwargs):
        matches = board == physical['board']
        if matches:
            state.note_verified_pending_board(board)
        return matches

    hardware.verify_physical_board = Mock(side_effect=verify)
    room = SimpleNamespace(code='ABC234', session='test-session', generation='test-peer',
                            connected=True, publish=Mock(), send=Mock(), close=Mock())
    pvp = RobotPvPController(state, hardware, room)
    hardware.pvp_controller = pvp
    handler = InputHandler(state, hardware)
    move = ((4, 6), (4, 5))
    state.mark_move_pending(state.create_move_context(*move, MoveActor.ROBOT))
    expected, captured = xiangqi.make_temp_move(state.board, move)
    state.set_pending_physical_move(move, expected, captured, moving_color='r')
    state.move_sync_error = 'Post-motion camera verification failed'
    state.recovery_required = state.physical_sync_fault = True
    state.manual_override_active = state.snapshot_continue_required = True
    state.mark_move_failed(state.move_sync_error)
    assert coordinator.request is None
    yield SimpleNamespace(state=state, hw=hardware, handler=handler, coordinator=coordinator,
                          physical=physical, expected=expected, observations=observations, pvp=pvp)
    finish_ui_job(hardware)
    request = coordinator.request
    if request is not None and request.thread is not None:
        request.thread.join(2)
    hardware.motion_worker.close()
    pvp.close()
    state.close_journal()


def press_v(recovery):
    recovery.handler.handle_keyboard(pygame.K_v)
    finish_ui_job(recovery.hw)


def assert_no_actuation(recovery):
    robot = recovery.hw.robot
    robot.send_controlled_stop.assert_not_called()
    robot.latch_motion_stop.assert_not_called()
    robot.go_to_home_chess.assert_not_called()
    robot.gripper_ctrl.assert_not_called()
    robot.activate_physical_control.assert_not_called()


def test_old_board_recovery_retires_pending_then_second_v_allows_red_reselection(failed_pvp):
    r = failed_pvp
    before, fen, ids = deepcopy(r.state.board), r.state.current_fen, dict(r.state.piece_ids)
    press_v(r)
    assert r.state.pending_move is None and r.state.pending_ai_move is None
    assert r.state.board == before and r.state.current_fen == fen and r.state.piece_ids == ids
    assert r.state.turn == 'r' and r.state.board_revision == 0 and not r.state.move_history
    assert r.state.physical_sync_fault and r.state.snapshot_continue_required
    assert not r.pvp.handle_click(4, 6)  # A second deliberate operator recovery is required.
    assert r.coordinator.request is None
    press_v(r)
    assert not r.state.recovery_required and not r.state.physical_sync_fault
    assert not r.state.snapshot_continue_required and not r.state.manual_override_active
    assert r.state.move_sync_error is None
    assert r.pvp.handle_click(4, 6) and r.state.selected_pos == (4, 6)
    assert r.state.board_revision == 0 and not r.state.move_history
    assert r.coordinator.request is None
    assert_no_actuation(r)


def test_expected_board_recovery_commits_red_once_and_never_replays_the_move(failed_pvp):
    r = failed_pvp
    r.physical['board'] = deepcopy(r.expected)
    press_v(r)
    assert r.state.pending_move is None and r.state.pending_ai_move is None
    assert r.state.board == r.expected and r.state.turn == 'b'
    assert r.state.board_revision == 1 and len(r.state.move_history) == 1
    assert r.state.last_move == ((4, 6), (4, 5))
    assert not r.state.recovery_required and not r.state.physical_sync_fault
    assert r.state.move_sync_error is None and r.coordinator.request is None
    press_v(r)
    assert r.state.board_revision == 1 and len(r.state.move_history) == 1
    assert r.state.turn == 'b'
    assert_no_actuation(r)


@pytest.mark.parametrize('condition', ['stale', 'moving', 'fault', 'disconnected', 'invalid', 'duplicate',
                                      'gripper', 'other_worker'])
def test_untrusted_robot_measurements_cannot_retire_pending_or_clear_recovery(failed_pvp, condition):
    r = failed_pvp
    pending, context = r.state.pending_ai_move, r.state.pending_move
    r.observations.update(condition=condition, timestamp=time.time())
    if condition == 'gripper':
        r.hw.robot._gripper_pulse_active = True
    if condition == 'other_worker':
        r.coordinator._worker_checks.append(lambda: False)
    press_v(r)
    assert r.state.pending_ai_move is pending and r.state.pending_move is context
    assert r.state.recovery_required and r.state.physical_sync_fault
    assert r.state.snapshot_continue_required and r.state.manual_override_active
    assert r.state.turn == 'r' and r.state.board_revision == 0
    assert r.coordinator.request is None
    if condition == 'gripper':
        assert r.hw.robot._gripper_pulse_active is True  # Observation cannot falsify the pulse state.
    assert_no_actuation(r)


def test_direct_reconciliation_does_not_create_operator_idle_approval(failed_pvp):
    r = failed_pvp
    pending = r.state.pending_ai_move
    r.handler._reconcile_physical_sync_fault()
    assert r.state.pending_ai_move is pending and r.state.recovery_required
    assert r.coordinator.request is None
    assert_no_actuation(r)


def test_recovery_proof_never_hides_a_later_real_stop_request(failed_pvp):
    r = failed_pvp
    press_v(r)
    press_v(r)
    assert r.state.pending_move is None and not r.state.physical_sync_fault
    assert r.coordinator.request is None
    assert_no_actuation(r)
    stop = r.coordinator.begin('new urgent stop after operator recovery', timeout=.5)
    assert stop.done.wait(2)
    stop.thread.join(2)
    assert stop.result.safe and stop.result.acknowledged
    r.hw.robot.send_controlled_stop.assert_called_once()
    r.hw.robot.latch_motion_stop.assert_called_once()
    r.hw.robot.go_to_home_chess.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()


def test_v_can_resume_a_camera_pause_without_a_pending_move_or_previous_stop(failed_pvp):
    r = failed_pvp
    r.state.clear_pending_ai_move()
    r.state.move_sync_error = None
    r.state.recovery_required = True
    r.state.physical_sync_fault = False
    r.state.snapshot_continue_required = r.state.manual_override_active = True
    press_v(r)
    assert not r.state.recovery_required and not r.state.physical_sync_fault
    assert not r.state.snapshot_continue_required and not r.state.manual_override_active
    assert r.pvp.handle_click(4, 6)
    assert r.state.turn == 'r' and r.state.board_revision == 0
    assert r.coordinator.request is None
    assert_no_actuation(r)


def test_urgent_stop_during_camera_verification_supersedes_the_temporary_observation(failed_pvp):
    r = failed_pvp
    pending = r.state.pending_ai_move
    verify = r.hw.verify_physical_board.side_effect
    stops = []

    def camera(board, **kwargs):
        if not stops:
            stops.append(r.coordinator.begin('urgent stop during operator camera check', timeout=1))
        return verify(board, **kwargs)

    r.hw.verify_physical_board.side_effect = camera
    press_v(r)
    assert len(stops) == 1
    assert r.coordinator.request is stops[0]
    assert not r.coordinator.request.observation_only
    assert stops[0].done.wait(2)
    stops[0].thread.join(2)
    assert r.state.pending_ai_move is pending and r.state.physical_sync_fault
    assert r.state.turn == 'r' and r.state.board_revision == 0
    r.hw.robot.send_controlled_stop.assert_called_once()
    r.hw.robot.latch_motion_stop.assert_called_once()
    r.hw.robot.go_to_home_chess.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.hw.robot.activate_physical_control.assert_not_called()


def test_urgent_stop_while_gathering_idle_samples_prevents_publishing_stale_proof(failed_pvp):
    r = failed_pvp
    pending = r.state.pending_ai_move
    snapshot = r.hw.backend.get_state_snapshot.side_effect
    stops = []
    starting_stop = [False]

    def measured():
        if not stops and not starting_stop[0]:
            starting_stop[0] = True
            stops.append(r.coordinator.begin('urgent stop while proving idle', timeout=1))
        return snapshot()

    r.hw.backend.get_state_snapshot.side_effect = measured
    press_v(r)
    assert len(stops) == 1
    assert r.coordinator.request is stops[0]
    assert not r.coordinator.request.observation_only
    assert stops[0].done.wait(2)
    stops[0].thread.join(2)
    assert r.state.pending_ai_move is pending and r.state.recovery_required
    assert r.state.physical_sync_fault and r.state.snapshot_continue_required
    r.hw.verify_physical_board.assert_not_called()
    r.hw.robot.send_controlled_stop.assert_called_once()
    r.hw.robot.go_to_home_chess.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
