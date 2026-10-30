"""Logical rollback contracts; no camera, robot or provider is contacted."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from src.core import xiangqi
from src.core.game_state import GameState
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator


class ManualRollbackTests(unittest.TestCase):
    def state(self):
        state = GameState()
        state.api_client = Mock(room_id=None, token='')
        state.sync_remote_board = Mock(return_value=True)
        return state

    def black(self, state, src=(0, 3), dst=(0, 4)):
        after, victim = xiangqi.make_temp_move(state.board, (src, dst))
        state.set_pending_ai_move((src, dst), after, victim)
        self.assertTrue(state.commit_pending_ai_move())

    def pair(self):
        state = self.state()
        checkpoint = {k: deepcopy(getattr(state, k)) for k in state.manual_rollback.FIELDS}
        state.process_human_move((0, 6), (0, 5), 'r_P')
        self.black(state)
        return state, checkpoint

    def test_only_verified_completed_pair_is_eligible(self):
        state = self.state()
        self.assertFalse(state.manual_rollback.eligible)
        state.process_human_move((0, 6), (0, 5), 'r_P')
        self.assertFalse(state.manual_rollback.eligible)
        after, victim = xiangqi.make_temp_move(state.board, ((0, 3), (0, 4)))
        state.set_pending_ai_move(((0, 3), (0, 4)), after, victim)
        self.assertFalse(state.manual_rollback.eligible)
        state.commit_pending_ai_move()
        self.assertTrue(state.manual_rollback.eligible)

    def test_begin_preserves_live_position_and_complete_restores_once(self):
        state, checkpoint = self.pair()
        runtime = state.manual_rollback
        live = deepcopy(state.board)
        old_generation, old_epoch = state.human_commit_generation, state.game_epoch
        state.sync_remote_board.reset_mock()
        self.assertTrue(runtime.begin())
        token = runtime.session_token
        self.assertEqual(live, state.board)
        self.assertEqual(checkpoint['board'], runtime.target_board)
        copy = runtime.target_board
        copy[0][0] = '.'
        self.assertEqual(checkpoint['board'], runtime.target_board)
        self.assertFalse(runtime.complete(token - 1))
        self.assertTrue(runtime.complete(token))
        for key, value in checkpoint.items():
            self.assertEqual(value, getattr(state, key), key)
        self.assertGreater(state.game_epoch, old_epoch)
        self.assertGreater(state.human_commit_generation, old_generation)
        self.assertFalse(state.can_start_ai_turn())
        state.sync_remote_board.assert_called_once()
        self.assertFalse(runtime.complete(token))
        self.assertFalse(runtime.eligible)
        state.process_human_move((2, 6), (2, 5), 'r_P')
        self.assertTrue(state.can_start_ai_turn())

    def test_active_blocks_all_logical_gameplay_and_reset(self):
        state, _ = self.pair()
        self.assertTrue(state.manual_rollback.begin())
        before = deepcopy(state.board)
        self.assertFalse(state.process_human_move((2, 6), (2, 5), 'r_P'))
        self.assertFalse(state.process_emergency_move((2, 6), (2, 5), 'r_P'))
        self.assertFalse(state.reset_game())
        self.assertFalse(state.handle_game_over('b', 'RESIGN'))
        self.assertFalse(state.check_no_legal_moves())
        self.assertFalse(state.can_start_ai_turn())
        request = SimpleNamespace(turn_token=(state.game_epoch, state.human_commit_generation, 0),
                                  move=((2, 6), (2, 5)))
        self.assertEqual('PHYSICAL_SYNC_REQUIRED', HumanMoveCommitCoordinator(state).try_commit(request))
        self.assertEqual(before, state.board)

    def test_circles_for_each_side_and_captured_victims(self):
        state = self.state()
        state.board = [['.'] * 9 for _ in range(10)]
        for (c, r), piece in { (4, 0): 'b_K', (4, 9): 'r_K', (4, 5): 'r_P',
                              (1, 6): 'r_R', (1, 3): 'b_P', (2, 0): 'b_R',
                              (2, 6): 'r_P' }.items():
            state.board[r][c] = piece
        state.update_fen_from_board()
        initial = deepcopy(state.board)
        state.process_human_move((1, 6), (1, 3), 'r_R')
        self.black(state, (2, 0), (2, 6))
        self.assertTrue(state.manual_rollback.begin())
        circles = state.manual_rollback.render_state()['manual_rollback_circles']
        self.assertEqual(6, len(circles))
        self.assertIn(dict(square=(1, 3), side='b', role='restoration'), circles)
        self.assertIn(dict(square=(2, 6), side='r', role='restoration'), circles)
        self.assertTrue(state.manual_rollback.complete())
        self.assertEqual(initial, state.board)
        self.assertEqual([], state.r_captured)
        self.assertEqual([], state.b_captured)

    def test_recaptured_player_piece_has_return_circle_without_fake_source(self):
        state = self.state()
        state.board = [['.'] * 9 for _ in range(10)]
        for (c, r), piece in { (4, 0): 'b_K', (4, 9): 'r_K', (4, 5): 'r_P',
                              (1, 6): 'r_R', (1, 3): 'b_P', (1, 0): 'b_R' }.items():
            state.board[r][c] = piece
        state.update_fen_from_board()
        state.process_human_move((1, 6), (1, 3), 'r_R')
        self.black(state, (1, 0), (1, 3))
        self.assertTrue(state.manual_rollback.begin())
        circles = state.manual_rollback.render_state()['manual_rollback_circles']
        self.assertIn(dict(square=(1, 6), side='r', role='restoration'), circles)
        self.assertNotIn(dict(square=(1, 3), side='r', role='source'), circles)
        self.assertIn(dict(square=(1, 3), side='b', role='source'), circles)

    def test_terminal_emergency_reset_and_test_mode_are_not_undoable(self):
        for flag in ('game_over', 'emergency_mode', 'pick_test_mode', 'physical_sync_fault',
                     'physical_motion_busy', 'ai_thinking', 'pick_test_resume_required'):
            state, _ = self.pair()
            setattr(state, flag, True)
            self.assertFalse(state.manual_rollback.begin(), flag)
        state, _ = self.pair()
        state.reset_game()
        self.assertFalse(state.manual_rollback.eligible)
        state, _ = self.pair()
        state.process_emergency_move((2, 6), (2, 5), 'r_P')
        self.black(state, (2, 3), (2, 4))
        self.assertFalse(state.manual_rollback.eligible)

    def test_new_human_move_replaces_previous_checkpoint(self):
        state, _ = self.pair()
        newest = deepcopy(state.board)
        state.process_human_move((2, 6), (2, 5), 'r_P')
        self.black(state, (2, 3), (2, 4))
        self.assertTrue(state.manual_rollback.begin())
        self.assertEqual(newest, state.manual_rollback.target_board)

    def test_source_circle_disappears_after_piece_moves_away(self):
        state, _ = self.pair()
        state.manual_rollback.begin()
        board = deepcopy(state.board)
        board[5][0] = '.'
        state.manual_rollback.update_observed_board(board)
        circles = state.manual_rollback.render_state()['manual_rollback_circles']
        self.assertNotIn(dict(square=(0, 5), side='r', role='source'), circles)
        self.assertIn(dict(square=(0, 6), side='r', role='destination'), circles)


if __name__ == '__main__':
    unittest.main()
