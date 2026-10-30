"""Offline integration contracts for the approved physical rollback flow."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.core.game_state import GameState
from src.core import xiangqi
from src.core.rollback_runtime import RollbackRuntime
from src.api.simulation_client import TuongKyDaiSuClient
from src.ui.input_handler import InputHandler
from copy import deepcopy
import pygame


def state_and_cycle():
    state = GameState()
    state.api_client = Mock(room_id='room', token='')
    state.api_client.queue_fen_commit.return_value = True
    initial = [row[:] for row in state.board]
    state.process_human_move((0, 6), (0, 5), 'r_P')
    after, victim = xiangqi.make_temp_move(state.board, ((0, 3), (0, 4)))
    state.set_pending_ai_move(((0, 3), (0, 4)), after, victim)
    state.commit_pending_ai_move()
    return state, initial


class RollbackIntegrationTests(unittest.TestCase):
    def setup_physical_cycle(self, directory, *, async_motion=False):
        state = GameState()
        client = TuongKyDaiSuClient('http://invalid', 'fixture')
        client.refresh_sync = Mock()
        client.room_id = 'original-room'
        state.api_client = client
        runtime = state.rollback_runtime
        runtime.configure(Path(directory) / 'rollback.json')
        initial = deepcopy(state.board)
        state.process_human_move((0, 6), (0, 5), 'r_P')
        expected, victim = xiangqi.make_temp_move(state.board, ((0, 3), (0, 4)))
        state.set_pending_ai_move(((0, 3), (0, 4)), expected, victim)
        actual = deepcopy(expected)
        motions = []

        def proof(board, allowed_missing_cells=(), **kwargs):
            allowed = set(allowed_missing_cells)
            matched = all(actual[r][c] == board[r][c] or
                          ((c, r) in allowed and actual[r][c] == '.')
                          for r in range(10) for c in range(9))
            return dict(matched=matched, complete=matched and actual == [list(row) for row in board], errors=[])

        def motion(sc, sr, dc, dr, capture, **kwargs):
            self.assertEqual(expected, state.board, 'Logical state changed during partial motion')
            self.assertEqual('.', actual[dr][dc])
            self.assertFalse(capture)
            motions.append(((sc, sr), (dc, dr)))
            actual[dr][dc], actual[sr][sc] = actual[sr][sc], '.'

        hardware = SimpleNamespace(config=SimpleNamespace(VISUAL_MOTION_ASYNC_ENABLED=async_motion),
            robot=SimpleNamespace(verify_rollback_ready=Mock(return_value={'ready': True}), move_piece=motion),
            verify_rollback_board=proof,
            get_robot_center_pick_targets=lambda cells: {'moving': SimpleNamespace(
                col=cells['moving'][0]+.05, row=cells['moving'][1])},
            capture_baseline_if_needed=Mock(return_value=True))
        handler = InputHandler(state, hardware)
        self.assertTrue(handler._finalize_pending_ai_move('Your turn', (0, 120, 0)))
        return state, runtime, hardware, handler, initial, actual, motions

    def test_z_runs_whole_cycle_red_then_black_and_is_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            self.assertTrue(runtime.eligibility()[0])
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual([((0, 5), (0, 6)), ((0, 4), (0, 3))], motions)
            self.assertEqual(initial, actual)
            self.assertEqual(initial, state.board)
            self.assertEqual('DONE', runtime.coordinator.phase)
            self.assertFalse(runtime.eligibility()[0])
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual(2, len(motions))
            self.assertFalse(handler.poll_board_stability() if runtime.blocked else state.can_start_ai_turn())
            self.assertFalse(state.ai_retry_requested)

    def test_latest_partial_cycle_revokes_previous_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            previous = runtime.cycle
            state.process_human_move((2, 6), (2, 5), 'r_P')
            self.assertEqual('INVALIDATED', previous.status)
            self.assertNotEqual(previous.cycle_id, runtime.cycle.cycle_id)
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual([], motions)
            self.assertFalse(runtime.eligibility()[0])

    def test_no_move_space_cannot_overwrite_latest_verified_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            original = runtime.cycle.to_dict()
            hw.yolo_detector = hw.cam_monitor = None
            self.assertFalse(handler._handle_space_key())
            state.save_rollback_state()
            self.assertEqual(original, runtime.cycle.to_dict())
            self.assertTrue(runtime.eligibility()[0])

    def test_gameplay_buttons_and_normal_poll_cannot_mutate_partial_rollback(self):
        from src.ui.board_renderer import BTN_NEW_GAME_RECT, BTN_SURRENDER_RECT
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            original = hw.robot.move_piece
            def lost(*args, **kwargs):
                original(*args, **kwargs)
                raise TimeoutError('lost ACK')
            hw.robot.move_piece = lost
            handler.handle_keyboard(pygame.K_z)
            held = deepcopy(state.board)
            state.api_client.end_match = Mock()
            for key in (pygame.K_z, pygame.K_m, pygame.K_t):
                handler.handle_keyboard(key)
            for button in (BTN_NEW_GAME_RECT, BTN_SURRENDER_RECT):
                handler.handle_mouse_down(*button.center)
            self.assertFalse(handler.poll_board_stability())
            self.assertFalse(handler.try_auto_confirm_move())
            self.assertFalse(state.reset_game(hw))
            self.assertEqual(held, state.board)
            self.assertEqual(1, len(motions))
            self.assertFalse(state.emergency_mode)
            self.assertFalse(state.pick_test_mode)
            state.api_client.end_match.assert_not_called()

    def test_async_worker_owns_start_gate_without_blocking_caller(self):
        import threading
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory, async_motion=True)
            entered, release = threading.Event(), threading.Event()
            original = hw.verify_rollback_board
            def slow(*args, **kwargs):
                entered.set()
                release.wait(10)
                return original(*args, **kwargs)
            hw.verify_rollback_board = slow
            handler.handle_keyboard(pygame.K_z)
            try:
                self.assertTrue(entered.wait(5))
                self.assertTrue(state.physical_motion_busy)
                self.assertEqual(0, len(motions))
                handler.handle_keyboard(pygame.K_z)
            finally:
                # Always stop the fake worker before TemporaryDirectory removes
                # its journal, even if a responsiveness assertion failed.
                release.set()
                handler._motion_thread.join(10)
            self.assertFalse(handler._motion_thread.is_alive())
            self.assertEqual('DONE', runtime.coordinator.phase)
            self.assertEqual(2, len(motions))

    def test_failed_z_baseline_preparation_retries_before_any_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            # Baseline readiness for rollback is checked only after Z.
            hw.capture_baseline_if_needed.return_value = False
            handler.handle_keyboard(pygame.K_z)
            self.assertTrue(runtime.blocked)
            self.assertFalse(runtime.eligibility()[0])
            self.assertEqual([], motions)
            hw.capture_baseline_if_needed.return_value = True
            handler.handle_keyboard(pygame.K_v)
            self.assertFalse(runtime.blocked)
            self.assertEqual('DONE', runtime.coordinator.phase)
            self.assertEqual(2, len(motions))

    def test_outbox_failure_locks_new_moves_until_durable_s0_enqueue(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            queue = state.api_client.queue_fen_commit
            state.api_client.queue_fen_commit = Mock(return_value=False)
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual(initial, state.board)
            self.assertTrue(runtime.pending_sync)
            self.assertTrue(runtime.blocked)
            handler.handle_keyboard(pygame.K_m)
            self.assertFalse(state.emergency_mode)
            state.api_client.queue_fen_commit = queue
            runtime.retry_pending_sync(force=True)
            self.assertFalse(runtime.blocked)
            self.assertEqual(initial, state.board)
            self.assertEqual(2, len(motions))

    def test_dry_run_commit_never_enqueues_a_real_provider_update(self):
        state, _ = state_and_cycle()
        with patch('config.DRY_RUN', True):
            state.rollback_runtime._commit(state.rollback_runtime.cycle.s0, 'dry-commit')
        state.api_client.queue_fen_commit.assert_not_called()
        self.assertFalse(state.rollback_runtime.pending_sync)

    def test_restart_after_local_commit_loads_s0_without_any_arm_command(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            handler.handle_keyboard(pygame.K_z)
            recovered = GameState()
            recovered.api_client = TuongKyDaiSuClient('http://invalid', 'fixture')
            recovered.api_client.refresh_sync = Mock()
            self.assertTrue(recovered.rollback_runtime.configure(Path(directory) / 'rollback.json'))
            self.assertEqual(initial, recovered.board)
            self.assertEqual('original-room', recovered.api_client.room_id)
            self.assertTrue(recovered.rollback_runtime.blocked)
            self.assertFalse(recovered.can_start_ai_turn())
            self.assertEqual(2, len(motions))
            recovered.rollback_runtime.attach_hardware(hw)
            recovered.rollback_runtime.resume(empty_gripper_confirmed=True)
            self.assertFalse(recovered.rollback_runtime.blocked)
            self.assertEqual(2, len(motions))

    def test_partial_failure_restart_keeps_s2_and_does_not_replay_first_step(self):
        with tempfile.TemporaryDirectory() as directory:
            state, runtime, hw, handler, initial, actual, motions = self.setup_physical_cycle(directory)
            s2 = deepcopy(state.board)
            original = hw.robot.move_piece
            def lost(*args, **kwargs):
                original(*args, **kwargs)
                if len(motions) == 1:
                    raise TimeoutError('lost acknowledgement after physical placement')
            hw.robot.move_piece = lost
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual(s2, state.board)
            self.assertEqual(1, len(motions))
            recovered = GameState()
            recovered.api_client = TuongKyDaiSuClient('http://invalid', 'fixture')
            recovered.api_client.refresh_sync = Mock()
            self.assertTrue(recovered.rollback_runtime.configure(Path(directory) / 'rollback.json'))
            self.assertEqual(s2, recovered.board)
            recovered.rollback_runtime.attach_hardware(hw)
            recovered.rollback_runtime.resume()
            self.assertEqual(1, len(motions))
            recovered.rollback_runtime.resume(empty_gripper_confirmed=True)
            self.assertEqual(2, len(motions))
            self.assertEqual(initial, recovered.board)

    def test_complete_logical_cycle_can_request_z_without_pre_scanning(self):
        state, _ = state_and_cycle()
        self.assertTrue(state.rollback_runtime.eligibility()[0])
        self.assertEqual('BUILDING', state.rollback_runtime.cycle.status)
        self.assertIsNotNone(state.rollback_runtime.cycle)

    def test_emergency_cycle_cannot_become_physical_rollback(self):
        state = GameState()
        state.api_client = Mock(room_id='room', token='')
        state.process_emergency_move((0, 6), (0, 5), 'r_P')
        self.assertIsNone(state.rollback_runtime.cycle)

    def test_commit_restores_s0_once_and_preserves_audit(self):
        state, initial = state_and_cycle()
        runtime = state.rollback_runtime
        cycle = runtime.cycle
        runtime._commit(cycle.s0, 'commit-test')
        runtime._commit(cycle.s0, 'commit-test')
        self.assertEqual(initial, state.board)
        self.assertEqual('r', state.turn)
        self.assertEqual([], state.move_history)
        self.assertEqual(2, len([e for e in runtime.move_audit if e.get('rolled_back')]))
        self.assertFalse(state.can_start_ai_turn())
        state.api_client.queue_fen_commit.assert_called_once()

    def test_blocked_runtime_rejects_human_and_ai(self):
        state = GameState()
        state.rollback_runtime.recovery_error = 'journal unreadable'
        state.human_commit_generation = 1
        self.assertFalse(state.can_start_ai_turn())
        from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
        request = SimpleNamespace(turn_token=(0, 1, 0), move=((0, 6), (0, 5)))
        self.assertEqual('PHYSICAL_SYNC_REQUIRED', HumanMoveCommitCoordinator(state).try_commit(request))

    def test_outbox_commit_survives_restart_without_duplicate_logical_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'outbox.json'
            client = TuongKyDaiSuClient('http://invalid', 'fixture')
            client.room_id = 'room'
            client.configure_outbox(path)
            with patch.object(client, 'refresh_sync'):
                self.assertTrue(client.queue_fen_commit('s0', 'id', 3))
                sequence = client._sync_sequence
                self.assertTrue(client.queue_fen_commit('s0', 'id', 3))
                self.assertEqual(sequence, client._sync_sequence)
            other = TuongKyDaiSuClient('http://invalid', 'fixture')
            other.room_id = 'room'
            self.assertTrue(other.configure_outbox(path))
            with patch.object(other, 'refresh_sync'):
                self.assertTrue(other.queue_fen_commit('s0', 'id', 3))
                self.assertEqual(sequence, other._sync_sequence)


if __name__ == '__main__':
    unittest.main()
