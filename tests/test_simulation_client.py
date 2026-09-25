import unittest
from unittest.mock import Mock, patch

from src.api.simulation_client import TuongKyDaiSuClient


class SimulationClientTests(unittest.TestCase):
    @patch("src.api.simulation_client.time.sleep")
    @patch("src.api.simulation_client.requests.post")
    def test_retries_a_failed_fen_post_and_preserves_capture_fen(self, post, sleep):
        failed = Mock(status_code=503)
        failed.json.return_value = {"success": False, "message": "temporary"}
        success = Mock(status_code=200)
        success.json.return_value = {
            "success": True,
            "data": {"currentTurn": "r", "move": {"captured": "r_N"}},
        }
        post.side_effect = [failed, success]
        client = TuongKyDaiSuClient("https://example.test", "token")
        client.room_id = "room"
        capture_fen = "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 2"

        result = client.send_move_update_board(capture_fen)

        self.assertEqual({"captured": "r_N"}, result)
        self.assertEqual(2, post.call_count)
        self.assertEqual(capture_fen, post.call_args.kwargs["json"]["fen"])
        sleep.assert_called_once_with(0.25)

    @patch("src.api.simulation_client.requests.post")
    def test_does_not_retry_permanent_fen_rejection(self, post):
        rejected = Mock(status_code=400)
        rejected.json.return_value = {"success": False, "message": "invalid FEN"}
        post.return_value = rejected
        client = TuongKyDaiSuClient("https://example.test", "token")
        client.room_id = "room"

        self.assertIsNone(client.send_move_update_board("bad-fen"))
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
