"""Audit PHYSICAL gameplay with fake SDK/camera only; never open a device/socket."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config
from src.core import xiangqi
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.hardware.rpc_transport import RpcOutcomeUnknown
from src.ui.input_handler import InputHandler
from src.vision.camera_monitor import CameraMonitor
from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator


def new_state():
    return GameState()


def arm_with_fake_sdk(*, bad_home=False, missing_bin=False):
    arm = FR5Robot(dry_run=False)
    arm.connected = True
    arm.robot = Mock()
    for name in ('Mode', 'RobotEnable', 'MoveCart', 'MoveJ', 'SetToolDO'):
        getattr(arm.robot, name).return_value = 0
    arm.robot.GetRobotTeachingPoint.return_value = (
        0, [-20., 340., 200., 180., 0., 0.] + [0.] * 6 + [arm.tool_num, 9 if bad_home else arm.user_num])
    arm.teaching_points = {
        name: dict(pose=[x, y, 10., 180., 0., 0.], joints=[0.] * 6,
                   tool=arm.tool_num, user=arm.user_num)
        for name, x, y in [('R1', -200., 500.), ('R2', -200., 180.),
                           ('R3', 160., 180.), ('R4', 160., 500.)]}
    if not missing_bin:
        arm.teaching_points['R_Trash'] = dict(pose=[0., 0., 200., 180., 0., 0.],
            joints=[0.] * 6, tool=arm.tool_num, user=arm.user_num)
    arm.telemetry_readiness = lambda **_: True
    return arm


def preflight_probe():
    bad_home = arm_with_fake_sdk(bad_home=True)
    enabled = bad_home.activate_physical_control(commissioned=True)
    first = bad_home.move_piece(7, 2, 4, 2, False)
    no_bin = arm_with_fake_sdk(missing_bin=True)
    bin_enabled = no_bin.activate_physical_control(commissioned=True)
    ordinary = no_bin.move_piece(0, 3, 0, 4, False)
    before = no_bin.robot.MoveCart.call_count + no_bin.robot.MoveJ.call_count
    capture = no_bin.move_piece(0, 4, 0, 5, True)
    after = no_bin.robot.MoveCart.call_count + no_bin.robot.MoveJ.call_count
    assert enabled and not first.success and 'HOMECHESS' in first.message
    assert bad_home.robot.MoveCart.call_count == 0
    assert bin_enabled and ordinary.success and not capture.success and before == after
    return dict(home=dict(enable_accepted=enabled, first_move_success=first.success,
                          reason=first.message, motion_calls=bad_home.robot.MoveCart.call_count),
                bin=dict(enable_accepted=bin_enabled, ordinary_move_success=ordinary.success,
                         capture_success=capture.success, reason=capture.message,
                         capture_motion_calls=after-before))


def recovery_probe():
    state = new_state()
    assert state.process_human_move((6, 6), (6, 5), 'r_P')
    state.mark_ai_turn_started()
    hw = SimpleNamespace(config=config, dry_run=False, simulation_runtime=None,
                         is_robot_ready=True, execute_piece_move=Mock(),
                         verify_physical_board=Mock(return_value=False),
                         physical_telemetry_ready=lambda **_: True,
                         stop_coordinator=SimpleNamespace(safe_for_release=lambda **_: True),
                         yolo_detector=object(), cam_monitor=object(),
                         capture_baseline_if_needed=Mock(return_value=True))
    assert not execute_ai_move(state, hw, ((0, 3), (0, 4)), dry_run=False)
    assert hw.execute_piece_move.call_count == 0
    hw.verify_physical_board.return_value = True
    handler = InputHandler(state, hw)
    cleared = handler._clear_failed_session()
    answer = dict(operator_clear_returned=cleared, status=state.status_message,
                  turn=state.turn, pending=state.pending_ai_move,
                  physical_fault=state.physical_sync_fault,
                  can_start_ai=state.can_start_ai_turn(), retry_requested=state.ai_retry_requested,
                  human_generation=state.human_commit_generation,
                  consumed_generation=state.ai_started_for_human_commit_generation,
                  dispatches=hw.execute_piece_move.call_count)
    assert cleared and not answer['can_start_ai'] and answer['turn'] == 'b'
    state.ai_retry_requested = True  # Equivalent to the explicit F5 handler.
    answer['explicit_F5_can_start_ai'] = state.can_start_ai_turn()
    assert answer['explicit_F5_can_start_ai']
    return answer


def camera_deadline_probe():
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    def read():
        entered.set()
        if not release.wait(2):
            raise RuntimeError('Probe watchdog')
        return True, frame
    cap = SimpleNamespace(isOpened=lambda: True, grab=lambda: True, read=read)
    board = xiangqi.get_board()
    recognizer = SimpleNamespace(extract_rectified_board=lambda frame, keypoints: (frame, None),
        recognize_layout=lambda frame: (board, board, [[1.] * 9 for _ in range(10)]))
    camera = CameraMonitor(cap, cchess_recognizer=recognizer, device_preference='cpu')
    camera._M = camera._inv_M = np.eye(3)
    hw = SimpleNamespace(camera_calibration_ready=True, cam_monitor=camera,
        recognize_board_state=lambda _: None,
        config=SimpleNamespace(VERIFY_BOARD_RETRY_TIMEOUT_SEC=.02,
                               VERIFY_BOARD_RETRY_POLL_SEC=0., VISUAL_PICK_SAMPLE_COUNT=3))
    result = []
    def run():
        try:
            result.append(HardwareManager.verify_physical_board(hw, board))
        finally:
            done.set()
    worker = threading.Thread(target=run)
    started = time.monotonic()
    worker.start()
    try:
        assert entered.wait(1)
        finished_by_four_times_budget = done.wait(.08)
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert not finished_by_four_times_budget and result == [False]
    return dict(budget_sec=.02, wait_before_releasing_camera_sec=.08,
                finished_by_four_times_budget=finished_by_four_times_budget,
                elapsed_sec=round(time.monotonic()-started, 3), result=result[0])


def lost_reply_probe():
    arm = arm_with_fake_sdk()
    arm.activate_physical_control(commissioned=True)
    arm.robot.MoveCart.side_effect = RpcOutcomeUnknown('Injected missing reply; command outcome unknown')
    result = arm.move_piece(0, 3, 0, 4, False)
    assert not result.success and arm.robot.MoveCart.call_count == 1
    return dict(success=result.success, fake_cart_attempts=arm.robot.MoveCart.call_count,
                last_completed_stage=getattr(result.last_completed_stage, 'name', None),
                reason=result.message, no_automatic_motion_replay=True)


def replay_probe():
    rng = random.Random(19)
    state = new_state()
    arm = arm_with_fake_sdk()
    arm.activate_physical_control(commissioned=True)
    hw = HardwareManager.__new__(HardwareManager)
    hw.config = config
    hw.dry_run = False
    hw.simulation_runtime = hw.stop_coordinator = hw.twin_bridge = None
    hw.robot = arm
    hw.game_state = state
    hw.profile = SimpleNamespace(robot_moves_enabled=True)
    hw._piece_move_lock = threading.Lock()
    hw.camera_calibration_ready = True
    hw.recognize_board_state = lambda frame: None  # Atomic observation path used below.
    hw.backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state='IDLE'))
    arm.telemetry_readiness = hw.physical_telemetry_ready
    real_board = [row[:] for row in state.board]
    sequence = 0
    target_cell = [None]
    source_temporarily_missing = [False]
    capture_retry_injected = [False]
    bin_operations = [0]
    def observation():
        nonlocal sequence
        sequence += 1
        return (time.monotonic(), object(), [], dict(success=True, quality_ok=True,
            board=[row[:] for row in real_board], observation_id=sequence))
    def raw_snapshot():
        return object(), []
    hw.cam_monitor = SimpleNamespace(get_fresh_observation=observation,
                                    get_fresh_pick_snapshot=raw_snapshot, _max_result_age_s=1.5)
    hw.center_pick_estimator = SimpleNamespace(
        estimate_pick_target=lambda detections, col, row: (
            None if source_temporarily_missing[0] else GridTarget(float(col), float(row), .99, 0.)),
        aggregate_targets=VisualPickEstimator.aggregate_targets, last_reason='accepted', last_measurement={})
    original_pick, original_place, original_bin = arm.pick_at, arm.place_at, arm.place_in_capture_bin
    def pick(col, row, visual_target=None):
        assert real_board[row][col] != '.'
        value = original_pick(col, row, visual_target)
        target_cell[0] = real_board[row][col]
        real_board[row][col] = '.'
        return value
    def place(col, row):
        value = original_place(col, row)
        real_board[row][col] = target_cell[0]
        target_cell[0] = None
        return value
    def bin_place(current_z=None):
        value = original_bin(current_z)
        target_cell[0] = None
        bin_operations[0] += 1
        if not capture_retry_injected[0]:
            source_temporarily_missing[0] = capture_retry_injected[0] = True
        return value
    arm.pick_at, arm.place_at, arm.place_in_capture_bin = pick, place, bin_place
    hw.is_cell_visually_clear = lambda cell: real_board[cell[1]][cell[0]] == '.'
    state._execution_binding_provider = lambda: dict(environment='PHYSICAL', calibration_token='fixture')
    rows, captures, capture_retries = [], 0, 0
    with tempfile.TemporaryDirectory(prefix='xiangqi-gameplay-audit-') as journal_root:
        state.attach_journal(journal_root, 'PHYSICAL', 'HUMAN_VS_ROBOT')
        try:
            for ply in range(240):
                if state.game_over:
                    break
                valid = xiangqi.find_all_valid_moves(state.turn, state.board)
                assert valid
                # Prefer captures to exercise bin/removal/refresh paths repeatedly.
                taking = [move for move in valid if state.board[move[1][1]][move[1][0]] != '.']
                move = rng.choice(taking or valid)
                old_revision = state.board_revision
                if state.turn == 'r':
                    real_board[:], _ = xiangqi.make_temp_move(real_board, move)
                    success = state.process_human_move(*move, state.board[move[0][1]][move[0][0]])
                else:
                    captures += bool(state.board[move[1][1]][move[1][0]] != '.')
                    state.mark_ai_turn_started()
                    success = execute_ai_move(state, hw, move, dry_run=False)
                    if not success and source_temporarily_missing[0]:
                        assert state.visual_pick_retry['stage'] == 'capture_removed'
                        assert state.visual_capture_checkpoint is not None
                        assert not state.physical_sync_fault and not state.move_sync_error
                        disposed_before_retry = bin_operations[0]
                        source_temporarily_missing[0] = False
                        # Same operation used by the explicit Y retry; preserve move identity.
                        success = execute_ai_move(state, hw, move, dry_run=False)
                        assert bin_operations[0] == disposed_before_retry
                        capture_retries += 1
                assert success, (ply, move, state.move_sync_error)
                assert state.board == real_board and state.board_revision == old_revision + 1
                assert state.pending_move is None and state.pending_ai_move is None
                rows.append(dict(ply=ply+1, move=move, revision=state.board_revision))
            committed = state._journal._db.execute('SELECT count(*) FROM committed_moves').fetchone()[0]
            assert committed == len(rows) and captures > 0 and capture_retries == 1
            return dict(plies=len(rows), robot_moves=len(rows)//2, robot_captures=captures,
                        durable_commits=committed, game_over=state.game_over,
                        winner=state.winner, capture_removed_retries=capture_retries,
                        repeated_capture_disposals=bin_operations[0]-captures,
                        fake_motion_calls=arm.robot.MoveCart.call_count + arm.robot.MoveJ.call_count,
                        camera_observations=sequence, board_equals_physical_fixture=True,
                        note='Legal deterministic replay, ideal camera and fake SDK; not a physical full-match test')
        finally:
            state.close_journal(clean=True)


def main():
    with ExitStack() as stack, redirect_stdout(io.StringIO()) as console:
        stack.enter_context(patch('src.hardware.robot_VIP.robot_sdk_core.RPC',
            side_effect=AssertionError('Real SDK is forbidden in this probe')))
        stack.enter_context(patch('src.core.game_state.TuongKyDaiSuClient',
            return_value=Mock(token='', room_id=None)))
        stack.enter_context(patch.object(config, 'ROBOT_BACKEND', 'PHYSICAL'))
        stack.enter_context(patch.object(config, 'DRY_RUN', False))
        stack.enter_context(patch.object(config, 'GAME_MODE', 'HUMAN_VS_ROBOT'))
        for name in ('GRIPPER_OPEN_MAX_PULSE_SEC','GRIPPER_CLOSE_PULSE_SEC',
                     'GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC','GRIPPER_OPEN_SETTLE_SEC',
                     'GRIPPER_CLOSE_SETTLE_SEC','GRIPPER_DIRECTION_DEADTIME_SEC'):
            stack.enter_context(patch.object(config, name, 0.))
        result = dict(environment='Windows / Python '+sys.version.split()[0], actual_hardware_calls=0,
            preflight=preflight_probe(), recovery=recovery_probe(), lost_reply=lost_reply_probe(),
            camera_deadline=camera_deadline_probe(), replay=replay_probe())
    root = Path(__file__).parent
    (root/'probe-console.txt').write_text(console.getvalue(), encoding='utf-8')
    (root/'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
