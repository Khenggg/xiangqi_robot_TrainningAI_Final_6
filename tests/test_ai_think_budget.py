"""Total AI deadlines cover startup/providers without accumulating stuck workers."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.ai.ai_controller import AIController, AIEngineError, ai_think_budget_seconds
from src.core import xiangqi


class AIThinkBudgetTests(unittest.TestCase):
    def config(self, **options):
        settings = dict(AI_DIFFICULTY="impossible", MOONFISH_THINK_MS=1000,
                        AI_MAX_THINK_SECONDS=0.08)
        settings.update(options)
        return SimpleNamespace(**settings)

    def test_budget_can_never_exceed_thirty_seconds(self):
        for value in (None, "bad", 0, -1, float("inf"), float("nan"), 90):
            self.assertEqual(30.0, ai_think_budget_seconds(self.config(AI_MAX_THINK_SECONDS=value)))
        self.assertEqual(0.08, ai_think_budget_seconds(self.config()))

    def test_hung_search_times_out_and_later_moves_do_not_spawn_more_searches(self):
        release = threading.Event()
        calls = []

        def search(*args, **kwargs):
            calls.append(True)
            release.wait(2)
            return ((0, 0), (0, 1))

        controller = AIController(SimpleNamespace(pick_best_move=search), None, self.config())
        self.addCleanup(release.set)
        started = time.monotonic()
        with self.assertRaisesRegex(AIEngineError, "deadline"):
            controller.pick_move(xiangqi.get_board())
        self.assertLess(time.monotonic() - started, 0.5)
        abandoned = controller._search_thread
        for _ in range(3):
            with self.assertRaisesRegex(AIEngineError, "busy"):
                controller.pick_move(xiangqi.get_board())
            self.assertIs(abandoned, controller._search_thread)
        self.assertEqual(1, len(calls))
        release.set()
        abandoned.join(1)
        self.assertFalse(abandoned.is_alive())
        self.assertEqual(((0, 0), (0, 1)), controller.pick_move(xiangqi.get_board()))

    def test_startup_consumes_search_budget_and_never_starts_late_search(self):
        release = threading.Event()
        engine = SimpleNamespace(_ready=False, start=lambda: release.wait(2), pick_best_move=Mock())
        controller = AIController(engine, None, self.config())
        self.addCleanup(release.set)
        with self.assertRaisesRegex(AIEngineError, "deadline"):
            controller.pick_move(xiangqi.get_board())
        release.set()
        controller._search_thread.join(1)
        engine.pick_best_move.assert_not_called()

    def test_hybrid_shares_one_budget_and_does_not_search_local_after_cloud_timeout(self):
        release = threading.Event()

        def cloud(*args):
            release.wait(2)
            raise TimeoutError("cloud stalled")

        local = SimpleNamespace(pick_best_move=Mock())
        controller = AIController(local, SimpleNamespace(pick_best_move=cloud),
                                  self.config(AI_DIFFICULTY="custom", ENGINE_TYPE="HYBRID"))
        self.addCleanup(release.set)
        with self.assertRaisesRegex(AIEngineError, "deadline"):
            controller.pick_move(xiangqi.get_board())
        release.set()
        controller._search_thread.join(1)
        local.pick_best_move.assert_not_called()

    def test_impossible_without_movetime_is_capped_at_remaining_total_budget(self):
        local = SimpleNamespace(pick_best_move=Mock(return_value=((0, 0), (0, 1))))
        controller = AIController(local, None, self.config(MOONFISH_THINK_MS=None))
        self.assertEqual(((0, 0), (0, 1)), controller.pick_move(xiangqi.get_board()))
        self.assertGreater(local.pick_best_move.call_args.kwargs["movetime_ms"], 0)
        self.assertLessEqual(local.pick_best_move.call_args.kwargs["movetime_ms"], 80)

    def test_oversized_local_movetime_is_capped_even_with_unbounded_config(self):
        local = SimpleNamespace(pick_best_move=Mock(return_value=((0, 0), (0, 1))))
        controller = AIController(local, None,
                                  self.config(MOONFISH_THINK_MS=100000, AI_MAX_THINK_SECONDS=90))
        controller.pick_move(xiangqi.get_board())
        self.assertLessEqual(local.pick_best_move.call_args.kwargs["movetime_ms"], 30000)


if __name__ == "__main__":
    unittest.main()
