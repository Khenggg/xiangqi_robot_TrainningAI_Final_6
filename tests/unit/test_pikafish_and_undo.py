"""
Unit tests for Pikafish Engine integration, ELO difficulty presets,
and GameState Undo Round functionality.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

import config
from src.core import xiangqi
from src.core.xiangqi import get_board
from src.core.game_state import GameState
from src.ai.ai_controller import AIController






class TestGameStateUndoRound(unittest.TestCase):
    """Kiểm tra chức năng hoàn tác (Undo round) của GameState."""

    def setUp(self):
        self.state = GameState(allow_mouse_move=True)

    def test_undo_on_empty_history_returns_false(self):
        """Khi chưa có nước đi, undo_round trả về False."""
        res = self.state.undo_round()
        self.assertFalse(res)
        self.assertIn("Chưa có nước đi", self.state.status_message)

    def test_undo_restores_state_correctly(self):
        """Undo khôi phục chính xác quân cờ, lượt đi, và lịch sử sau khi người chơi đi."""
        # Trạng thái ban đầu
        initial_board_copy = [row[:] for row in self.state.board]
        self.assertEqual(self.state.turn, 'r')

        # Con người đi Pháo đỏ: (1, 7) -> (4, 7)
        self.state.process_human_move((1, 7), (4, 7), "r_C")
        self.assertEqual(self.state.turn, 'b')
        self.assertEqual(len(self.state.history_snapshots), 1)
        self.assertEqual(len(self.state.move_history), 1)

        # Thực hiện Undo
        success = self.state.undo_round()
        self.assertTrue(success)
        self.assertEqual(self.state.board, initial_board_copy)
        self.assertEqual(self.state.turn, 'r')
        self.assertEqual(len(self.state.history_snapshots), 0)
        self.assertEqual(len(self.state.move_history), 0)
        self.assertIn("hoàn tác", self.state.status_message.lower())

    def test_undo_blocked_when_ai_thinking(self):
        """Không cho phép Undo khi AI đang suy nghĩ."""
        self.state.process_human_move((1, 7), (4, 7), "r_C")
        self.state.ai_thinking = True
        success = self.state.undo_round()
        self.assertFalse(success)
        self.assertIn("AI đang tính toán", self.state.status_message)




class TestCheckmateAndGameRules(unittest.TestCase):
    """Kiểm tra logic phát hiện Chiếu tướng và Chiếu bí (Checkmate / Stalemate)."""

    def test_initial_board_not_in_check_or_mate(self):
        board = get_board()
        self.assertFalse(xiangqi.is_king_in_check('r', board))
        self.assertFalse(xiangqi.is_king_in_check('b', board))
        self.assertFalse(xiangqi.is_checkmate('r', board))
        self.assertFalse(xiangqi.is_checkmate('b', board))

    def test_in_check_detection(self):
        """Xe đen áp sát Tướng đỏ tạo thế chiếu."""
        board = [['.' for _ in range(9)] for _ in range(10)]
        board[9][4] = 'r_K'  # Tướng đỏ ở (4, 9)
        board[0][0] = 'b_K'  # Tướng đen ở (0, 0)
        board[8][4] = 'b_R'  # Xe đen ở (4, 8) chiếu trực diện
        self.assertTrue(xiangqi.is_king_in_check('r', board))

    def test_checkmate_detection_and_game_over(self):
        """Thế cờ chiếu bí tuyệt sát: Tướng đỏ không còn đường đi hợp lệ."""
        board = [['.' for _ in range(9)] for _ in range(10)]
        board[9][4] = 'r_K'  # Tướng đỏ ở (4, 9)
        board[0][4] = 'b_K'  # Tướng đen ở (4, 0) đối diện cùng cột
        board[8][4] = 'b_R'  # Xe đen ở (4, 8)
        # Xe đen khác chặn đường thoát sang trái/phải
        board[9][3] = 'b_R'  # Ô (3, 9) bị chặn
        board[9][5] = 'b_R'  # Ô (5, 9) bị chặn
        
        # Tướng đỏ không thể đi đâu (ăn xe (4, 8) thì lộ mặt tướng với b_K ở (4, 0))
        self.assertTrue(xiangqi.is_king_in_check('r', board))
        self.assertTrue(xiangqi.is_checkmate('r', board))

        # Thử kích hoạt trên GameState
        state = GameState(allow_mouse_move=True)
        state.board = board
        state.turn = 'r'
        self.assertEqual(len(state.get_legal_moves_for_selected()), 0)
        state.handle_game_over('b', reason='CHIẾU BÍ')
        self.assertTrue(state.game_over)
        self.assertEqual(state.winner, 'b')
        self.assertEqual(state.game_over_reason, 'CHIẾU BÍ')


if __name__ == '__main__':
    unittest.main()
