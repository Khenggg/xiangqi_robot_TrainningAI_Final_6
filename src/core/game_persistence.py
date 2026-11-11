"""Persist business transitions before optional projections and motion dispatch."""
from copy import deepcopy
from functools import wraps
import logging
from pathlib import Path
import threading
from uuid import uuid4

from src.core.session_journal import SessionJournal, JournalError
from src.core.fen_utils import board_array_to_fen
from src.domain.game_move import piece_symbol_for_identity


STATE_FIELDS = (
    "board", "turn", "current_fen", "piece_ids", "last_move", "last_committed_move",
    "r_captured", "b_captured", "move_history", "move_log", "history_snapshots",
    "move_number", "board_revision", "game_epoch", "ai_epoch", "game_over", "winner",
    "human_commit_generation", "ai_started_for_human_commit_generation",
    "pending_move", "pending_ai_move", "move_execution_status", "move_execution_error",
    "physical_sync_fault", "move_sync_error", "manual_override_active",
    "snapshot_continue_required", "snapshot_continue_can_commit_pending",
    "turn_confirmation_required", "emergency_mode", "pick_test_mode", "pick_test_resume_required",
    "recovery_required", "mode_change_pending", "pick_test_board", "pick_test_piece_ids", "pick_test_fault",
    "pending_execution_binding", "last_execution_binding",
    "pending_test_motion", "last_test_motion",
)


def durable_transition(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._transition_lock:
            before = self.persistence_snapshot()
            before_result = self.last_commit_result
            committed_before = self._durable_commit_count
            try:
                return method(self, *args, **kwargs)
            except Exception as exc:
                if self._durable_commit_count == committed_before:
                    self._apply_persistence_snapshot(before)
                    self.last_commit_result = before_result
                elif not isinstance(exc, JournalError) and method.__name__ in {
                        "commit_pending_physical_move", "process_human_move", "process_emergency_move"}:
                    self.projection_error = f"Committed move projection pending: {exc}"
                    return True
                # Failure after a durable write cannot undo the committed board.
                self.physical_sync_fault = True
                self.manual_override_active = True
                self.snapshot_continue_required = True
                self.snapshot_continue_can_commit_pending = False
                self.move_execution_error = f"RECOVERY_REQUIRED: {exc}"
                self.set_status(self.move_execution_error, duration=60)
                from src.core.project_logging import event
                import logging
                event("session.persistence_failed", str(exc), level=logging.ERROR,
                      code="SESSION_PERSISTENCE_FAILED", operation=method.__name__)
                if method.__name__ in {"mark_move_pending", "set_pending_physical_move", "clear_pending_ai_move"}:
                    raise
                return False
    return run


class GamePersistence:
    def initialize_persistence(self):
        self._journal = None
        self._transition_lock = threading.RLock()
        self._durable_commit_count = 0
        self._pending_verified = False
        self.recovery_required = False
        self.mode_change_pending = False
        self._match_end_intent = None
        self._projection_worker = None
        self._spectator_bound_session = None
        self._local_session_id = uuid4().hex
        self._execution_binding_provider = None
        self.pending_execution_binding = self.last_execution_binding = None
        self.pending_test_motion = self.last_test_motion = None

    def persistence_snapshot(self):
        values = {name: deepcopy(getattr(self, name)) for name in STATE_FIELDS if name != "history_snapshots"}
        # Each undo snapshot previously repeated every earlier move/log entry.
        # Store shared-prefix lengths instead, retaining the complete undo history.
        values["history_snapshots"] = []
        for item in self.history_snapshots:
            compact = {key: deepcopy(value) for key, value in item.items()
                       if key not in {"move_history", "move_log"}}
            compact["_history_prefix_length"] = len(item.get("move_history", ()))
            compact["_log_prefix_length"] = len(item.get("move_log", ()))
            values["history_snapshots"].append(compact)
        values.update(schema_version=1, game_over_reason=getattr(self, "game_over_reason", ""),
                      capture_removed=bool(self.visual_capture_checkpoint),
                      pending_verified=self._pending_verified, match_end=deepcopy(self._match_end_intent))
        return values

    def _validate_persistence_snapshot(self, snapshot):
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
            raise JournalError("Unsupported/corrupt session snapshot")
        # Additive v1 fields from earlier snapshots; restore still forces operator
        # recovery and recomputes mode compatibility from the journal header.
        for name, default in (("recovery_required", False), ("mode_change_pending", False),
                              ("pick_test_board", None), ("pick_test_piece_ids", None), ("pick_test_fault", None),
                              ("pending_execution_binding", None), ("last_execution_binding", None),
                              ("pending_test_motion", None), ("last_test_motion", None)):
            snapshot.setdefault(name, default)
        if snapshot["pick_test_mode"] and snapshot["pick_test_board"] is None:
            # Older v1 files stored test flags without the isolated board. Do not
            # enter a renderer/robot test using a missing or guessed board.
            snapshot["pick_test_mode"] = False
            snapshot["pick_test_resume_required"] = True
            snapshot["pick_test_fault"] = "Saved test board unavailable; operator reconciliation/New Game required"
        if any(name not in snapshot for name in STATE_FIELDS):
            raise JournalError("Incomplete session snapshot")
        board = snapshot["board"]
        if (not isinstance(board, list) or len(board) != 10
                or any(not isinstance(row, list) or len(row) != 9 for row in board)
                or snapshot["turn"] not in {"r", "b"}
                or type(snapshot["move_number"]) is not int or snapshot["move_number"] < 1
                or type(snapshot["board_revision"]) is not int or snapshot["board_revision"] < 0):
            raise JournalError("Invalid saved board/revision")
        identities = snapshot["piece_ids"]
        if not isinstance(identities, dict) or len(set(identities.values())) != len(identities):
            raise JournalError("Invalid saved piece identities")
        cells = {(row, col) for row in range(10) for col in range(9) if board[row][col] != "."}
        if cells != set(identities) or any(board[row][col] != piece_symbol_for_identity(identity)
                                         for (row, col), identity in identities.items()):
            raise JournalError("Saved board/identity mismatch")
        if snapshot["current_fen"] != board_array_to_fen(board, snapshot["turn"], snapshot["move_number"]):
            raise JournalError("Saved FEN/board mismatch")
        pending, context = snapshot["pending_ai_move"], snapshot["pending_move"]
        binding = snapshot.get("pending_execution_binding")
        if binding is not None and (not isinstance(binding, dict) or context is None
                or binding.get("move_id") != context.move_id
                or binding.get("board_revision") != snapshot["board_revision"]):
            raise JournalError("Saved execution binding does not match its pending move/revision")
        if pending is not None:
            from src.core.xiangqi import make_temp_move
            if (context is None or identities.get(context.src) != context.piece_id
                    or identities.get(context.dst) != context.captured_piece_id
                    or pending["move"] != ((context.src[1], context.src[0]), (context.dst[1], context.dst[0]))
                    or pending["moving_color"] != snapshot["turn"]
                    or make_temp_move(board, pending["move"])[0] != pending["expected_board"]):
                raise JournalError("Saved pending move/identity mismatch")
        if snapshot.get("capture_removed") and (pending is None or pending["captured_piece"] == "."):
            raise JournalError("Invalid saved capture checkpoint")
        test = snapshot.get("pending_test_motion")
        if test is not None:
            from src.domain.game_move import MoveActor, MoveContext
            context = test.get("context") if isinstance(test, dict) else None
            binding = test.get("binding") if isinstance(test, dict) else None
            if (not isinstance(context, MoveContext) or not isinstance(binding, dict)
                    or not snapshot["pick_test_resume_required"]
                    or binding.get("move_id") != context.move_id
                    or binding.get("board_revision") != snapshot["board_revision"]
                    or not isinstance(binding.get("session_id"), str) or not binding["session_id"]
                    or snapshot["pick_test_board"] != test.get("before_board")
                    or snapshot["pick_test_piece_ids"] != test.get("before_ids")
                    or test.get("verified_outcome") not in {None, "completed", "unchanged", "restored"}):
                raise JournalError("Invalid saved manual test transaction")
            before, before_ids = test.get("before_board"), test.get("before_ids")
            expected, expected_ids = test.get("expected_board"), test.get("expected_ids")
            src, dst = context.src, context.dst
            if (context.actor is not MoveActor.ROBOT or context.captured_piece_id is not None
                    or src == dst or not isinstance(src, tuple) or not isinstance(dst, tuple)
                    or len(src) != 2 or len(dst) != 2
                    or any(type(value) is not int for value in (*src, *dst))
                    or any(not (0 <= row < 10 and 0 <= col < 9) for row, col in (src, dst))
                    or not isinstance(before, list) or len(before) != 10
                    or any(not isinstance(row, list) or len(row) != 9 for row in before)
                    or not isinstance(expected, list) or len(expected) != 10
                    or any(not isinstance(row, list) or len(row) != 9 for row in expected)
                    or not isinstance(before_ids, dict) or not isinstance(expected_ids, dict)
                    or set((row, col) for row in range(10) for col in range(9)
                           if before[row][col] != ".") != set(before_ids)
                    or len(set(before_ids.values())) != len(before_ids)
                    or any(before[row][col] != piece_symbol_for_identity(identity)
                           for (row, col), identity in before_ids.items())
                    or before_ids.get(src) != context.piece_id
                    or before[src[0]][src[1]] == "." or before[dst[0]][dst[1]] != "."):
                raise JournalError("Invalid saved manual test board/context")
            derived_board, derived_ids = deepcopy(before), dict(before_ids)
            derived_board[dst[0]][dst[1]] = derived_board[src[0]][src[1]]
            derived_board[src[0]][src[1]] = "."
            derived_ids[dst] = derived_ids.pop(src, None)
            if expected != derived_board or expected_ids != derived_ids:
                raise JournalError("Saved manual test expected board/identity mismatch")

    def _apply_persistence_snapshot(self, snapshot):
        for name in STATE_FIELDS:
            setattr(self, name, deepcopy(snapshot[name]))
        for item in self.history_snapshots:
            if "_history_prefix_length" in item:
                history_length = item.pop("_history_prefix_length")
                log_length = item.pop("_log_prefix_length")
                if (type(history_length) is not int or type(log_length) is not int
                        or not 0 <= history_length <= len(self.move_history)
                        or not 0 <= log_length <= len(self.move_log)):
                    raise JournalError("Saved undo-history prefix invalid")
                item["move_history"] = deepcopy(self.move_history[:history_length])
                item["move_log"] = deepcopy(self.move_log[:log_length])
        self.game_over_reason = snapshot.get("game_over_reason", "")
        self._pending_verified = snapshot.get("pending_verified", False)
        self._match_end_intent = deepcopy(snapshot.get("match_end"))
        self.visual_pick_retry = None
        self.test_pick_retry = None
        self.visual_capture_checkpoint = None
        if snapshot.get("capture_removed"):
            from src.core.visual_move_coordinator import signature
            self.visual_capture_checkpoint = dict(pending=self.pending_ai_move, signature=signature(self))

    def _discard_pre_dispatch_ai_failure(self, phase, journal=None):
        """Drop a failed AI command that provably failed before actuation.

        HOMECHESS/frame verification happens before the first motion stage.
        Keeping that pending transaction alive makes every restart re-arm the
        same stale error. The board/FEN recovery lock remains active; only the
        failed pending command is retired.
        """
        if phase != "RECOVERY_REQUIRED" or self.pending_ai_move is None:
            return False
        error = str(self.move_sync_error or self.move_execution_error or "")
        markers = ("HOMECHESS", "tool/user frame differs", "frame differs from R1-R4")
        if not any(marker in error for marker in markers):
            return False
        context = self.pending_move
        move_id = getattr(context, "move_id", None)
        if journal is not None and move_id and journal.has_command_stage(move_id, "capture_removed"):
            # A capture already reached the removal stage; HOMECHESS after that
            # may have failed with a held/partially moved piece. Keep it locked.
            return False
        self.pending_ai_move = None
        self.pending_move = None
        self.pending_execution_binding = None
        self.move_sync_error = None
        self.move_execution_error = None
        self.move_execution_status = "IDLE"
        self.clear_visual_requests()
        return True

    def attach_journal(self, root, environment, game_mode, *, fresh_start=False):
        if self._journal is not None:
            raise JournalError("A session journal is already attached")
        journal = SessionJournal(Path(root) / "data" / "runtime" / f"{environment.lower()}.sqlite3",
                                 environment, game_mode)
        try:
            if journal.loaded is not None:
                retired = journal.loaded["state"]
                self._validate_persistence_snapshot(retired)
                if retired["board_revision"] != journal.loaded["revision"]:
                    raise JournalError("Journal header/snapshot revision mismatch")
                if fresh_start:
                    # A launch starts with the caller's new opening board, never
                    # the previous session's FEN or pending command authority.
                    # An interrupted physical session still needs operator
                    # inspection, fresh idle telemetry and camera verification.
                    inspection_required = environment == "PHYSICAL" and bool(
                        retired["recovery_required"] or retired["physical_sync_fault"]
                        or retired["move_sync_error"] or retired.get("capture_removed")
                        or retired["pick_test_resume_required"]
                        or any(retired[name] is not None for name in (
                            "pending_move", "pending_ai_move", "pending_test_motion")))
                    if inspection_required:
                        self.recovery_required = True
                        self.physical_sync_fault = True
                        self.manual_override_active = True
                        self.snapshot_continue_required = True
                        self.set_status(
                            "New session, opening FEN. V verifies the board and automatically checks controller state.",
                            duration=60)
                    previous_session = journal.session_id
                    journal.new_session(self.persistence_snapshot(), archive_previous=True)
                    journal.loaded = None
                    from src.core.project_logging import event
                    event("session.started_fresh", "New session created; previous game FEN not loaded",
                          session_id=journal.session_id, previous_session_id=previous_session,
                          environment=environment, fen=self.current_fen,
                          operator_inspection_required=inspection_required)
                elif (journal.loaded["clean"] and retired.get("match_end") is not None
                        and not any(retired[name] for name in (
                            "recovery_required", "mode_change_pending", "physical_sync_fault", "move_sync_error"))
                        and all(retired[name] is None for name in (
                            "pending_move", "pending_ai_move", "pending_test_motion",
                            "pending_execution_binding"))
                        and not retired.get("capture_removed")
                        and not retired["pick_test_resume_required"]):
                    # Home/normal shutdown already settled and retired this game.
                    # Preserve its outbox, but never restore it into the next mode.
                    journal.new_session(self.persistence_snapshot(), retiring_snapshot=retired)
                    journal.loaded = None
            if journal.loaded is not None:
                snapshot = journal.loaded["state"]
                self._validate_persistence_snapshot(snapshot)
                binding = snapshot.get("pending_execution_binding")
                if binding is not None and binding.get("session_id") != journal.session_id:
                    raise JournalError("Saved command binding belongs to another session")
                test = snapshot.get("pending_test_motion")
                if test is not None and test["binding"]["session_id"] != journal.session_id:
                    raise JournalError("Saved manual test belongs to another session")
                if snapshot["board_revision"] != journal.loaded["revision"]:
                    raise JournalError("Journal header/snapshot revision mismatch")
                self._apply_persistence_snapshot(snapshot)
                discarded_pre_dispatch_ai = self._discard_pre_dispatch_ai_failure(
                    journal.loaded["phase"], journal)
                if self.pending_test_motion is not None:
                    self.pending_test_motion["verified_outcome"] = None
                    self.pick_test_fault = "Test was sent before closing; V checks controller state and reconciles the board. Do not re-run."
                if self.pending_move is not None and self.pending_ai_move is None:
                    # IDENTIFIED was saved before PREPARED; no automatic dispatch on restore.
                    from src.core.xiangqi import make_temp_move
                    context = self.pending_move
                    move = ((context.src[1], context.src[0]), (context.dst[1], context.dst[0]))
                    self.pending_ai_move = dict(move=move, expected_board=make_temp_move(self.board, move)[0],
                                                captured_piece=self.board[context.dst[0]][context.dst[1]],
                                                moving_color=self.turn)
                self.game_epoch += 1
                self.ai_epoch += 1
                # Saved observations are historical; a fresh operator check is required.
                self._pending_verified = False
                self.recovery_required = True
                self.mode_change_pending = journal.loaded["game_mode"] != game_mode
                self.manual_override_active = True
                self.snapshot_continue_required = True
                self.snapshot_continue_can_commit_pending = False
                if environment == "PHYSICAL":
                    self.physical_sync_fault = True
                if self.visual_capture_checkpoint:
                    from src.core.visual_move_coordinator import signature
                    self.visual_capture_checkpoint["signature"] = signature(self)
                self.set_status("Saved session restored; V checks controller state and reconciles the board. No automatic replay.", duration=60)
                if self.mode_change_pending:
                    self.set_status("A different mode was selected. Resolve the pending session, then New Game; the old game is not kept when switching modes.", duration=60)
                from src.core.project_logging import event
                event("session.restored", "Saved state loaded; waiting for operator reconciliation",
                      session_id=journal.session_id, environment=environment,
                      saved_mode=journal.loaded["game_mode"], selected_mode=game_mode,
                      revision=self.board_revision, phase=journal.loaded["phase"],
                      move_id=getattr(self.pending_move, "move_id", None))
                if discarded_pre_dispatch_ai:
                    event("session.discarded_pre_dispatch_ai",
                          "Failed AI transaction dropped before sending the command; board confirmation still required",
                          level=logging.INFO, environment=environment)
                    self.set_status(
                        "Old failed AI transaction dropped. Confirm the board with V/F4 before playing.",
                        duration=60)
            self._journal = journal
            if journal.loaded is None:
                journal.checkpoint(self.persistence_snapshot(), "READY")
            elif discarded_pre_dispatch_ai:
                journal.checkpoint(self.persistence_snapshot(), "RECOVERY_REQUIRED")
        except Exception:
            journal.close()
            self._journal = None
            raise

    def bind_spectator_session(self, *, restore=False):
        journal, client = self._journal, self.api_client
        if journal is None or self._spectator_bound_session == journal.session_id:
            return
        binding = journal.spectator_room(journal.session_id) if restore else None
        if binding is not None and binding["base_url"] != client.base_url:
            raise RuntimeError("Saved spectator room belongs to another server; New Game required")
        client.bind_session(journal.session_id, journal.bind_spectator_room, restored_room=binding)
        self._spectator_bound_session = journal.session_id

    def ensure_spectator_match(self, *, new=False):
        if not getattr(self.api_client, "token", None):
            return False
        try:
            self.bind_spectator_session(restore=not new)
            profile = getattr(self, "session_profile", None)
            names = profile.match_names if profile is not None else ("Player", "Robot AI")
            operation = self.api_client.create_match if new else self.api_client.ensure_match
            return operation(red_name=names[0], black_name=names[1], initial_fen=self.current_fen)
        except Exception as exc:
            from src.core.project_logging import event
            import logging
            self.projection_error = f"Spectator room pending: {exc}"
            event("projection.room_pending", str(exc), level=logging.WARNING)
            return False

    def persist_checkpoint(self, phase):
        if self._journal is not None:
            with self._transition_lock:
                self._journal.checkpoint(self.persistence_snapshot(), phase)

    @durable_transition
    def discard_stopped_virtual_work(self, hardware):
        """An explicit virtual reset may discard work, in one durable transition."""
        profile = getattr(hardware, "profile", None)
        if (hardware.dry_run is not True
                or (profile is not None and profile.execution_environment != "VIRTUAL")
                or (self._journal is not None and self._journal.environment != "VIRTUAL")
                or not hardware.stop_coordinator.safe_for_release()
                or hardware.motion_worker.busy):
            raise JournalError("Only a stopped virtual session may discard pending work")
        self.pending_move = self.pending_ai_move = self.pending_execution_binding = None
        self.pending_test_motion = None
        self.visual_capture_checkpoint = self.visual_pick_retry = self.test_pick_retry = None
        self._pending_verified = False
        self.persist_checkpoint("VIRTUAL_PENDING_DISCARDED")
        if self._journal is not None:
            self._durable_commit_count += 1
        return True

    def record_motion_dispatch(self, context, stage):
        with self._transition_lock:
            if self.recovery_required or context is None or context is not self.pending_move:
                raise JournalError("Unresolved recovery/stale move; no dispatch permitted")
            self.assert_execution_binding(context)
            if self._journal is not None:
                self._journal.dispatch(self.persistence_snapshot(), context, stage)

    def make_execution_binding(self, context):
        return dict(move_id=context.move_id,
                    session_id=self._journal.session_id if self._journal is not None else self._local_session_id,
                    board_revision=self.board_revision,
                    authority=self._execution_binding_provider() if self._execution_binding_provider else None)

    def assert_execution_binding(self, context=None):
        context = context if context is not None else self.pending_move
        if (context is None or context is not self.pending_move or self.pending_execution_binding is None
                or self.pending_execution_binding != self.make_execution_binding(context)):
            raise JournalError("Move session/board/calibration changed; no old command or target may be dispatched")
        return True

    def record_test_dispatch(self, context):
        """Save one test command receipt before any actuator call; never overwrite it."""
        with self._transition_lock:
            if (not self.pick_test_mode or self.pick_test_fault or self.pending_test_motion is not None
                    or self.pending_move is not None or self.pending_ai_move is not None):
                raise JournalError("Resolve the current test/game transaction before another test command")
            ids, board = self.pick_test_piece_ids, self.pick_test_board
            from src.domain.game_move import MoveActor
            if (context is None or context.captured_piece_id is not None
                    or context.actor is not MoveActor.ROBOT
                    or ids.get(context.src) != context.piece_id or context.dst in ids
                    or board[context.src[0]][context.src[1]] != piece_symbol_for_identity(context.piece_id)
                    or board[context.dst[0]][context.dst[1]] != "."):
                raise JournalError("Manual test identity/destination changed")
            expected_board, expected_ids = deepcopy(board), dict(ids)
            expected_board[context.dst[0]][context.dst[1]] = expected_board[context.src[0]][context.src[1]]
            expected_board[context.src[0]][context.src[1]] = "."
            expected_ids[context.dst] = expected_ids.pop(context.src)
            self.pending_test_motion = dict(context=context, binding=self.make_execution_binding(context),
                before_board=deepcopy(board), before_ids=dict(ids),
                expected_board=expected_board, expected_ids=expected_ids, verified_outcome=None)
            try:
                if self._journal is not None:
                    self._journal.dispatch(self.persistence_snapshot(), context, "manual_test")
            except Exception:
                self.pending_test_motion = None
                raise

    def assert_test_execution_binding(self, context):
        test = self.pending_test_motion
        if (test is None or test["context"] != context or not self.pick_test_mode
                or test["binding"] != self.make_execution_binding(context)):
            raise JournalError("Manual test session/board/calibration changed; command replay forbidden")
        return True

    def note_verified_test_board(self, context, outcome):
        with self._transition_lock:
            if (self.pending_test_motion is None or self.pending_test_motion["context"] != context
                    or outcome not in {"completed", "unchanged", "restored"}):
                raise JournalError("Camera test verification belongs to another transaction")
            self.pending_test_motion["verified_outcome"] = outcome
            try:
                self.persist_checkpoint("TEST_VERIFIED")
            except Exception:
                self.pending_test_motion["verified_outcome"] = None
                raise

    @durable_transition
    def complete_test_motion(self, context, *, outcome="completed", operator_recovery=False):
        test = self.pending_test_motion
        if test is None or test["context"] != context or outcome not in {"completed", "unchanged", "restored"}:
            raise JournalError("Manual test resolution requires the original transaction")
        if (self._journal is not None and self._journal.environment == "PHYSICAL"
                and test.get("verified_outcome") != outcome):
            raise JournalError("Fresh Camera verification required before resolving the physical test")
        if outcome == "restored":
            from src.core.fen_utils import INITIAL_FEN, fen_to_board_array
            from src.domain.game_move import initial_piece_identities
            self.pick_test_board = fen_to_board_array(INITIAL_FEN)[0]
            self.pick_test_piece_ids = initial_piece_identities()
        else:
            prefix = "expected" if outcome == "completed" else "before"
            self.pick_test_board = deepcopy(test[f"{prefix}_board"])
            self.pick_test_piece_ids = dict(test[f"{prefix}_ids"])
        self.last_test_motion = dict(test, outcome=outcome, operator_recovery=operator_recovery)
        self.pending_test_motion = None
        self.test_pick_retry = None
        self.pick_test_resume_required = True
        self.pick_test_fault = "Test reconciled; restore the board, then New Game" if operator_recovery else None
        if operator_recovery:
            self.pick_test_mode = False
        self.persist_checkpoint("TEST_OPERATOR_RESOLVED" if operator_recovery else "TEST_COMPLETED")
        if self._journal is not None:
            self._durable_commit_count += 1
        return True

    def note_verified_pending_board(self, board):
        if self.pending_ai_move is not None and board == self.pending_ai_move["expected_board"]:
            self._pending_verified = True
            try:
                self.persist_checkpoint("VERIFIED")
            except Exception:
                self._pending_verified = False
                raise

    def approve_recovery_after_verification(self, hardware):
        self.hardware_recovery_reason = None
        if self.mode_change_pending:
            self.set_status("Changing mode requires New Game after resolving the pending move.", duration=30)
            # Camera recovery may resolve an existing pending transaction, but
            # it must not authorize new actor dispatch in the newly selected mode.
        if not self.recovery_required and not self.physical_sync_fault:
            return True
        physical = hardware.simulation_runtime is None and not hardware.dry_run
        if physical and (not hardware.physical_telemetry_ready(require_idle=True)
                         or not hardware.stop_coordinator.safe_for_release(ignore_current_worker=True)):
            explain = getattr(hardware, "physical_recovery_block_reason", None)
            reason = explain() if callable(explain) else None
            reason = reason or "Controller state is not ready for recovery; waiting for current idle telemetry."
            self.hardware_recovery_reason = reason
            from src.core.project_logging import event
            event("recovery.hardware_blocked", f"Camera confirmed the board; {reason}",
                  level=logging.WARNING, code="ROBOT_NOT_READY",
                  board_verified=True, robot_reason=reason)
            self.set_status(f"Camera confirmed the board; {reason}", duration=60)
            return False
        self.recovery_required = False
        try:
            self.persist_checkpoint("OPERATOR_VERIFIED")
        except Exception:
            self.recovery_required = True
            raise
        return True

    def close_journal(self, *, clean=False):
        self.close_projection_worker()
        if self._journal is not None:
            journal = self._journal
            if clean:
                with journal.transaction():
                    settled = self.pending_move is None and self.pending_ai_move is None and not self.visual_capture_checkpoint
                    settled = settled and self.pending_test_motion is None
                    journal._write(self.persistence_snapshot(), "CLOSED", clean=settled)
            journal.close()
            self._journal = None

    def start_projection_worker(self):
        if self._journal is not None and self._projection_worker is None:
            from src.core.projection_worker import ProjectionWorker
            self._projection_worker = ProjectionWorker(self, self._journal)

    def close_projection_worker(self):
        if self._projection_worker is not None:
            self._projection_worker.close()
            self._projection_worker = None

    def request_current_projection(self):
        if self._journal is not None and self._projection_worker is not None:
            try:
                with self._transition_lock:
                    self._journal.request_projection(self.persistence_snapshot())
            except Exception as exc:
                from src.core.project_logging import event
                import logging
                self.projection_error = f"Projection still pending: {exc}"
                event("projection.enqueue_failed", str(exc), level=logging.ERROR, code="PROJECTION_FAILED")
                return False
            self._projection_worker.wake()
            return True
        return False

    def publish_match_end(self, *, winner="DRAW", reason="OTHER", retiring=False):
        already_recorded = self._match_end_intent is not None
        if self._match_end_intent is None:
            self._match_end_intent = dict(winner=winner, reason=reason)
        if self._journal is not None and self._projection_worker is not None:
            self.persist_checkpoint("MATCH_ENDED")
            self.request_current_projection()
            if retiring and getattr(self.api_client, "token", None):
                # Queue the oldest remaining update before another room creation.
                # Archived routes retain any subsequent states and terminal intent.
                entry = next((item for item in self._journal.pending_projections() if item[2] == "spectator"), None)
                if entry is not None:
                    journal = self._journal
                    def completed(success, error):
                        if success and journal._db is not None:
                            try:
                                journal.acknowledge_projection(entry)
                            except Exception:
                                # A close or failed ACK write leaves the durable
                                # intent intact; it is never a robot retry request.
                                pass
                    from src.core.session_journal import decode
                    import json
                    payload = decode(json.loads(entry[3]))
                    # A room validates moves in order. Never End using an older
                    # unacknowledged board, or ACK it on behalf of the final FEN.
                    terminal = payload.get("match_end")
                    room = journal.spectator_room(entry[0])
                    def fen_acknowledged(room_id, fen):
                        journal.bind_spectator_room(entry[0], self.api_client.base_url, room_id, fen)
                    def end_acknowledged(room_id, match_end):
                        journal.acknowledge_spectator_end(entry[0], room_id, match_end)
                    return self.api_client.submit_board_projection(
                        payload["current_fen"], completed, match_end=terminal,
                        session_id=entry[0], room=room, fen_acknowledged=fen_acknowledged,
                        end_acknowledged=end_acknowledged,
                        room_refresh=lambda: journal.spectator_room(entry[0]))
            return True
        if already_recorded:
            return True
        try:
            return self.api_client.end_match(winner=winner, reason=reason)
        except Exception as exc:
            self.projection_error = f"Spectator end pending: {exc}"
            return False

    def update_projection_status(self, revision, pending, error):
        from src.domain.move_commit import MoveCommitResult
        if self.last_commit_result is not None and revision == self.last_commit_result.board_revision:
            result = self.last_commit_result
            self.last_commit_result = MoveCommitResult(True, result.move_id, revision, pending, error)
        self.projection_error = error if pending else None
