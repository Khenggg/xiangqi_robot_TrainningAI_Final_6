"""Exercise the main-loop decision functions without importing UI startup."""
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock

from src.core import xiangqi
from src.core.game_state import GameState
from src.core.ai_turn_flow import AIJobResult, evaluate_ai_result, dispatch_pending_ai_move
from src.ui.input_handler import InputHandler


class AiTurnFlowTests(unittest.TestCase):
    def state(self):
        state = GameState()
        state.api_client = Mock(room_id=None)
        state.process_human_move((0, 6), (0, 5), 'r_P')
        state.api_client.reset_mock()
        return state

    def pending(self, state):
        move = ((0, 3), (0, 4))
        expected, _ = xiangqi.make_temp_move(state.board, move)
        state.set_pending_ai_move(move, expected, '.')

    def test_engine_exception_does_not_declare_checkmate_or_change_fen(self):
        state = self.state()
        fen = state.current_fen
        self.assertIsNone(evaluate_ai_result(state, AIJobResult(error='search timeout')))
        self.assertFalse(state.game_over)
        self.assertEqual(state.current_fen, fen)
        self.assertEqual(state.turn, 'b')
        self.assertIn('search timeout', state.ai_failure)
        state.api_client.end_match.assert_not_called()

    def test_no_move_response_with_legal_moves_keeps_match_alive(self):
        state = self.state()
        self.assertIsNone(evaluate_ai_result(state, AIJobResult()))
        self.assertFalse(state.game_over)
        self.assertIsNotNone(state.ai_failure)

    def test_actual_no_legal_moves_can_end_match(self):
        state = self.state()
        state.board = [['.'] * 9 for _ in range(10)]
        state.board[9][4] = 'r_K'
        self.assertIsNone(evaluate_ai_result(state, AIJobResult()))
        self.assertTrue(state.game_over)
        state.api_client.end_match.assert_called_once_with(winner='RED', reason='CHECKMATE')

    def test_illegal_or_malformed_engine_move_cannot_reach_motion(self):
        for move in (((0, 3), (1, 3)), ((99, 99), (0, 0)), 'invalid'):
            state = self.state()
            self.assertIsNone(evaluate_ai_result(state, AIJobResult(move=move)))
            self.assertIsNotNone(state.ai_failure)
            self.assertIsNone(state.pending_ai_move)

    def test_disconnected_robot_retains_fen_and_pending_until_manual_confirmation(self):
        state = self.state()
        self.pending(state)
        fen = state.current_fen
        hardware = SimpleNamespace(robot=Mock(connected=False))
        handler = Mock()
        self.assertFalse(dispatch_pending_ai_move(state, hardware, handler, SimpleNamespace(DRY_RUN=False)))
        self.assertEqual(state.current_fen, fen)
        self.assertEqual(state.turn, 'b')
        self.assertTrue(state.pending_ai_move['manual_handoff'])
        self.assertTrue(state.physical_sync_fault)
        handler.start_pending_ai_motion.assert_not_called()
        state.api_client.send_move_update_board.assert_not_called()

    def test_connected_motion_is_dispatched_once_without_optimistic_commit(self):
        state = self.state()
        self.pending(state)
        before = state.current_fen
        handler = Mock()
        hardware = SimpleNamespace(robot=Mock(connected=True))
        self.assertTrue(dispatch_pending_ai_move(state, hardware, handler, SimpleNamespace(DRY_RUN=False)))
        handler.start_pending_ai_motion.assert_called_once()
        self.assertEqual(state.current_fen, before)
        self.assertIsNotNone(state.pending_ai_move)

    def test_ambiguous_previous_command_blocks_new_dispatch_until_controller_proof(self):
        state = self.state()
        self.pending(state)
        hardware = SimpleNamespace(robot=SimpleNamespace(connected=True, communication_fault=True))
        handler = Mock()
        self.assertFalse(dispatch_pending_ai_move(state, hardware, handler, SimpleNamespace(DRY_RUN=False)))
        handler.start_pending_ai_motion.assert_not_called()
        self.assertTrue(state.physical_sync_fault)
        self.assertIsNotNone(state.pending_ai_move)

    def test_board_match_alone_cannot_clear_ambiguous_running_controller(self):
        state = self.state()
        self.pending(state)
        state.physical_sync_fault = True
        robot = SimpleNamespace(communication_fault=True, can_resume_after_communication_fault=Mock(return_value=False))
        hardware = SimpleNamespace(robot=robot, verify_physical_board=Mock(return_value=True))
        before = state.current_fen
        InputHandler(state, hardware)._reconcile_physical_sync_fault()
        self.assertEqual(state.current_fen, before)
        self.assertIsNotNone(state.pending_ai_move)
        self.assertFalse(state.ai_retry_requested)
        hardware.verify_physical_board.assert_not_called()

    def test_fresh_idle_controller_and_expected_board_can_finalize_once(self):
        state = self.state()
        self.pending(state)
        state.physical_sync_fault = True
        robot = SimpleNamespace(communication_fault=True, can_resume_after_communication_fault=Mock(return_value=True))
        hardware = SimpleNamespace(robot=robot, verify_physical_board=Mock(side_effect=[False, True]),
                                   capture_baseline_if_needed=Mock(return_value=True))
        handler = InputHandler(state, hardware)
        handler._reconcile_physical_sync_fault()
        self.assertEqual(state.turn, 'r')
        self.assertIsNone(state.pending_ai_move)
        robot.can_resume_after_communication_fault.assert_called_once()

    def test_slow_controller_recovery_does_not_block_camera_ui_caller(self):
        state = self.state()
        self.pending(state)
        state.physical_sync_fault = True
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(2)
            return False
        hardware = SimpleNamespace(config=SimpleNamespace(VISUAL_MOTION_ASYNC_ENABLED=True),
            robot=SimpleNamespace(communication_fault=True, can_resume_after_communication_fault=probe),
            verify_physical_board=Mock())
        handler = InputHandler(state, hardware)
        try:
            handler._reconcile_physical_sync_fault()
            self.assertTrue(entered.wait(1))
            self.assertTrue(state.physical_motion_busy)
            self.assertTrue(handler._motion_thread.is_alive())
            # The caller returned while the controller check is still waiting.
        finally:
            release.set()
            handler._motion_thread.join(2)
        self.assertFalse(state.physical_motion_busy)
        self.assertTrue(state.physical_sync_fault)
        hardware.verify_physical_board.assert_not_called()

    def test_dry_run_commit_uses_same_single_finalizer_without_robot(self):
        state = self.state()
        self.pending(state)
        hardware = SimpleNamespace(config=SimpleNamespace(), robot=Mock(), capture_baseline_if_needed=Mock(return_value=True))
        handler = InputHandler(state, hardware)
        self.assertTrue(dispatch_pending_ai_move(state, hardware, handler, SimpleNamespace(DRY_RUN=True)))
        self.assertEqual(state.turn, 'r')
        self.assertIsNone(state.pending_ai_move)
        hardware.robot.move_piece.assert_not_called()


if __name__ == '__main__':
    unittest.main()
