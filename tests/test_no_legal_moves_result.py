"""Terminal positions use actual Xiangqi rules, never camera/robot access."""
import unittest
from unittest.mock import Mock

from src.core import xiangqi
from src.core.game_state import GameState
from src.core.rollback_cycle import StateSnapshot
from src.core.ai_turn_flow import AIJobResult, evaluate_ai_result
from src.ui.board_renderer import BoardRenderer
from src.ui.input_handler import InputHandler


class NoLegalMovesResultTests(unittest.TestCase):
    def state(self, attacker):
        state = GameState()
        state.api_client = Mock(room_id=None)
        state.board = [['.'] * 9 for _ in range(10)]
        state.board[0][4], state.board[9][4] = 'b_K', 'r_K'
        if attacker == 'b':
            state.board[8][3], state.board[7][5], state.board[5][4] = 'b_R', 'b_R', 'b_P'
            state.turn = 'b'
        else:
            state.board[1][3], state.board[2][5], state.board[4][4] = 'r_R', 'r_R', 'r_P'
            state.turn = 'r'
        state.update_fen_from_board()
        return state

    def test_human_stalemates_ai_ends_without_waiting_for_engine(self):
        state = self.state('r')
        self.assertTrue(xiangqi.is_valid_move((5, 2), (5, 1), state.board, 'r'))
        state.process_human_move((5, 2), (5, 1), 'r_R')
        self.assertFalse(xiangqi.is_king_in_check('b', state.board))
        self.assertEqual([], xiangqi.find_all_valid_moves('b', state.board))
        self.assertTrue(state.game_over)
        self.assertEqual(('r', 'NO_LEGAL_MOVES'), (state.winner, state.game_over_reason))
        evaluate_ai_result(state, AIJobResult(error='late timeout'))
        self.assertIsNone(state.ai_failure)
        state.api_client.end_match.assert_called_once_with(winner='RED', reason='CHECKMATE')

    def test_verified_ai_stalemates_human_and_skips_next_turn_baseline(self):
        state = self.state('b')
        # Start a real Red->Black cycle with production-like hardware attached.
        state.turn = 'r'
        state.board[9][4], state.board[8][4] = '.', 'r_K'
        hardware = Mock(config=None)
        handler = InputHandler(state, hardware)
        self.assertTrue(xiangqi.is_valid_move((4, 8), (4, 9), state.board, 'r'))
        state.process_human_move((4, 8), (4, 9), 'r_K')
        state.api_client.reset_mock()
        expected, victim = xiangqi.make_temp_move(state.board, ((5, 7), (5, 8)))
        state.set_pending_ai_move(((5, 7), (5, 8)), expected, victim)
        self.assertFalse(state.check_no_legal_moves())
        self.assertFalse(state.game_over)
        self.assertTrue(handler._finalize_pending_ai_move('Your turn', (0, 100, 180)))
        self.assertFalse(xiangqi.is_king_in_check('r', state.board))
        self.assertEqual([], xiangqi.find_all_valid_moves('r', state.board))
        self.assertEqual(('b', 'NO_LEGAL_MOVES'), (state.winner, state.game_over_reason))
        self.assertTrue(state.game_over)
        hardware.capture_baseline_if_needed.assert_not_called()
        self.assertFalse(state.rollback_runtime.needs_seal)
        self.assertEqual('INVALIDATED', state.rollback_runtime.cycle.status)
        state.api_client.end_match.assert_called_once_with(winner='BLACK', reason='CHECKMATE')
        events = [call[0] for call in state.api_client.mock_calls]
        self.assertLess(events.index('queue_fen'), events.index('end_match'))

    def test_emergency_black_move_also_checks_human_available_moves(self):
        state = self.state('b')
        state.process_emergency_move((5, 7), (5, 8), 'b_R')
        self.assertTrue(state.game_over)
        self.assertEqual('b', state.winner)
        state.api_client.end_match.assert_called_once_with(winner='BLACK', reason='CHECKMATE')

    def test_checkmate_with_king_still_present_ends_match(self):
        state = self.state('b')
        state.board[7][5] = '.'
        state.board[8][5] = 'b_R'
        state.board[8][4] = 'b_R'
        state.turn = 'r'
        self.assertTrue(xiangqi.is_king_in_check('r', state.board))
        self.assertEqual([], xiangqi.find_all_valid_moves('r', state.board))
        self.assertTrue(state.check_no_legal_moves())
        self.assertEqual('b', state.winner)

    def test_repeated_checks_do_not_send_duplicate_result(self):
        state = self.state('r')
        state.process_human_move((5, 2), (5, 1), 'r_R')
        self.assertTrue(state.check_no_legal_moves())
        self.assertFalse(state.handle_game_over('b', reason='RESIGN'))
        self.assertEqual('r', state.winner)
        state.api_client.end_match.assert_called_once()

    def test_recovery_guard_does_not_send_remote_result(self):
        state = self.state('b')
        state.board[7][5] = '.'
        state.board[8][5] = 'b_R'
        state.turn = 'r'
        state.rollback_runtime.restart_pending = True
        self.assertFalse(state.check_no_legal_moves())
        self.assertFalse(state.game_over)
        state.api_client.end_match.assert_not_called()

    def test_normal_position_is_not_a_loss(self):
        state = self.state('b')
        state.board = xiangqi.get_board()
        state.turn = 'r'
        self.assertFalse(state.check_no_legal_moves())
        state.api_client.end_match.assert_not_called()

    def test_notifications_separate_no_moves_from_surrender(self):
        for winner, title, loser in [('b', 'AI THẮNG', 'Bạn'), ('r', 'BẠN THẮNG', 'AI')]:
            self.assertEqual((title, loser + ' không còn nước đi hợp lệ.'),
                             BoardRenderer.game_over_text(winner, 'NO_LEGAL_MOVES'))
        self.assertEqual(('AI THẮNG', 'Bạn đã đầu hàng.'),
                         BoardRenderer.game_over_text('b', 'RESIGN'))

    def test_result_reason_roundtrips_without_changing_old_snapshot_signature(self):
        state = self.state('r')
        old = StateSnapshot.from_state(state)
        self.assertNotIn('game_over_reason', old.to_dict())
        self.assertEqual(old.signature, StateSnapshot.from_dict(old.to_dict()).signature)
        for reason in ('NO_LEGAL_MOVES', 'RESIGN'):
            state.game_over, state.winner, state.game_over_reason = True, 'b', reason
            snapshot = StateSnapshot.from_state(state)
            restored = self.state('r')
            StateSnapshot.from_dict(snapshot.to_dict()).apply_to(restored)
            self.assertEqual(reason, restored.game_over_reason)
            old.apply_to(restored)
            self.assertIsNone(restored.game_over_reason)
        invalid = old.to_dict()
        invalid['game_over_reason'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'result reason'):
            StateSnapshot.from_dict(invalid)


if __name__ == '__main__':
    unittest.main()
