"""Regression tests use isolated Python UCCI children; no hardware or network."""
import pathlib
import tempfile
import threading
import time
import types
import unittest

from src.ai.ai_controller import AIController
from src.ai.cloud_engine import CloudEngine
from src.ai.moonfish_engine import MoonfishEngine
from src.core import xiangqi


class EngineFailureRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, body):
        script = pathlib.Path(self.tmp.name) / "engine.py"
        script.write_text("import sys, time\n" + body, encoding="utf-8")
        engine = MoonfishEngine(str(script))
        engine.startup_timeout_sec = 0.3
        engine.search_timeout_sec = 0.3
        self.addCleanup(engine.stop)
        return engine

    def bounded(self, operation, engine, limit=1.2):
        result = []
        def run():
            try:
                result.append(("result", operation()))
            except Exception as error:
                result.append(("error", error))
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(limit)
        hung = thread.is_alive()
        if hung and engine.process is not None:
            engine.process.kill()
            thread.join(1)
        self.assertFalse(hung, "engine operation exceeded bounded deadline")
        return result[0]

    def test_silent_startup_times_out_and_reaps_child(self):
        engine = self.engine("time.sleep(60)\n")
        kind, error = self.bounded(engine.start, engine)
        self.assertEqual(kind, "error")
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("timeout", str(error).lower())
        self.assertIsNone(engine.process)

    def test_engine_banner_without_ucciok_is_not_ready(self):
        engine = self.engine("print('Moonfish', flush=True)\ntime.sleep(60)\n")
        kind, _ = self.bounded(engine.start, engine)
        self.assertEqual(kind, "error")
        self.assertFalse(engine._ready)

    def test_silent_search_times_out_and_invalidates_session(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): time.sleep(60)\n")
        self.bounded(engine.start, engine)
        kind, error = self.bounded(lambda: engine.pick_best_move(xiangqi.get_board(), 'b'), engine)
        self.assertEqual(kind, "error")
        self.assertIn("timeout", str(error).lower())
        self.assertFalse(engine._ready)
        self.assertIsNone(engine.process)

    def test_eof_during_search_is_failure_not_no_move(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): sys.exit(1)\n")
        self.bounded(engine.start, engine)
        kind, _ = self.bounded(lambda: engine.pick_best_move(xiangqi.get_board(), 'b'), engine)
        self.assertEqual(kind, "error")

    def test_stderr_is_drained_without_blocking_handshake(self):
        engine = self.engine("sys.stderr.write('diagnostic' * 200000)\nsys.stderr.flush()\nfor line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): print('bestmove a9a8', flush=True)\n elif line.strip() == 'quit': break\n")
        engine.startup_timeout_sec = 1
        kind, _ = self.bounded(engine.start, engine, limit=2)
        self.assertEqual(kind, "result")
        self.assertEqual(engine.pick_best_move(xiangqi.get_board(), 'b'), ((0, 0), (0, 1)))

    def test_explicit_no_move_remains_none(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): print('bestmove (none)', flush=True)\n elif line.strip() == 'quit': break\n")
        self.bounded(engine.start, engine)
        self.assertIsNone(engine.pick_best_move(xiangqi.get_board(), 'b'))

    def test_malformed_move_raises_error(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): print('bestmove z9a8', flush=True)\n elif line.strip() == 'quit': break\n")
        self.bounded(engine.start, engine)
        with self.assertRaises(RuntimeError):
            engine.pick_best_move(xiangqi.get_board(), 'b')

    def test_restarted_session_ignores_prior_output(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): print('bestmove a9a8', flush=True)\n elif line.strip() == 'quit': print('bestmove i9i8', flush=True); break\n")
        self.bounded(engine.start, engine)
        self.assertEqual(engine.pick_best_move(xiangqi.get_board(), 'b'), ((0, 0), (0, 1)))
        engine.stop()
        self.bounded(engine.start, engine)
        self.assertEqual(engine.pick_best_move(xiangqi.get_board(), 'b'), ((0, 0), (0, 1)))

    def test_stop_cancels_active_search(self):
        marker = pathlib.Path(self.tmp.name) / "searching"
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'):\n  open(" + repr(str(marker)) + ", 'w').close()\n  time.sleep(60)\n")
        self.bounded(engine.start, engine)
        engine.search_timeout_sec = 60
        errors = []
        def search():
            try:
                engine.pick_best_move(xiangqi.get_board(), 'b')
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=search, daemon=True)
        thread.start()
        deadline = time.monotonic() + 1
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(marker.exists())
        self.bounded(engine.stop, engine)
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertTrue(errors, "cancelled search must raise instead of reporting no legal move")

    def test_controller_propagates_failure_without_cloud_for_difficulty(self):
        def fail(*args, **kwargs):
            raise BrokenPipeError("broken child")
        def cloud(*args, **kwargs):
            self.fail("selected difficulty may not fall back to cloud")
        config = types.SimpleNamespace(AI_DIFFICULTY='impossible', MOONFISH_THINK_MS=1000, ENGINE_TYPE='HYBRID')
        controller = AIController(types.SimpleNamespace(pick_best_move=fail), types.SimpleNamespace(pick_best_move=cloud), config)
        with self.assertRaises(RuntimeError) as caught:
            controller.pick_move(xiangqi.get_board())
        self.assertIsInstance(caught.exception.__cause__, BrokenPipeError)

    def test_missing_local_engine_is_failure(self):
        config = types.SimpleNamespace(AI_DIFFICULTY='impossible', MOONFISH_THINK_MS=1000, ENGINE_TYPE='LOCAL')
        with self.assertRaises(RuntimeError):
            AIController(None, None, config).pick_move(xiangqi.get_board())

    def test_controller_restarts_only_on_next_requested_pick_after_timeout(self):
        engine = self.engine("for line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): time.sleep(60)\n")
        config = types.SimpleNamespace(AI_DIFFICULTY='impossible', MOONFISH_THINK_MS=1000)
        controller = AIController(engine, None, config)
        kind, _ = self.bounded(lambda: controller.pick_move(xiangqi.get_board()), engine)
        self.assertEqual(kind, 'error')
        self.assertIsNone(engine.process)
        pathlib.Path(engine.engine_path).write_text("import sys\nfor line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('go'): print('bestmove a9a8', flush=True)\n elif line.strip() == 'quit': break\n", encoding='utf-8')
        self.assertEqual(controller.pick_move(xiangqi.get_board()), ((0, 0), (0, 1)))

    def test_cloud_malformed_move_is_failure_not_no_move(self):
        for move in ('a9', 'z9a8', 'a9a8extra', None):
            with self.subTest(move=move), self.assertRaises(ValueError):
                CloudEngine('unused')._uci_to_move(move)

    def test_concurrent_searches_keep_position_and_response_paired(self):
        engine = self.engine("color = None\nfor line in sys.stdin:\n if line.strip() == 'ucci': print('ucciok', flush=True)\n elif line.startswith('position'): color = line.split()[-5]; time.sleep(0.04)\n elif line.startswith('go'): print('bestmove ' + ('a0a1' if color == 'w' else 'a9a8'), flush=True)\n elif line.strip() == 'quit': break\n")
        self.bounded(engine.start, engine)
        results = {}
        def pick(color):
            results[color] = engine.pick_best_move(xiangqi.get_board(), color)
        threads = [threading.Thread(target=pick, args=(color,)) for color in ('r', 'b')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(1)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results, {'r': ((0, 9), (0, 8)), 'b': ((0, 0), (0, 1))})


if __name__ == '__main__':
    unittest.main()
