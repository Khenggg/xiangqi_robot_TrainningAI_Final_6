"""Independent durability regressions found while reviewing runtime wiring."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.core.game_state import GameState
from src.core.rollback_cycle import StateSnapshot


class RollbackRuntimeReviewTests(unittest.TestCase):
    def state(self):
        state = GameState()
        state.api_client = Mock(room_id='room-review')
        state.api_client._outbox_scope.return_value = 'review-account'
        return state

    def test_terminal_state_and_invalidated_ledger_are_durable(self):
        state = self.state()
        runtime = state.rollback_runtime
        with tempfile.TemporaryDirectory() as folder:
            runtime.configure(Path(folder) / 'rollback.json')
            state.handle_game_over('r')
            runtime.persist(force=True)
            saved = runtime.journal.load()
            self.assertTrue(saved['committed_snapshot']['game_over'])
            self.assertEqual(saved['committed_snapshot']['winner'], 'r')

    def test_malformed_snapshot_does_not_replace_live_state(self):
        for field, value in [('move_log', {}), ('move_number', 'bad'),
                             ('human_commit_generation', 'bad'),
                             ('current_fen', 'valid string but wrong FEN')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                state = self.state()
                runtime = state.rollback_runtime
                path = Path(folder) / 'rollback.json'
                runtime.configure(path)
                runtime.persist(force=True)
                saved = runtime.journal.load()
                saved['committed_snapshot'][field] = value
                runtime.journal.save(saved)
                original = deepcopy(StateSnapshot.from_state(state).to_dict())
                self.assertFalse(runtime.configure(path))
                self.assertTrue(runtime.recovery_error)
                self.assertEqual(StateSnapshot.from_state(state).to_dict(), original)

    def test_dry_run_commit_keeps_provider_disabled(self):
        state = self.state()
        snapshot = StateSnapshot.from_state(state)
        with patch('src.core.game_state.config.DRY_RUN', True):
            state.rollback_runtime._commit(snapshot, 'rollback:dry-run-review')
        state.api_client.queue_fen_commit.assert_not_called()
        self.assertIn('rollback:dry-run-review', state.rollback_runtime.applied_commits)

    def test_pending_fen_cannot_disagree_with_committed_authority(self):
        state = self.state()
        runtime = state.rollback_runtime
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rollback.json'
            runtime.configure(path)
            runtime.persist(force=True)
            saved = runtime.journal.load()
            saved['applied_commits'] = ['rollback:pending-review']
            saved['pending_sync'] = {'rollback:pending-review': {
                'fen': 'invalid pending FEN', 'revision': saved['revision'],
                'room_id': saved['room_id']}}
            runtime.journal.save(saved)
            self.assertFalse(runtime.configure(path))
            self.assertTrue(runtime.recovery_error)
            state.api_client.queue_fen_commit.assert_not_called()

    def test_closed_ready_or_done_session_does_not_resurrect_old_room_or_cycle(self):
        from test_rollback_integration import RollbackIntegrationTests
        import pygame
        helper = RollbackIntegrationTests()
        for complete in (False, True):
            with self.subTest(complete=complete), tempfile.TemporaryDirectory() as folder:
                state, runtime, _, handler, initial, _, _ = helper.setup_physical_cycle(folder)
                if complete:
                    handler.handle_keyboard(pygame.K_z)
                    self.assertEqual(runtime.coordinator.phase, 'DONE')
                else:
                    self.assertEqual(runtime.cycle.status, 'BUILDING')
                self.assertTrue(runtime.close_session())
                recovered = self.state()
                recovered.api_client.room_id = 'fresh-room'
                recovered.api_client._outbox_scope.return_value = runtime.scope
                self.assertFalse(recovered.rollback_runtime.configure(Path(folder) / 'rollback.json'))
                self.assertFalse(recovered.rollback_runtime.recovery_error)
                self.assertEqual(recovered.board, initial)
                self.assertEqual(recovered.api_client.room_id, 'fresh-room')
                self.assertIsNone(recovered.rollback_runtime.cycle)
                self.assertIsNone(recovered.rollback_runtime.coordinator)

    def test_unfinished_session_refuses_close_and_never_ends_room(self):
        from test_rollback_integration import RollbackIntegrationTests
        import pygame
        helper = RollbackIntegrationTests()
        with tempfile.TemporaryDirectory() as folder:
            state, runtime, hw, handler, _, _, _ = helper.setup_physical_cycle(folder)
            state.api_client.end_match = Mock()
            original = hw.robot.move_piece

            def lost(*args, **kwargs):
                original(*args, **kwargs)
                raise TimeoutError('lost ACK')

            hw.robot.move_piece = lost
            handler.handle_keyboard(pygame.K_z)
            self.assertEqual(runtime.coordinator.phase, 'PAUSED_FAULT')
            self.assertFalse(runtime.close_session())
            self.assertFalse(runtime.journal.load()['session_closed'])
            state.api_client.end_match.assert_not_called()


if __name__ == '__main__':
    unittest.main()
