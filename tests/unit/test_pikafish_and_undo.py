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
from src.ai.pikafish_engine import PikafishEngine, ELO_PRESETS, DEFAULT_ELO
from src.ai.ai_controller import AIController


class TestPikafishEngineLogic(unittest.TestCase):
    """Kiểm tra logic chuyển đổi FEN, toạ độ và điều khiển ELO của PikafishEngine."""

    def setUp(self):
        with patch("os.path.isfile", return_value=True):
            self.engine = PikafishEngine(config.PIKAFISH_EXE, config.PIKAFISH_NNUE)

    def test_elo_presets_and_defaults(self):
        """Kiểm tra danh sách nấc ELO từ 800 đến 3000."""
        self.assertIn(800, ELO_PRESETS)
        self.assertIn(1400, ELO_PRESETS)
        self.assertIn(3000, ELO_PRESETS)
        self.assertEqual(self.engine.get_current_elo(), DEFAULT_ELO)

    def test_set_elo_and_step_elo(self):
        """Kiểm tra gán ELO và tăng giảm nấc ELO."""
        self.engine.set_elo(800)
        self.assertEqual(self.engine.get_current_elo(), 800)
        self.assertIn("800", self.engine.get_elo_title())

        # Tăng 1 nấc -> 1100
        self.engine.step_elo(1)
        self.assertEqual(self.engine.get_current_elo(), 1100)

        # Đặt ELO không chuẩn (1550) -> làm tròn về nấc gần nhất (1400 hoặc 1700)
        self.engine.set_elo(1550)
        self.assertIn(self.engine.get_current_elo(), [1400, 1700])

        # Step xuống mức thấp nhất không bị âm
        self.engine.set_elo(800)
        self.engine.step_elo(-5)
        self.assertEqual(self.engine.get_current_elo(), 800)

        # Step lên mức cao nhất không vượt quá 3000
        self.engine.step_elo(20)
        self.assertEqual(self.engine.get_current_elo(), 3000)

    def test_board_to_fen_initial(self):
        """Kiểm tra sinh FEN từ bàn cờ ban đầu."""
        board = get_board()
        fen_red = self.engine.board_to_fen(board, 'r')
        self.assertTrue(fen_red.endswith(" w - - 0 1"))
        self.assertIn("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR", fen_red)

        fen_black = self.engine.board_to_fen(board, 'b')
        self.assertTrue(fen_black.endswith(" b - - 0 1"))

    def test_uci_to_move(self):
        """Kiểm tra giải mã nước cờ UCI dạng a0a1, b7e7."""
        # UCI: 'b7e7' -> col b=1, row 7 -> board col 1, row 9-7=2
        # dst: e7 -> col e=4, row 7 -> board col 4, row 9-7=2
        move = self.engine._uci_to_move("b7e7")
        self.assertEqual(move, ((1, 2), (4, 2)))

        # UCI: 'h2e2' (Pháo đỏ h2 vào trung lộ e2)
        # col h=7, row 2 -> board row 9-2=7
        move_red = self.engine._uci_to_move("h2e2")
        self.assertEqual(move_red, ((7, 7), (4, 7)))

        # Nước cờ rác hoặc không hợp lệ
        self.assertIsNone(self.engine._uci_to_move("x"))
        self.assertIsNone(self.engine._uci_to_move(""))


class TestPikafishExecution(unittest.TestCase):
    """Kiểm tra chạy engine thật nếu file exe tồn tại trên máy."""

    @unittest.skipUnless(os.path.isfile(config.PIKAFISH_EXE), "Pikafish binary not found")
    def test_real_engine_lifecycle_and_move(self):
        engine = PikafishEngine(config.PIKAFISH_EXE, config.PIKAFISH_NNUE)
        try:
            engine.start(threads=1, hash_mb=32)
            self.assertTrue(engine._ready)

            board = get_board()
            # Yêu cầu nước đi ở nấc Quán cóc 1400
            move = engine.pick_best_move(board, 'b', elo=1400)
            self.assertIsNotNone(move)
            src, dst = move
            self.assertEqual(len(src), 2)
            self.assertEqual(len(dst), 2)
            # Nước đi phải nằm trong bàn cờ 10x9
            self.assertTrue(0 <= src[0] <= 8 and 0 <= src[1] <= 9)
            self.assertTrue(0 <= dst[0] <= 8 and 0 <= dst[1] <= 9)
        finally:
            engine.stop()
            self.assertFalse(engine._ready)


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


class TestAIControllerWithELO(unittest.TestCase):
    """Kiểm tra AIController điều phối ELO mượt mà."""

    def test_controller_delegates_elo(self):
        mock_local = MagicMock()
        mock_local.set_elo.return_value = 1700
        mock_local.get_elo_title.return_value = "Cao thủ CLB (1700)"
        mock_local.get_current_elo.return_value = 1700

        ctrl = AIController(local_engine=mock_local, cloud_engine=None, config=config)
        elo, title = ctrl.set_elo(1700)
        self.assertEqual(elo, 1700)
        self.assertEqual(title, "Cao thủ CLB (1700)")

        # Thử pick_move
        board = get_board()
        mock_local.pick_best_move.return_value = ((1, 2), (4, 2))
        mock_local.current_elo = 1700
        move = ctrl.pick_move(board, 'b')
        self.assertEqual(move, ((1, 2), (4, 2)))
        mock_local.pick_best_move.assert_called_with(board, 'b', elo=1700)


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
