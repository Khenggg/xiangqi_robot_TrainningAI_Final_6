import unittest

from src.core import xiangqi
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
from src.vision.player_turn_types import CommitRequest


class HumanCommitAiHandoffTests(unittest.TestCase):
    def test_accepted_commit_opens_exactly_one_ai_generation(self):
        class State:
            def __init__(self):
                self.board = xiangqi.get_board()
                self.turn = "r"
                self.game_over = False
                self.calls = 0

            def process_human_move(self, src, dst, piece):
                self.calls += 1
                self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
                self.turn = "b"

        state = State()
        coordinator = HumanMoveCommitCoordinator(state)
        request = CommitRequest(7, ((0, 6), (0, 5)))
        self.assertEqual("ACCEPTED", coordinator.try_commit(request, "r_P"))
        self.assertEqual("DUPLICATE", coordinator.try_commit(request, "r_P"))
        self.assertEqual(1, state.calls)
        self.assertEqual("b", state.turn)


if __name__ == "__main__":
    unittest.main()
