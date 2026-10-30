"""No rollback hardware work or recovery ownership before an explicit Z."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call
import pygame

from src.core.game_state import GameState
import test_rollback_integration as rollback_fixtures


class RollbackPlayabilityTests(unittest.TestCase):
    def setup_cycle(self, folder):
        return rollback_fixtures.RollbackIntegrationTests().setup_physical_cycle(folder)

    def test_normal_cycle_never_scans_or_probes_for_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, motions = self.setup_cycle(folder)
            self.assertEqual('BUILDING', runtime.cycle.status)
            self.assertFalse(runtime.blocked)
            self.assertFalse(runtime.needs_seal)
            self.assertFalse((Path(folder) / 'rollback.json').exists())
            hw.robot.verify_rollback_ready.assert_not_called()
            hw.verify_rollback_board = Mock(side_effect=AssertionError('Pre-Z scan forbidden'))
            handler.handle_keyboard(pygame.K_v)
            hw.verify_rollback_board.assert_not_called()
            hw.robot.verify_rollback_ready.assert_not_called()
            state.process_human_move((2, 6), (2, 5), 'r_P')
            self.assertEqual('b', state.turn)
            self.assertEqual([], motions)

    def test_pre_z_journal_write_failure_cannot_interrupt_normal_moves(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, motions = self.setup_cycle(folder)
            runtime.journal.save = Mock(side_effect=OSError('disk unavailable'))
            state.process_human_move((2, 6), (2, 5), 'r_P')
            runtime.journal.save.assert_not_called()
            self.assertFalse(runtime.blocked)
            self.assertEqual('b', state.turn)

    def test_new_normal_move_archives_old_transaction_before_memory_only(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, initial, _, motions = self.setup_cycle(folder)
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual('DONE', runtime.coordinator.phase)
            state.process_human_move((2, 6), (2, 5), 'r_P')
            self.assertIsNone(runtime.journal.load()['coordinator'])
            recovered = GameState()
            recovered.api_client = Mock(room_id=None)
            recovered.api_client._outbox_scope.return_value = runtime.scope
            self.assertFalse(recovered.rollback_runtime.configure(Path(folder) / 'rollback.json'))
            self.assertFalse(recovered.rollback_runtime.blocked)

    def test_failed_z_preparation_can_cancel_without_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, motions = self.setup_cycle(folder)
            hw.verify_rollback_board = Mock(return_value=dict(
                matched=False, complete=False, errors=['layout uncertain at a0']))
            handler.handle_keyboard(pygame.K_z)
            self.assertTrue(runtime.blocked)
            self.assertIsNone(runtime.coordinator)
            self.assertIn('layout uncertain at a0', state.status_message)
            handler.handle_keyboard(pygame.K_m)
            self.assertIn('layout uncertain at a0', state.status_message)
            handler.handle_keyboard(pygame.K_x)
            self.assertFalse(runtime.blocked)
            self.assertEqual([], motions)

    def test_e_confirmation_reaches_z_preparation_and_completes_request(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, initial, _, motions = self.setup_cycle(folder)
            hw.robot.verify_rollback_ready.side_effect = [
                dict(ready=False, errors=['Confirm parked arm and empty gripper']),
                dict(ready=True)] + [dict(ready=True)] * 10
            handler.handle_keyboard(pygame.K_z)
            self.assertTrue(runtime.blocked)
            self.assertEqual([], motions)
            handler.handle_keyboard(pygame.K_e)
            self.assertFalse(runtime.blocked)
            self.assertEqual('DONE', runtime.coordinator.phase)
            self.assertEqual(initial, state.board)
            self.assertIn(call(operator_empty_gripper_confirmed=True),
                          hw.robot.verify_rollback_ready.call_args_list)

    def test_transient_restart_probe_error_remains_retryable(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, motions = self.setup_cycle(folder)
            runtime.restart_pending = True
            hw.robot.verify_rollback_ready.side_effect = [TimeoutError('controller temporarily offline'), {'ready': True}]
            handler.handle_keyboard(pygame.K_e)
            self.assertTrue(runtime.blocked)
            self.assertEqual('', runtime.recovery_error)
            self.assertIn('controller temporarily offline', state.status_message)
            handler.handle_keyboard(pygame.K_e)
            self.assertFalse(runtime.blocked)
            self.assertEqual([], motions)

    def test_old_pre_z_journal_does_not_restore_state_or_lock_new_game(self):
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, motions = self.setup_cycle(folder)
            runtime.needs_seal = True
            runtime.persist(force=True)
            recovered = GameState()
            initial_fen = recovered.current_fen
            recovered.api_client = Mock(room_id=None)
            recovered.api_client._outbox_scope.return_value = runtime.scope
            self.assertFalse(recovered.rollback_runtime.configure(Path(folder) / 'rollback.json'))
            self.assertFalse(recovered.rollback_runtime.blocked)
            self.assertEqual(initial_fen, recovered.current_fen)
            self.assertIsNone(recovered.api_client.room_id)
            self.assertEqual([], motions)


if __name__ == '__main__':
    unittest.main()
