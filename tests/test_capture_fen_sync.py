import unittest
from unittest.mock import Mock

from src.core.game_state import GameState
from src.core import xiangqi


def empty_board():
    return [["." for _ in range(9)] for _ in range(10)]


class CaptureFenSyncTests(unittest.TestCase):
    def make_state(self):
        state = GameState()
        state.api_client.send_move_update_board = Mock()
        state.board = empty_board()
        state.board[0][4] = "b_K"
        state.board[9][4] = "r_K"
        state.turn = "r"
        state.move_number = 1
        return state

    def test_red_capture_removes_black_piece_and_posts_resulting_fen(self):
        state = self.make_state()
        state.board[5][0] = "r_C"
        state.board[2][0] = "b_N"

        state.process_human_move((0, 5), (0, 2), "r_C")

        self.assertEqual("r_C", state.board[2][0])
        self.assertIn("b_N", state.b_captured)
        state.api_client.send_move_update_board.assert_called_once_with(state.current_fen)
        self.assertNotIn("n", state.current_fen.split()[0])

    def test_black_capture_removes_red_piece_and_exposes_fen_for_one_api_post(self):
        state = self.make_state()
        state.turn = "b"
        state.board[2][0] = "b_C"
        state.board[5][0] = "r_N"
        expected, captured = xiangqi.make_temp_move(state.board, ((0, 2), (0, 5)))
        state.set_pending_ai_move(((0, 2), (0, 5)), expected, captured)

        self.assertTrue(state.commit_pending_ai_move())
        state.api_client.send_move_update_board(state.current_fen)

        self.assertEqual("b_C", state.board[5][0])
        self.assertIn("r_N", state.r_captured)
        state.api_client.send_move_update_board.assert_called_once_with(state.current_fen)
        self.assertNotIn("N", state.current_fen.split()[0])


if __name__ == "__main__":
    unittest.main()
