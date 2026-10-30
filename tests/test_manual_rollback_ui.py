"""Manual restoration runs without any arm commands or UI waits."""
import unittest
from unittest.mock import Mock
import numpy as np
from src.core.game_state import GameState
from src.core import xiangqi
from src.ui.input_handler import InputHandler

class ManualRollbackUITests(unittest.TestCase):
    def setup_cycle(self):
        state = GameState()
        state.api_client = Mock(room_id=None)
        target = [row[:] for row in state.board]
        state.process_human_move((0, 6), (0, 5), 'r_P')
        move = ((0, 3), (0, 4))
        expected, victim = xiangqi.make_temp_move(state.board, move)
        state.set_pending_ai_move(move, expected, victim)
        self.assertTrue(state.commit_pending_ai_move())
        hw = Mock(config=None)
        hw.publish_manual_rollback_baseline.return_value = True
        handler = InputHandler(state, hw)
        handler._begin_manual_rollback()
        self.assertTrue(state.manual_rollback.active)
        # Simulate an already-running acquisition so polling only consumes evidence.
        handler._manual_scan_thread = Mock()
        handler._manual_scan_thread.is_alive.return_value = True
        hw.reset_mock()
        return state, hw, handler, target

    def feed(self, state, handler, target, at, matched=True):
        handler._manual_scan_result = (state.manual_rollback.session_token,
            dict(matched=matched, frame=np.zeros((2,2,3)), detections=[],
                 observed_board=target, error=''), at)
        handler.poll_manual_rollback()

    def test_stable_camera_restoration_resumes_red_once_with_no_robot_calls(self):
        state, hw, handler, target = self.setup_cycle()
        state.api_client.reset_mock()
        for at in (1., 1.5):
            self.feed(state, handler, target, at)
            self.assertTrue(state.manual_rollback.active)
        self.feed(state, handler, target, 2.1)
        self.assertFalse(state.manual_rollback.active)
        self.assertEqual(target, state.board)
        self.assertEqual('r', state.turn)
        self.assertFalse(state.can_start_ai_turn())
        state.api_client.queue_fen.assert_called_once()
        hw.publish_manual_rollback_baseline.assert_called_once()
        hw.robot.assert_not_called()
        self.assertEqual([], hw.robot.mock_calls)
        handler.poll_manual_rollback()
        state.api_client.queue_fen.assert_called_once()

    def test_failed_baseline_keeps_logical_post_board_and_pause(self):
        state, hw, handler, target = self.setup_cycle()
        post = [row[:] for row in state.board]
        hw.publish_manual_rollback_baseline.return_value = False
        for at in (1., 1.5, 2.1):
            self.feed(state, handler, target, at)
        self.assertTrue(state.manual_rollback.active)
        self.assertEqual(post, state.board)
        self.assertFalse(handler._handle_space_key())
        self.assertFalse(handler.start_pending_ai_motion())
        self.assertEqual([], hw.robot.mock_calls)

    def test_queued_old_evidence_cannot_publish_baseline(self):
        import time
        state, hw, handler, target = self.setup_cycle()
        for age in (7., 6.5, 5.5):
            handler._manual_scan_result = (state.manual_rollback.session_token,
                dict(matched=True, frame=np.zeros((2,2,3)), observed_board=target,
                     captured_at=time.monotonic() - age), time.monotonic())
            handler.poll_manual_rollback()
        self.assertTrue(state.manual_rollback.active)
        hw.publish_manual_rollback_baseline.assert_not_called()

    def test_mismatch_and_stale_session_never_complete(self):
        state, hw, handler, target = self.setup_cycle()
        for at in (1., 1.5, 2.1):
            self.feed(state, handler, target, at, matched=False)
        handler._manual_scan_result = (state.manual_rollback.session_token - 1,
            dict(matched=True, frame=np.zeros((2,2,3)), observed_board=target), 3.)
        handler.poll_manual_rollback()
        self.assertTrue(state.manual_rollback.active)
        hw.publish_manual_rollback_baseline.assert_not_called()
        self.assertEqual([], hw.robot.mock_calls)

if __name__ == '__main__':
    unittest.main()
