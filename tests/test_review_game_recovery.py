"""Recovery and remote ordering regressions; every provider/hardware is mocked."""
import threading
import json
import tempfile
import time
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.api.simulation_client import FenSyncResult, TuongKyDaiSuClient
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
from src.ui.input_handler import InputHandler
from src.vision.player_turn_types import CommitRequest


def state_with_pending():
    state = GameState()
    state.api_client.token = ""
    state.api_client.send_move_update_board = Mock(return_value=FenSyncResult(True))
    state.api_client.create_match = Mock()
    state.api_client.end_match = Mock()
    state.turn = "b"
    expected, captured = xiangqi.make_temp_move(state.board, ((0, 3), (0, 4)))
    state.set_pending_ai_move(((0, 3), (0, 4)), expected, captured)
    state.physical_sync_fault = True
    return state


class GameRecoveryTests(unittest.TestCase):
    def test_z_leaves_committed_and_pending_positions_unchanged(self):
        import pygame
        for pending in (False, True):
            with self.subTest(pending=pending):
                state = state_with_pending()
                if not pending:
                    state.physical_sync_fault = False
                    self.assertTrue(state.commit_pending_ai_move())
                before = (state.current_fen, [row[:] for row in state.board], state.turn,
                          list(state.move_log), state.game_epoch, state.ai_epoch,
                          state.pending_ai_move, state.physical_sync_fault)
                hardware = Mock(config=None)
                handler = InputHandler(state, hardware)
                hardware.reset_mock()
                handler.handle_keyboard(pygame.K_z)
                self.assertEqual(before, (state.current_fen, state.board, state.turn,
                                          state.move_log, state.game_epoch, state.ai_epoch,
                                          state.pending_ai_move, state.physical_sync_fault))
                self.assertEqual([], hardware.mock_calls)

    def test_new_game_discards_pending_transition(self):
        state = state_with_pending()
        old_epoch = state.game_epoch
        state.reset_game()
        self.assertIsNone(state.pending_ai_move)
        self.assertFalse(state.physical_sync_fault)
        self.assertGreater(state.game_epoch, old_epoch)

    def test_physical_fault_blocks_moves_until_board_is_verified(self):
        state = state_with_pending()
        state.pending_ai_move = None
        state.turn = "r"
        self.assertFalse(state.can_start_ai_turn())
        request = CommitRequest((state.game_epoch, state.human_commit_generation, 0), ((0, 6), (0, 5)))
        self.assertEqual("PHYSICAL_SYNC_REQUIRED", HumanMoveCommitCoordinator(state).try_commit(request))
        hardware = SimpleNamespace(verify_physical_board=Mock(return_value=False),
                                   capture_baseline_if_needed=Mock(return_value=True))
        handler = InputHandler(state, hardware)
        handler._reconcile_physical_sync_fault()
        self.assertTrue(state.physical_sync_fault)
        hardware.capture_baseline_if_needed.assert_not_called()
        hardware.verify_physical_board.return_value = True
        handler._reconcile_physical_sync_fault()
        self.assertFalse(state.physical_sync_fault)
        self.assertEqual("r", state.turn)
        self.assertFalse(state.ai_retry_requested)

    def test_pending_commit_rejects_epoch_base_and_intent_mutation(self):
        for mutation in ("epoch", "base", "intent"):
            state = state_with_pending()
            before = state.current_fen
            if mutation == "epoch":
                state.game_epoch += 1
            elif mutation == "base":
                state.board[5][0] = "r_P"
            else:
                state.pending_ai_move["expected_board"][4][1] = "b_P"
            self.assertFalse(state.commit_pending_ai_move(), mutation)
            self.assertEqual(before, state.current_fen)
            self.assertIsNotNone(state.pending_ai_move)

    def test_human_request_from_old_epoch_cannot_move_current_board(self):
        state = state_with_pending()
        state.clear_pending_ai_move()
        state.turn = "r"
        request = CommitRequest((state.game_epoch, state.human_commit_generation, 0), ((0, 6), (0, 5)))
        state.game_epoch += 1
        self.assertEqual("STALE", HumanMoveCommitCoordinator(state).try_commit(request))

    def test_continue_requires_proof_even_when_legacy_override_flag_set(self):
        state = state_with_pending()
        state.snapshot_continue_can_commit_pending = True
        before = state.current_fen
        hardware = SimpleNamespace(verify_physical_board=Mock(return_value=False))
        InputHandler(state, hardware)._continue_after_snapshot_pause()
        self.assertEqual(before, state.current_fen)
        self.assertTrue(state.physical_sync_fault)
        self.assertIsNotNone(state.pending_ai_move)

    def test_manual_disconnected_handoff_accepts_geometry_without_robot_replay(self):
        state = state_with_pending()
        state.pending_ai_move["manual_handoff"] = True
        hardware = SimpleNamespace(verify_physical_board=Mock(return_value=False),
                                   verify_visual_move=Mock(return_value=True),
                                   capture_baseline_if_needed=Mock(return_value=True), robot=Mock())
        handler = InputHandler(state, hardware)
        handler._handle_space_key()
        self.assertEqual("r", state.turn)
        self.assertIsNone(state.pending_ai_move)
        self.assertEqual("b_P", state.board[4][0])
        hardware.robot.move_piece.assert_not_called()

    def test_manual_handoff_still_old_board_never_queues_robot_retry(self):
        state = state_with_pending()
        state.pending_ai_move["manual_handoff"] = True
        hardware = SimpleNamespace(verify_physical_board=Mock(return_value=True))
        InputHandler(state, hardware)._reconcile_physical_sync_fault()
        self.assertIsNotNone(state.pending_ai_move)
        self.assertFalse(state.ai_retry_requested)
        self.assertTrue(state.physical_sync_fault)

    def test_pending_from_old_epoch_never_invokes_camera_or_commits(self):
        state = state_with_pending()
        state.ai_epoch += 1
        hardware = SimpleNamespace(verify_physical_board=Mock())
        InputHandler(state, hardware)._reconcile_physical_sync_fault()
        hardware.verify_physical_board.assert_not_called()
        self.assertIsNotNone(state.pending_ai_move)

    def test_engine_error_retry_v_does_not_need_physical_proof_or_move(self):
        import pygame
        state = state_with_pending()
        state.clear_pending_ai_move()
        state.ai_failure = "engine timeout"
        state.human_commit_generation = 1
        state.ai_started_for_human_commit_generation = 1
        hardware = SimpleNamespace(robot=Mock(), verify_physical_board=Mock())
        before = state.current_fen
        InputHandler(state, hardware).handle_keyboard(pygame.K_v)
        self.assertTrue(state.ai_retry_requested)
        self.assertIsNone(state.ai_failure)
        self.assertEqual(before, state.current_fen)
        hardware.robot.move_piece.assert_not_called()
        hardware.verify_physical_board.assert_not_called()

    def test_engine_retry_waits_for_worker_exit(self):
        state = state_with_pending()
        state.clear_pending_ai_move()
        state.ai_failure = "engine timeout"
        state.ai_thread = Mock()
        state.ai_thread.is_alive.return_value = True
        InputHandler(state, SimpleNamespace())._continue_after_snapshot_pause()
        self.assertFalse(state.ai_retry_requested)
        self.assertEqual("engine timeout", state.ai_failure)

    def test_new_game_detaches_old_room_when_new_room_creation_fails(self):
        state = state_with_pending()
        state.api_client.room_id = "old-room"
        state.reset_game()
        self.assertIsNone(state.api_client.room_id)
        state.api_client.end_match.assert_called_once()



class RemoteSyncRecoveryTests(unittest.TestCase):
    def test_every_ack_snapshot_remains_restorable_for_other_rooms(self):
        import copy
        client = self.client()
        client.queue_fen('first-fen')
        client.room_id = 'second-room'
        client.queue_fen('second-fen')
        snapshots = []
        client._persist_locked = lambda: snapshots.append(copy.deepcopy(client._sync_jobs))
        client.send_move_update_board = Mock(return_value=FenSyncResult(True))
        client._drain_sync()
        self.assertTrue(snapshots)
        for snapshot in snapshots:
            self.assertTrue(all('fen' in job or 'end' in job for job in snapshot.values()))
        self.assertEqual(snapshots[-1], {})

    def test_non_object_outbox_is_reported_without_startup_crash_or_http(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'outbox.json'
            path.write_text('[]', encoding='utf-8')
            client = self.client()
            with patch('src.api.simulation_client.requests.post') as post:
                self.assertFalse(client.configure_outbox(path))
            post.assert_not_called()
            self.assertTrue(client.persistence_error)
            self.assertEqual(path.read_text(encoding='utf-8'), '[]')

    def client(self):
        client = TuongKyDaiSuClient("https://example.test", "test-token")
        client.room_id = "old-room"
        # Deterministic drain under test control, no real thread or HTTP.
        client.refresh_sync = Mock()
        return client

    def test_success_response_without_move_is_explicit_success(self):
        response = Mock(status_code=200)
        response.json.return_value = {"success": True}
        with patch("src.api.simulation_client.requests.post", return_value=response):
            result = self.client().send_move_update_board("fen")
        self.assertTrue(result.success)
        self.assertIsNone(result.move)

    def test_latest_fen_supersedes_failed_fen_and_end_waits_for_ack(self):
        client = self.client()
        client.send_move_update_board = Mock(return_value=FenSyncResult(False, True, error="offline"))
        client._post_end = Mock(return_value=FenSyncResult(True))
        client.queue_fen("fen-1")
        client.end_match(winner="BLACK", reason="CHECKMATE")
        client._drain_sync()
        self.assertTrue(client.sync_pending)
        client._post_end.assert_not_called()
        client.queue_fen("fen-2")
        client.send_move_update_board.return_value = FenSyncResult(True)
        client._drain_sync()
        self.assertEqual(["fen-1", "fen-2"], [c.args[0] for c in client.send_move_update_board.call_args_list])
        client._post_end.assert_called_once_with("old-room", {"winner": "BLACK", "reason": "CHECKMATE"})
        self.assertIsNone(client.room_id)

    def test_old_room_close_and_new_fen_are_scoped_across_reset(self):
        client = self.client()
        calls = []
        client.send_move_update_board = lambda fen, **kw: calls.append((kw["_room_id"], fen)) or FenSyncResult(True)
        client._post_end = lambda room, payload: calls.append((room, "end")) or FenSyncResult(True)
        client.queue_fen("old-fen")
        client.end_match()
        client.room_id = "new-room"
        client.queue_fen("new-fen")
        client._drain_sync()
        self.assertEqual([("old-room", "old-fen"), ("old-room", "end"), ("new-room", "new-fen")], calls)
        self.assertEqual("new-room", client.room_id)

    def test_new_fen_during_inflight_request_remains_after_old_ack(self):
        client = self.client()
        entered, release = threading.Event(), threading.Event()
        calls = []
        def post(fen, **kwargs):
            calls.append(fen)
            if fen == "old":
                entered.set()
                self.assertTrue(release.wait(2))
            return FenSyncResult(True)
        client.send_move_update_board = post
        client.queue_fen("old")
        worker = threading.Thread(target=client._drain_sync)
        worker.start()
        self.assertTrue(entered.wait(2))
        client.queue_fen("new")
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(["old", "new"], calls)
        self.assertFalse(client.sync_pending)

    def test_permanent_rejection_does_not_auto_retry_or_close_match(self):
        client = self.client()
        client.send_move_update_board = Mock(return_value=FenSyncResult(False, error="invalid FEN"))
        client._post_end = Mock()
        client.queue_fen("invalid")
        client.end_match()
        client._drain_sync()
        client._drain_sync()
        client.send_move_update_board.assert_called_once()
        client._post_end.assert_not_called()
        self.assertEqual("invalid FEN", client.sync_error)
        self.assertTrue(client.sync_pending)

    def test_failed_sync_is_visible_without_local_rollback_or_motion(self):
        state = state_with_pending()
        client = self.client()
        client.send_move_update_board = Mock(return_value=FenSyncResult(False, True))
        state.api_client = client
        before = state.current_fen
        state.sync_remote_board()
        state.set_status("Your turn!", duration=8)
        state.refresh_remote_sync_status()
        self.assertTrue(state.remote_sync_pending)
        self.assertIn("FEN máy chủ chưa đồng bộ", state.status_message)
        self.assertEqual(before, state.current_fen)
        client.send_move_update_board.assert_not_called()

    def test_remote_status_clears_after_room_end_ack(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        state.remote_sync_pending = True
        client.room_id = None
        state.refresh_remote_sync_status()
        self.assertFalse(state.remote_sync_pending)

    def test_old_blocked_room_does_not_warn_on_healthy_current_match(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        client.room_id = 'current-room'
        client._sync_jobs['old-room'] = dict(fen='old', blocked=True, error='old rejection')
        state.set_status('Move accepted — AI thinking...', duration=8)
        for _ in range(3):
            state.refresh_remote_sync_status()
        self.assertEqual('Move accepted — AI thinking...', state.status_message)
        self.assertFalse(state.remote_sync_pending)
        self.assertFalse(client.sync_blocked)
        self.assertEqual('', client.sync_error)
        self.assertTrue(client.sync_pending)  # Old job remains durable.
        self.assertIn('old-room', client._sync_jobs)

    def test_old_rejection_does_not_mislabel_current_transient_retry(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        client.room_id = 'current-room'
        client._sync_jobs['old-room'] = dict(fen='old', blocked=True, error='old rejection')
        client.queue_fen('current')
        state.refresh_remote_sync_status()
        self.assertIn('đang thử lại', state.status_message)
        self.assertNotIn('Máy chủ từ chối FEN', state.status_message)
        client.send_move_update_board = Mock(return_value=FenSyncResult(True))
        client._drain_sync()
        state.refresh_remote_sync_status()
        self.assertFalse(state.remote_sync_pending)
        self.assertNotIn('đang thử lại', state.status_message)
        self.assertTrue(client.sync_pending)

    def test_switching_rooms_clears_old_rejection_suffix(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        client.queue_fen('rejected')
        client.send_move_update_board = Mock(return_value=FenSyncResult(False, error='invalid'))
        client._drain_sync()
        state.refresh_remote_sync_status()
        self.assertIn('Máy chủ từ chối FEN', state.status_message)
        client.room_id = 'new-room'
        state.refresh_remote_sync_status()
        self.assertNotIn('Máy chủ từ chối FEN', state.status_message)
        self.assertFalse(state.remote_sync_pending)
        client.room_id = None
        state.refresh_remote_sync_status()
        self.assertFalse(state.remote_sync_pending)

    def test_remote_permanent_rejection_is_distinct_from_transient_retry(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        client.queue_fen("fen")
        client.send_move_update_board = Mock(return_value=FenSyncResult(False, True, error="offline"))
        client._drain_sync()
        state.refresh_remote_sync_status()
        self.assertIn("đang thử lại", state.status_message)
        client.queue_fen("fen")
        client.send_move_update_board.return_value = FenSyncResult(False, error="invalid")
        client._drain_sync()
        state.refresh_remote_sync_status()
        self.assertIn("Máy chủ từ chối FEN", state.status_message)
        self.assertNotIn("đang thử lại", state.status_message)

    def test_unexpected_client_error_is_visible_and_does_not_spin(self):
        client = self.client()
        client.queue_fen("fen")
        client.send_move_update_board = Mock(side_effect=ValueError("bad response"))
        client._drain_sync()
        client._drain_sync()
        self.assertTrue(client.sync_blocked)
        self.assertIn("bad response", client.sync_error)
        client.send_move_update_board.assert_called_once()

    def test_terminal_human_capture_queues_fen_before_match_end(self):
        state = state_with_pending()
        state.clear_pending_ai_move()
        state.turn = "r"
        state.board = [["." for _ in range(9)] for _ in range(10)]
        state.board[0][4] = "b_K"
        state.board[1][4] = "r_R"
        state.board[9][4] = "r_K"
        calls = []
        state.api_client.send_move_update_board = lambda fen: calls.append("fen")
        state.api_client.end_match = lambda **kwargs: calls.append("end")
        state.process_human_move((4, 1), (4, 0), "r_R")
        self.assertEqual(["fen", "end"], calls)
        self.assertTrue(state.game_over)
        self.assertEqual("r", state.winner)


class DurableOutboxTests(unittest.TestCase):
    def client(self, token="fixture-secret-token"):
        client = TuongKyDaiSuClient("https://example.test", token)
        client.refresh_sync = Mock()
        return client

    def test_restart_reloads_room_jobs_and_ack_removes_them_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            client = self.client()
            self.assertTrue(client.configure_outbox(path))
            client.room_id = "room"
            client.queue_fen("latest-fen")
            client.end_match("BLACK", "CHECKMATE")
            client.shutdown(0)
            stored = path.read_text()
            self.assertNotIn(client.token, stored)
            self.assertNotIn("Authorization", stored)
            restarted = self.client()
            self.assertTrue(restarted.configure_outbox(path))
            restarted.send_move_update_board = Mock(return_value=FenSyncResult(True))
            restarted._post_end = Mock(return_value=FenSyncResult(True))
            restarted.send_move_update_board.assert_not_called()
            self.assertTrue(restarted.sync_pending)
            restarted._drain_sync()
            restarted.send_move_update_board.assert_called_once_with("latest-fen", _room_id="room")
            restarted._post_end.assert_called_once_with("room", {"winner": "BLACK", "reason": "CHECKMATE"})
            self.assertEqual({}, json.loads(path.read_text())["jobs"])

    def test_scope_mismatch_keeps_original_outbox_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            first = self.client()
            first.configure_outbox(path)
            first.room_id = "room"
            first.queue_fen("saved-fen")
            original = path.read_bytes()
            other = self.client("different-secret")
            self.assertFalse(other.configure_outbox(path))
            other.room_id = "different-room"
            other.queue_fen("other-fen")
            other.shutdown(0)
            self.assertEqual(original, path.read_bytes())
            self.assertTrue(other.persistence_error)

    def test_missing_room_retains_latest_fen_and_status_until_room_created(self):
        state = state_with_pending()
        client = self.client()
        state.api_client = client
        state.current_fen = "fen-first"
        state.sync_remote_board()
        state.current_fen = "fen-latest"
        state.sync_remote_board()
        state.refresh_remote_sync_status()
        self.assertTrue(client.missing_room)
        self.assertTrue(state.remote_sync_pending)
        self.assertIn("Chưa có room máy chủ", state.status_message)
        response = Mock(status_code=200)
        response.json.return_value = {"success": True, "data": {"roomId": "new-room"}}
        with patch("src.api.simulation_client.requests.post", return_value=response):
            self.assertEqual("new-room", client.create_match())
        self.assertFalse(client.missing_room)
        self.assertEqual("fen-latest", client._sync_jobs["new-room"]["fen"])

    def test_missing_room_draft_is_durable_but_new_game_can_discard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            first = self.client()
            first.configure_outbox(path)
            first.queue_fen("latest")
            restarted = self.client()
            restarted.configure_outbox(path)
            self.assertTrue(restarted.missing_room)
            restarted.discard_unassigned_fen()
            self.assertFalse(restarted.sync_pending)
            self.assertIsNone(json.loads(path.read_text())["unassigned_fen"])

    def test_definitive_end_is_preserved_against_generic_cleanup(self):
        client = self.client()
        client.room_id = "room"
        client.end_match("BLACK", "CHECKMATE")
        client.end_match()
        client.end_match("RED", "RESIGN")
        self.assertEqual({"winner": "BLACK", "reason": "CHECKMATE"}, client._sync_jobs["room"]["end"])
        other = self.client()
        other.room_id = "room"
        other.end_match()
        other.end_match("RED", "CHECKMATE")
        self.assertEqual({"winner": "RED", "reason": "CHECKMATE"}, other._sync_jobs["room"]["end"])

    def test_transient_deadline_resets_on_reload_and_errors_do_not_serialize_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            first = self.client()
            first.configure_outbox(path)
            first.room_id = "room"
            first.queue_fen("latest")
            first.send_move_update_board = Mock(return_value=FenSyncResult(False, True, error=first.token))
            first._drain_sync()
            self.assertGreater(first._sync_jobs["room"]["due"], time.monotonic())
            self.assertNotIn(first.token, path.read_text())
            restarted = self.client()
            restarted.configure_outbox(path)
            self.assertEqual(0, restarted._sync_jobs["room"]["due"])
            restarted.send_move_update_board = Mock(return_value=FenSyncResult(True))
            restarted._drain_sync()
            restarted.send_move_update_board.assert_called_once()

    def test_shutdown_is_bounded_and_persists_inflight_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            client = self.client()
            client.configure_outbox(path)
            client.room_id = "room"
            client.queue_fen("inflight")
            entered, release = threading.Event(), threading.Event()
            def post(*args, **kwargs):
                entered.set()
                release.wait(2)
                return FenSyncResult(True)
            client.send_move_update_board = Mock(side_effect=post)
            worker = threading.Thread(target=client._drain_sync)
            client._sync_worker = worker
            worker.start()
            self.assertTrue(entered.wait(2))
            started = time.monotonic()
            self.assertFalse(client.shutdown(0.01))
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual("inflight", json.loads(path.read_text())["jobs"]["room"]["fen"])
            release.set()
            worker.join(2)
            self.assertEqual({}, json.loads(path.read_text())["jobs"])
            TuongKyDaiSuClient.refresh_sync(client)
            self.assertIs(worker, client._sync_worker)

    def test_pending_requires_black_turn(self):
        state = state_with_pending()
        state.turn = "r"
        self.assertFalse(state.pending_ai_move_is_current())
        self.assertFalse(state.commit_pending_ai_move())

    def test_no_room_terminal_result_is_durable_then_fen_precedes_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            first = self.client()
            first.configure_outbox(path)
            first.queue_fen("terminal-fen")
            first.end_match("BLACK", "CHECKMATE")
            first.end_match()
            restarted = self.client()
            restarted.configure_outbox(path)
            response = Mock(status_code=200)
            response.json.return_value = {"success": True, "data": {"roomId": "room"}}
            with patch("src.api.simulation_client.requests.post", return_value=response):
                restarted.create_match()
            calls = []
            restarted.send_move_update_board = lambda fen, **kw: calls.append(("fen", fen)) or FenSyncResult(True)
            restarted._post_end = lambda room, payload: calls.append(("end", payload)) or FenSyncResult(True)
            restarted._drain_sync()
            self.assertEqual([("fen", "terminal-fen"), ("end", {"winner": "BLACK", "reason": "CHECKMATE"})], calls)
            self.assertFalse(restarted.sync_pending)

    def test_malformed_restore_never_installs_partial_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.json"
            first = self.client()
            first.configure_outbox(path)
            first.room_id = "room"
            first.queue_fen("fen")
            saved = json.loads(path.read_text())
            saved["jobs"]["room"]["sequence"] = "not-an-integer"
            path.write_text(json.dumps(saved))
            restarted = self.client()
            self.assertFalse(restarted.configure_outbox(path))
            self.assertEqual({}, restarted._sync_jobs)
            self.assertFalse(restarted.sync_pending)

    def test_dry_run_never_sends_provider_request_even_if_room_exists(self):
        state = state_with_pending()
        client = self.client()
        client.room_id = "room"
        client.send_move_update_board = Mock()
        state.api_client = client
        with patch("src.core.game_state.config.DRY_RUN", True):
            self.assertTrue(state.sync_remote_board())
            state.refresh_remote_sync_status()
        client.send_move_update_board.assert_not_called()
        client.refresh_sync.assert_not_called()
        self.assertFalse(state.remote_sync_pending)


if __name__ == "__main__":
    unittest.main()
