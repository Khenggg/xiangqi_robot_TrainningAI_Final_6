import unittest

from src.core import xiangqi
from src.vision.player_turn_arbiter import PlayerTurnArbiter
from src.vision.player_turn_types import BoardObservation, InteractionCapability, PlayerTurnState, Visibility


def moved(board, move=((0, 6), (0, 5))):
    return xiangqi.make_temp_move(board, move)[0]


class PlayerTurnArbiterTests(unittest.TestCase):
    def setUp(self):
        self.board = xiangqi.get_board()
        self.arbiter = PlayerTurnArbiter(clear_seconds=0.2, clear_samples=2,
                                         interaction_settle_seconds=0.5,
                                         idle_settle_seconds=0.6, idle_samples=3)
        self.arbiter.activate(self.board, InteractionCapability.AVAILABLE)

    def observation(self, at, layout, visibility=Visibility.CLEAR, **kwargs):
        return BoardObservation(at, tuple(tuple(row) for row in layout) if layout else None,
                                visibility, **kwargs)

    def test_lift_or_hand_never_completes_a_turn(self):
        lifted = [row[:] for row in self.board]
        lifted[6][0] = "."
        self.assertIsNone(self.arbiter.ingest(self.observation(0, lifted, Visibility.OCCLUDED,
                                                                 hand_or_object_present=True)))
        self.assertEqual(PlayerTurnState.INTERACTING_OR_OCCLUDED, self.arbiter.state)

    def test_returning_piece_to_origin_cancels_candidate(self):
        self.arbiter.ingest(self.observation(0, self.board, Visibility.OCCLUDED, hand_or_object_present=True))
        self.arbiter.ingest(self.observation(.1, self.board))
        self.arbiter.ingest(self.observation(.3, self.board))
        self.assertIsNone(self.arbiter.ingest(self.observation(.4, self.board)))
        self.assertEqual(PlayerTurnState.PLAYER_IDLE, self.arbiter.state)

    def test_move_after_hand_clear_requires_continuous_settle(self):
        target = moved(self.board)
        self.arbiter.ingest(self.observation(0, self.board, Visibility.OCCLUDED, hand_or_object_present=True))
        self.arbiter.ingest(self.observation(.1, target))
        self.arbiter.ingest(self.observation(.3, target))
        self.assertIsNone(self.arbiter.ingest(self.observation(.4, target)))
        self.assertIsNone(self.arbiter.ingest(self.observation(.6, target)))
        request = self.arbiter.ingest(self.observation(.9, target))
        self.assertIsNotNone(request)
        self.assertEqual(((0, 6), (0, 5)), request.move)

    def test_hand_returning_after_move_resets_settle_window(self):
        target = moved(self.board)
        self.arbiter.ingest(self.observation(0, target))
        self.arbiter.ingest(self.observation(.3, target))
        self.arbiter.ingest(self.observation(.4, target, Visibility.OCCLUDED, hand_or_object_present=True))
        self.arbiter.ingest(self.observation(.5, target))
        self.arbiter.ingest(self.observation(.7, target))
        self.assertIsNone(self.arbiter.ingest(self.observation(.8, target)))

    def test_no_hand_move_uses_longer_window(self):
        target = moved(self.board)
        self.assertIsNone(self.arbiter.ingest(self.observation(0, target)))
        self.assertIsNone(self.arbiter.ingest(self.observation(.3, target)))
        self.assertIsNone(self.arbiter.ingest(self.observation(.5, target)))
        self.assertIsNotNone(self.arbiter.ingest(self.observation(.6, target)))

    def test_unavailable_capability_cannot_activate(self):
        arbiter = PlayerTurnArbiter()
        self.assertEqual(PlayerTurnState.INACTIVE,
                         arbiter.activate(self.board, InteractionCapability.UNAVAILABLE))


if __name__ == "__main__":
    unittest.main()
