import threading
import unittest

from src.core.game_state import GameState


class GameStateAsyncTests(unittest.TestCase):
    def test_fen_sync_returns_without_waiting_for_http(self):
        state = GameState()
        started = threading.Event()
        release = threading.Event()

        def slow_send(_fen):
            started.set()
            release.wait(timeout=1)

        state.api_client.send_move_update_board = slow_send
        state.sync_fen_async("test-fen")

        self.assertTrue(started.wait(timeout=0.5))
        # Reaching this point while slow_send is still waiting proves callers
        # (the Pygame main thread) are not held by the network request.
        self.assertFalse(release.is_set())
        release.set()


if __name__ == "__main__":
    unittest.main()
