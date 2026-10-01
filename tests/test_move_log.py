import unittest
from unittest.mock import Mock

from src.core import xiangqi
from src.core.game_state import GameState
from src.ui.board_renderer import BLACK_PIECE_COLOR, RED_PIECE_COLOR, BoardRenderer


class MoveLogTests(unittest.TestCase):
    def make_state(self):
        state = GameState()
        state.api_client.send_move_update_board = Mock()
        state.board = xiangqi.get_board()
        return state

    def test_records_human_and_verified_ai_moves_for_the_feed(self):
        state = self.make_state()
        state.process_human_move((0, 6), (0, 5), "r_P")
        expected, captured = xiangqi.make_temp_move(state.board, ((0, 3), (0, 4)))
        state.set_pending_ai_move(((0, 3), (0, 4)), expected, captured)
        state.commit_pending_ai_move()

        self.assertEqual(
            [
                {"turn": "r", "src": (0, 6), "dst": (0, 5), "piece": "r_P"},
                {"turn": "b", "src": (0, 3), "dst": (0, 4), "piece": "b_P"},
            ],
            state.get_render_state()["recent_moves"],
        )

    def test_move_feed_format_and_side_colors_match_the_pieces(self):
        self.assertEqual("Xe a0 -> a1", BoardRenderer._format_move(
            {"piece": "b_R", "src": (0, 0), "dst": (0, 1)}
        ))
        self.assertEqual((220, 20, 60), RED_PIECE_COLOR)
        self.assertEqual((0, 0, 0), BLACK_PIECE_COLOR)

    def test_render_state_limits_the_feed_to_the_last_eight_moves(self):
        state = self.make_state()
        state.move_log = [
            {"turn": "r", "src": (index, 6), "dst": (index, 5), "piece": "r_P"}
            for index in range(9)
        ]

        recent_moves = state.get_render_state()["recent_moves"]

        self.assertEqual(8, len(recent_moves))
        self.assertEqual((1, 6), recent_moves[0]["src"])

    def test_reset_and_rollback_restore_the_display_log(self):
        state = self.make_state()
        state.save_rollback_state()
        state.process_human_move((0, 6), (0, 5), "r_P")
        state.handle_rollback()
        self.assertEqual([], state.move_log)

        state.reset_game()
        self.assertEqual([], state.move_log)


if __name__ == "__main__":
    unittest.main()
