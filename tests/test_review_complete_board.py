"""Full layout gates for human moves, including SHADOW and occupancy fallback."""
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import config
import numpy as np
from src.core import xiangqi
from src.core.game_state import GameState
from src.vision.snapshot_detector import SnapshotDetector
from src.ui.input_handler import InputHandler


class CompleteBoardGateTests(unittest.TestCase):
    def setUp(self):
        self.board = xiangqi.get_board()
        self.detector = SnapshotDetector('missing-perspective.npy', {})
        self.detector._baseline_occ = [[True] * 9 for _ in range(10)]
        self.detector._baseline_time = 1.

    def observed(self, moves):
        board = self.board
        for move in moves:
            board, _ = xiangqi.make_temp_move(board, move)
        return board

    def test_unique_complete_legal_move_is_accepted(self):
        layout = self.observed([((0, 6), (0, 5))])
        self.assertEqual(self.detector.detect_move(object(), [], self.board, {'success': True, 'board': layout}), ((0, 6), (0, 5), 'r_P'))

    def test_two_red_moves_are_rejected_instead_of_first_candidate(self):
        layout = self.observed([((0, 6), (0, 5)), ((2, 6), (2, 5))])
        self.assertEqual(self.detector.detect_move(object(), [], self.board, {'success': True, 'board': layout}), (None, None, None))

    def test_unrelated_missing_piece_blocks_legal_candidate(self):
        layout = self.observed([((0, 6), (0, 5))])
        layout[0][0] = '.'
        self.assertEqual(self.detector.detect_move(object(), [], self.board, {'success': True, 'board': layout}), (None, None, None))

    def test_invalid_complete_layout_cannot_fall_through_to_occupancy_guess(self):
        layout = self.observed([((0, 6), (0, 5))])
        layout[0][0] = 'x'
        self.detector._compare_snapshots = Mock(return_value=((0, 6), (0, 5), 'r_P'))
        self.assertEqual(self.detector.detect_move(object(), [], self.board, {'success': True, 'board': layout}), (None, None, None))
        self.detector._compare_snapshots.assert_not_called()

    def test_shadow_stability_cannot_commit_a_repeatable_invalid_whole_board(self):
        state = GameState()
        state.api_client = Mock()
        layout = self.observed([((0, 6), (0, 5)), ((2, 6), (2, 5))])
        hw = SimpleNamespace(config=config, yolo_detector=self.detector, cam_monitor=Mock(),
                             cchess_recognizer=object(), recognize_board_state=Mock(return_value={'success': True, 'board': layout}),
                             is_board_occluded=Mock(return_value=False), interaction_capability=Mock(return_value='UNAVAILABLE'))
        hw.cam_monitor.get_fresh_snapshot.return_value = (np.zeros((10, 10, 3), np.uint8), [])
        handler = InputHandler(state, hw)
        clock = iter([10., 10., 10.7, 10.7, 11.5, 11.5])
        with patch('time.monotonic', side_effect=lambda: next(clock, 12.)):
            self.assertFalse(handler.poll_board_stability())
            self.assertFalse(handler.poll_board_stability())
            self.assertFalse(handler.poll_board_stability())
        self.assertEqual(state.turn, 'r')
        self.assertEqual(state.board, self.board)
        self.assertEqual(state.move_history, [])
        state.api_client.send_move_update_board.assert_not_called()


if __name__ == '__main__':
    unittest.main()
