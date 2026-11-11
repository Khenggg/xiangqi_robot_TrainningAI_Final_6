import time
from copy import deepcopy
from collections import Counter, defaultdict
from src.domain.game_move import MoveActor, MoveContext, initial_piece_identities, piece_symbol_for_identity
from src.domain.move_commit import MoveCommitResult
from src.core.game_persistence import GamePersistence, durable_transition
from typing import Optional, Tuple, Dict, List, Any

from src.core import xiangqi  # type: ignore
from src.core.fen_utils import board_array_to_fen, fen_to_board_array, INITIAL_FEN  # type: ignore
from src.api.simulation_client import TuongKyDaiSuClient  # type: ignore
import config  # type: ignore

class GameState(GamePersistence):
    def __init__(self, allow_mouse_move=False):
        self.allow_mouse_move = allow_mouse_move
        self._move_observer = None
        self._board_observer = None
        self.api_client = TuongKyDaiSuClient(config.SIMULATION_API_URL, config.SIMULATION_TOKEN)
        
        # Core Game State
        self.current_fen = INITIAL_FEN
        self.board, self.turn = fen_to_board_array(self.current_fen)
        self.game_over = False
        self.winner = None
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.move_log = []
        self.history_snapshots = []
        self.move_number = 1
        self.piece_ids = initial_piece_identities()
        self.pending_move = None
        self.last_committed_move = None
        self.move_sync_error = None
        self.projection_error = None
        self.board_revision = 0
        self.last_commit_result = None
        self.turn_confirmation_required = False
        self.move_execution_status = "IDLE"
        self.move_execution_error = None
        
        
        # UI Feedback State
        self.status_message: str = ""
        self.status_color: Tuple[int, int, int] = (0, 0, 0)
        self.status_expiry: float = 0.0
        self.invalid_flash_pos: Optional[Tuple[int, int]] = None
        self.invalid_flash_expiry: float = 0.0
        
        # AI Thread State
        self.ai_thread: Any = None
        self._retired_ai_threads = []
        self.ai_result: Any = None
        self.ai_thinking: bool = False
        self.ai_think_start: float = 0.0
        # AI may start only after a locally committed human move.  The main
        # loop consumes each generation once, so repeated camera samples or a
        # duplicate commit cannot create a second robot job.
        self.human_commit_generation: int = 0
        self.ai_started_for_human_commit_generation: int = 0
        self.game_epoch: int = 0
        self.ai_epoch: int = 0
        self.ai_job_token = None
        self.ai_results: Dict[Any, Any] = {}
        self.ai_retry_requested: bool = False
        
        # Rollback State
        self._pre_space_state: Optional[Dict[str, Any]] = None
        self.manual_override_active: bool = False
        # Set only when the snapshot/FEN pipeline has explicitly paused the
        # game.  Emergency mode is a separate, deliberate control mode.
        self.snapshot_continue_required: bool = False
        self.hardware_recovery_reason = None  # Transient read-only diagnostic, never recovery authority.
        self.snapshot_continue_can_commit_pending: bool = False
        self.emergency_mode: bool = False
        self.pick_test_mode = False
        self.pick_test_board = None
        self.pick_test_piece_ids = None
        self.pick_test_resume_required = False
        self.pick_test_fault = None
        # A failed post-move camera check means the physical board may have
        # changed while FEN was intentionally left untouched.  Do not retry the
        # same robot command until an operator resolves the discrepancy.
        self.physical_sync_fault: bool = False
        self.pending_ai_move: Optional[Dict[str, Any]] = None
        self.visual_pick_retry = None
        self.visual_capture_checkpoint = None
        self.test_pick_retry = None
        self.is_robot_ready: bool = True
        self.physical_enable_pending: bool = False
        self.initialize_persistence()

    def update_fen_from_board(self):
        """Cập nhật current_fen từ board array hiện tại."""
        self.current_fen = board_array_to_fen(self.board, self.turn, self.move_number)

    def get_render_state(self):
        """Tạo dict game state cho renderer."""
        profile = getattr(self, "session_profile", None)
        return {
            "game_over": self.game_over,
            "turn": self.turn,
            "allow_mouse": self.allow_mouse_move,
            "game_mode": config.GAME_MODE,
            "robot_backend": config.ROBOT_BACKEND,
            "input_adapter": getattr(profile, "mouse_input", "LEGACY"),
            "pvp_room": getattr(self, "pvp_room", None),
            "camera_enabled": bool(getattr(profile, "camera_enabled", True)),
            "robot_moves_enabled": bool(getattr(profile, "robot_moves_enabled", True)),
            "simulation_enabled": bool(getattr(profile, "simulation_enabled", True)),
            "viewer_enabled": bool(getattr(profile, "viewer_enabled", True)),
            "client_controls_compact": profile is not None,
            "can_rollback": self._pre_space_state is not None,
            "is_robot_ready": getattr(self, "is_robot_ready", True),
            "physical_enable_pending": getattr(self, "physical_enable_pending", False),
            "ai_thinking": self.ai_thinking,
            "ai_think_start": self.ai_think_start,
            "status_message": self.status_message,
            "status_color": self.status_color,
            "status_expiry": self.status_expiry,
            "move_sync_error": self.move_sync_error,
            "physical_sync_fault": self.physical_sync_fault,
            "move_execution_error": self.move_execution_error,
            "move_execution_status": self.move_execution_status,
            "pending_ai_move": self.pending_ai_move,
            "visual_pick_retry": getattr(self, "visual_pick_retry", None),
            "test_pick_retry": getattr(self, "test_pick_retry", None),
            "pending_move": self.pending_move,
            "turn_confirmation_required": self.turn_confirmation_required,
            "manual_override_active": self.manual_override_active,
            "snapshot_continue_required": self.snapshot_continue_required,
            "hardware_recovery_reason": self.hardware_recovery_reason,
            "emergency_mode": self.emergency_mode,
            "pick_test_mode": self.pick_test_mode,
            "pick_test_fault": self.pick_test_fault,
            "pick_test_resume_required": self.pick_test_resume_required,
            "recent_moves": self.move_log[-8:],
        }

    @staticmethod
    def _is_game_only(hw_manager):
        cfg = getattr(hw_manager, "config", None)
        return (getattr(cfg, "GAME_ONLY", False) is True
                and getattr(cfg, "ROBOT_BACKEND", None) == "VIRTUAL"
                and getattr(hw_manager, "dry_run", False) is True)

    @durable_transition
    def reset_game(self, hw_manager=None):
        if hw_manager is not None:
            lock = getattr(hw_manager, "_piece_move_lock", None)
            control = getattr(hw_manager, "stop_coordinator", None)
            request = getattr(control, "request", None)
            physical = hw_manager.simulation_runtime is None and not hw_manager.dry_run
            if ((lock is not None and lock.locked())
                    or ((physical or request is not None)
                        and (control is None or not control.safe_for_release(ignore_current_worker=True)))
                    or self.pending_move is not None or self.pending_ai_move is not None
                    or self.pending_test_motion is not None
                    or self.visual_capture_checkpoint is not None):
                raise RuntimeError("Deferred reset required: stop/resolve the pending transaction first")
        self.retire_ai_job()
        self.visual_pick_retry = None
        self.visual_capture_checkpoint = None
        self.test_pick_retry = None
        retiring_snapshot = None
        # [API] Đóng room cũ trước khi tạo game mới
        if self._journal is not None or self.api_client.room_id or getattr(self.api_client, 'pending', False):
            print("[GAME] 🔚 Closing the old room before creating a new game...")
            winner = "DRAW"
            reason = "OTHER"
            
            # Nếu game đã kết thúc, dùng winner thực tế
            if self.game_over and self.winner:
                winner = "RED" if self.winner == "r" else "BLACK"
                reason = self.game_over_reason or "CHECKMATE"
            
            if self._journal is not None:
                retiring_snapshot = self.persistence_snapshot()
                retiring_snapshot["match_end"] = self._match_end_intent or dict(winner=winner, reason=reason)
            else:
                self.publish_match_end(winner=winner, reason=reason, retiring=True)
        
        self.game_epoch += 1
        self.ai_epoch += 1
        self.projection_error = None
        self.board_revision = 0
        self.last_commit_result = None
        self.current_fen = INITIAL_FEN
        self.board, self.turn = fen_to_board_array(self.current_fen)
        self.game_over = False
        self.winner = None
        self.game_over_reason = ""
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.move_log = []
        self.history_snapshots = []
        self.move_number = 1
        self.piece_ids = initial_piece_identities()
        self.pending_move = None
        self.last_committed_move = None
        self.move_sync_error = None
        self.turn_confirmation_required = False
        self.move_execution_status = "IDLE"
        self.move_execution_error = None
        self.status_message = ""
        self.status_expiry = 0.0
        self.invalid_flash_pos = None
        self.invalid_flash_expiry = 0.0
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        self.ai_think_start = 0.0
        self.ai_job_token = None
        self.ai_results = {}
        self.ai_retry_requested = False
        self.human_commit_generation = 0
        self.ai_started_for_human_commit_generation = 0
        self.manual_override_active = False
        self.snapshot_continue_required = False
        self.hardware_recovery_reason = None
        self.snapshot_continue_can_commit_pending = False
        self.emergency_mode = False
        self.pick_test_mode = False
        self.pick_test_board = None
        self.pick_test_piece_ids = None
        self.pick_test_resume_required = False
        self.pick_test_fault = None
        self.physical_sync_fault = False
        self.pending_ai_move = None
        self.recovery_required = False
        self.mode_change_pending = False
        self._pending_verified = False
        self._match_end_intent = None
        self.pending_execution_binding = self.last_execution_binding = None
        self.pending_test_motion = self.last_test_motion = None
        self.clear_visual_requests()

        physical_reset = (hw_manager is not None and hw_manager.simulation_runtime is None
                          and not hw_manager.dry_run)
        if physical_reset:
            self.physical_sync_fault = True
            self.manual_override_active = True
            self.snapshot_continue_required = True
            self.move_sync_error = "New game requires full physical board verification"

        self._pre_space_state = None
        print("[GAME] 🔄 New game started!")
        print(f"[FEN] {self.current_fen}")
        if self._journal is not None:
            self._journal.new_session(self.persistence_snapshot(), retiring_snapshot=retiring_snapshot)
            self._durable_commit_count += 1
        
        if hw_manager:
            try:
                if not self._is_game_only(hw_manager):
                    hw_manager.capture_baseline_if_needed(force_delay=0.0)
            except Exception as exc:
                # The new session is already durable. Camera initialization
                # cannot turn it into a failed reset or authorize blind play.
                self.physical_sync_fault = True
                self.manual_override_active = True
                self.snapshot_continue_required = True
                self.move_sync_error = f"New game requires camera recovery: {exc}"
                self.set_status(self.move_sync_error, duration=30)
            self.sync_current_board()
        else:
            self._require_scene_reconciliation("New game requires board reconciliation")
        
        # [API] Tạo room mới (nếu không ở chế độ DRY_RUN)
        self.ensure_spectator_match(new=True)
        return True

    def set_status(self, msg, color=(200, 0, 0), duration=2.5):
        self.status_message = msg
        self.status_color = color
        self.status_expiry = time.time() + duration

    def set_invalid_flash(self, col, row, duration=0.6):
        self.invalid_flash_pos = (col, row)
        self.invalid_flash_expiry = time.time() + duration

    def handle_game_over(self, the_winner, reason=""):
        if self.game_over:
            if self.winner != the_winner:
                raise RuntimeError("Cannot replace the recorded winner of a finished game")
            # Post-commit callers must not erase the atomic terminal reason or
            # invalidate the same AI generation a second time.
            return
        self.game_over_reason = reason
        self.winner = the_winner
        self.game_over = True
        self.ai_epoch += 1
        self.ai_job_token = None
        self.persist_checkpoint("TERMINAL")

    def save_rollback_state(self, baseline_occ=None, baseline_time=None):
        self._pre_space_state = {
            "board": [row[:] for row in self.board],
            "turn": self.turn,
            "last_move": self.last_move,
            "current_fen": self.current_fen,
            "move_number": self.move_number,
            "r_captured": list(self.r_captured),
            "b_captured": list(self.b_captured),
            "move_history": list(self.move_history),
            "move_log": list(self.move_log),
            "piece_ids": dict(self.piece_ids),
            "history_snapshots": deepcopy(self.history_snapshots),
            "game_over": self.game_over,
            "winner": self.winner,
            "game_over_reason": getattr(self, "game_over_reason", ""),
            "baseline_occ": baseline_occ,
            "baseline_time": baseline_time,
        }
        print("[SPACE] 💾 State saved for rollback (Z to undo).")

    @durable_transition
    def handle_rollback(self, hw_manager=None):
        """Rollback về trạng thái trước khi bấm SPACE lần cuối (phím Z)."""
        if not self._history_change_allowed(hw_manager):
            return False
        if self._pre_space_state is None:
            print("[ROLLBACK] ⚠️ No state to roll back!")
            self.set_status("⚠️  Nothing to roll back!", color=(180, 100, 0), duration=2.5)
            return

        print("[ROLLBACK] ↩️ Restoring the state before SPACE...")
        self.retire_ai_job()
        self.game_epoch += 1
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_results = {}
        self.ai_retry_requested = False
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        s = self._pre_space_state
        self.board = [row[:] for row in s["board"]]
        self.piece_ids = dict(s["piece_ids"])
        self.pending_move = None
        self.pending_ai_move = None
        self.clear_visual_requests()
        self.turn = s["turn"]
        self.last_move = s["last_move"]
        self.current_fen = s["current_fen"]
        self.move_number = s["move_number"]
        self.r_captured = list(s["r_captured"])
        self.b_captured = list(s["b_captured"])
        self.move_history = list(s["move_history"])
        self.move_log = list(s.get("move_log", []))
        self.history_snapshots = deepcopy(s.get("history_snapshots", []))
        self.game_over = s.get("game_over", False)
        self.winner = s.get("winner")
        self.game_over_reason = s.get("game_over_reason", "")
        self.board_revision += 1
        self.persist_checkpoint("ROLLBACK")
        if self._journal is not None:
            self._durable_commit_count += 1

        if hw_manager and not self._is_game_only(hw_manager):
            hw_manager.restore_yolo_baseline(s.get("baseline_occ"), s.get("baseline_time"))

        print("[ROLLBACK] 📸 T1 baselines restored.")

        self._pre_space_state = None   # Xóa sau khi rollback
        self.set_status("↩️  Rolled back! Move the piece again, then press SPACE.", color=(180, 100, 0), duration=5.0)
        print(f"[ROLLBACK] ✅ Done. FEN: {self.current_fen}")
        
        self.manual_override_active = False
        self.snapshot_continue_required = False
        self.snapshot_continue_can_commit_pending = False
        self.emergency_mode = False
        self.pick_test_mode = False
        self.pick_test_board = None
        self.pick_test_piece_ids = None
        self.pick_test_resume_required = False
        self.pick_test_fault = None
        if (hw_manager is not None and getattr(hw_manager, "simulation_runtime", None) is None
                and not self._is_game_only(hw_manager)):
            self.sync_current_board()
            self.physical_sync_fault = True
            self.move_sync_error = "Rollback requires physical board verification"
        else:
            self.sync_current_board()

    def set_pending_ai_move(self, move, expected_board, captured_piece):
        """Remember the only state transition a fault-recovery may commit."""
        self.visual_pick_retry = None
        self.visual_capture_checkpoint = None
        self.pending_ai_move = {
            "move": move,
            "expected_board": [row[:] for row in expected_board],
            "captured_piece": captured_piece,
        }

    def clear_visual_requests(self):
        """Drop acquisition requests whenever their pending game transition is replaced."""
        if self.pending_move is None:
            self.pending_execution_binding = None
        self.visual_pick_retry = None
        self.visual_capture_checkpoint = None
        self.test_pick_retry = None

    @durable_transition
    def clear_pending_ai_move(self):
        self.pending_ai_move = None
        self.pending_move = None
        self.pending_execution_binding = None
        self.clear_visual_requests()
        self.physical_sync_fault = False
        self._pending_verified = False
        self.persist_checkpoint("RESOLVED_OLD_BOARD")

    def prepare_ai_retry_after_physical_miss(self):
        """Re-open the current Black AI turn after a verified missed pickup.

        The FEN board remains unchanged.  A dedicated retry flag lets the main
        loop create one fresh AI job for that same human move; it never reuses
        a potentially stale robot command.
        """
        if self.game_over or self.turn != "b":
            return False
        worker = self.ai_thread
        is_alive = getattr(worker, "is_alive", None)
        if callable(is_alive) and is_alive():
            # Moonfish is a shared UCCI subprocess; never start a second
            # request while an earlier worker is still using it.
            return False
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_thread = None
        self.ai_thinking = False
        self.ai_results = {}
        self.ai_retry_requested = True
        return True

    def can_start_ai_turn(self):
        """Whether the main loop may create exactly one Black AI worker."""
        self._retired_ai_threads = [worker for worker in self._retired_ai_threads if worker.is_alive()]
        return (
            not self._retired_ai_threads
            and
            not self.recovery_required
            and
            not self.mode_change_pending
            and
            self._match_end_intent is None
            and
            not self.pick_test_mode
            and not self.pick_test_resume_required
            and not self.ai_thinking
            and self.ai_thread is None
            and (
                self.human_commit_generation > self.ai_started_for_human_commit_generation
                or self.ai_retry_requested
            )
        )

    def retire_ai_job(self):
        worker = self.ai_thread
        if worker is not None and worker.is_alive() is True:
            self._retired_ai_threads.append(worker)
        self.ai_thread = None
        self.ai_thinking = False

    def mark_ai_turn_started(self):
        """Consume the normal-generation or one-shot retry start authority."""
        self.ai_started_for_human_commit_generation = self.human_commit_generation
        self.ai_retry_requested = False

    def _record_move(self, turn, src, dst, piece):
        """Record a move for rules/history and the compact in-game move feed."""
        if not hasattr(self, "move_log"):
            self.move_log = []
        self.move_history.append({"turn": turn, "src": src, "dst": dst})
        self.move_log.append({"turn": turn, "src": src, "dst": dst, "piece": piece})

    def commit_pending_ai_move(self):
        return self.commit_pending_physical_move()

    @durable_transition
    def commit_pending_physical_move(self):
        """Atomically commit a verified robot move for either color."""
        if self.pending_ai_move is None:
            return False
        if (self._journal is not None and self._journal.environment == "PHYSICAL"
                and not self._pending_verified):
            self.mark_move_failed("Fresh full-board verification required before durable commit")
            return False
        pending = self.pending_ai_move
        src, dst = pending["move"]
        captured_piece = pending["captured_piece"]
        moving_color = pending.get("moving_color", "b")
        if self.turn != moving_color:
            return False
        context = self.pending_move
        if context is not None:
            if (context.actor != MoveActor.ROBOT or context.src != (src[1], src[0])
                    or context.dst != (dst[1], dst[0])
                    or self.piece_ids.get(context.src) != context.piece_id
                    or self.piece_ids.get(context.dst) != context.captured_piece_id):
                self.mark_move_failed("Robot move identity changed before commit")
                self.move_sync_error = self.move_execution_error
                return False
        elif self._move_observer is not None or self._board_observer is not None:
            self.mark_move_failed("Robot move lacks a semantic identity")
            self.move_sync_error = self.move_execution_error
            return False
        self._save_history_snapshot()
        self._record_move(moving_color, src, dst, self.board[src[1]][src[0]])
        if captured_piece != ".":
            (self.b_captured if moving_color == "r" else self.r_captured).append(captured_piece)
        self.board = [row[:] for row in pending["expected_board"]]
        self.last_move = pending["move"]
        self.turn = "b" if moving_color == "r" else "r"
        self.move_number += 1
        self.update_fen_from_board()
        if context is not None:
            self.commit_piece_identity(context)
        self.pending_ai_move = None
        self.clear_visual_requests()
        self.physical_sync_fault = False
        self.move_sync_error = None  # The verified commit supersedes the old command failure.
        self._record_commit_result(context)
        # A verified physical move is committed even if its spectator fails.
        # Keep the sync fault latched; never misreport an uncommitted move or
        # replay robot motion to repair a display.
        if not self.sync_current_board():
            self._set_commit_projection_pending()
        return True

    @property
    def is_human_turn(self):
        if self.recovery_required or self.mode_change_pending:
            return False
        mode = getattr(getattr(self, "session_profile", None), "game_mode",
                       getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT"))
        return mode == "HUMAN_VS_ROBOT" and self.turn == "r"

    @durable_transition
    def process_human_move(self, src, dst, p_name):
        if self.game_over or self.turn_confirmation_required or self.pick_test_mode or self.pick_test_resume_required:
            return False
        from src.core.project_logging import event
        if self.recovery_required or self.mode_change_pending or self.physical_sync_fault or self.move_sync_error or self.pending_move is not None:
            return False
        if not self.is_human_turn or not xiangqi.is_valid_move(src, dst, self.board, self.turn):
            return False
        moving_color = self.turn
        print(f"[HUMAN] ✅ Moved: {p_name} {xiangqi.format_move(src, dst)}")
        self.set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
        
        previous_rollback = self._pre_space_state or {}
        self.save_rollback_state(previous_rollback.get("baseline_occ"),
                                 previous_rollback.get("baseline_time"))
        self._save_history_snapshot()
        context = self.create_move_context(src, dst, MoveActor.HUMAN)
        self._record_move(moving_color, src, dst, p_name)
        
        cap_p = self.board[dst[1]][dst[0]]
        if cap_p != ".":
            (self.b_captured if moving_color == "r" else self.r_captured).append(cap_p)
        
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        
        self.commit_piece_identity(context)
        self.turn = "b" if moving_color == "r" else "r"  # Chuyển lượt
        self.human_commit_generation += 1
        self.move_number += 1
        self.update_fen_from_board()
        self._record_commit_result(context)
        event("game.human_move", "Player move accepted", move_id=context.move_id,
              src=src, dst=dst, cell_order="col,row", captured_piece_id=context.captured_piece_id,
              piece_id=context.piece_id, fen=self.current_fen)
        notified = self._notify_human_commit(context)
        projected = self.sync_current_board()
        if not (notified and projected):
            self._set_commit_projection_pending()
        print(f"[FEN] {self.current_fen}")
        
        # [API] Đồng bộ nước đi lên máy chủ Simulation
        self.publish_committed_fen()
        
        self._finish_human_committed_move(moving_color)
        return True

    def _finish_human_committed_move(self, moving_color):
        """Publish termination only after the committed FEN has been queued."""
        if self.game_over and self.winner == moving_color:
            self.publish_match_end(winner="RED" if moving_color == "r" else "BLACK",
                                   reason=self.game_over_reason or "CHECKMATE")

    @durable_transition
    def process_emergency_move(self, src, dst, p_name):
        """Commit one rule-checked client move for the side currently to move.

        A Red move intentionally follows the normal human path, which opens
        exactly one AI/robot reply.  A Black move is an operator correction:
        it cancels any in-flight AI result and hands the turn back to Red.
        """
        if (self.recovery_required or self.mode_change_pending or self.game_over or self.turn_confirmation_required or self.pick_test_mode or self.pick_test_resume_required
                or not xiangqi.is_valid_move(src, dst, self.board, self.turn)):
            return False
        if self.turn == "r" and (self.physical_sync_fault or self.move_sync_error or not self.is_human_turn):
            return False
        # An operator edit supersedes any unverified robot transition.  Never
        # let a later Continue overwrite the corrected client position.
        self.pending_ai_move = None
        self.pending_move = None
        self.pending_execution_binding = None
        self.clear_visual_requests()
        self.snapshot_continue_required = True
        self.snapshot_continue_can_commit_pending = False
        color = self.turn
        if color == "r":
            return self.process_human_move(src, dst, p_name)

        print(f"[EMERGENCY] ✅ Manual Black move: {p_name} {xiangqi.format_move(src, dst)}")
        captured_piece = self.board[dst[1]][dst[0]]
        self._save_history_snapshot()
        context = self.create_move_context(src, dst, MoveActor.HUMAN)
        self._record_move("b", src, dst, p_name)
        if captured_piece != ".":
            self.r_captured.append(captured_piece)
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        self.turn = "r"
        self.move_number += 1
        # Invalidate a worker which may have been calculating the old Black
        # position; Python cannot safely kill that thread, but its result is
        # discarded by the main-loop token check.
        self.commit_piece_identity(context)
        self.ai_epoch += 1
        self.ai_job_token = None
        self.retire_ai_job()
        self.ai_results = {}
        self.ai_retry_requested = False
        self.update_fen_from_board()
        self._record_commit_result(context)
        if not self.sync_current_board():
            self._set_commit_projection_pending()
        self.publish_committed_fen()
        self.set_status("✅ Emergency Black move accepted — Red to move.", color=(0, 120, 0), duration=6.0)
        self._finish_human_committed_move("b")
        return True

    def set_move_observer(self, callback):
        """Observe committed human moves. The observer must not actuate the robot."""
        self._move_observer = callback

    def set_board_observer(self, callback):
        """Install the observer for a complete, camera-confirmed cell map."""
        self._board_observer = callback

    def create_move_context(self, src_col_row, dst_col_row, actor) -> MoveContext:
        src = (int(src_col_row[1]), int(src_col_row[0]))
        dst = (int(dst_col_row[1]), int(dst_col_row[0]))
        src_sym = self.board[src[0]][src[1]]
        piece_id = self.piece_ids.get(src)

        if piece_id is None or piece_symbol_for_identity(piece_id) != src_sym:
            raise ValueError(f"Piece identity is not reconciled at {src}")

        destination_symbol = self.board[dst[0]][dst[1]]
        captured_id = self.piece_ids.get(dst)

        if (captured_id is None) != (destination_symbol == "."):
            raise ValueError(f"Destination identity is not reconciled at {dst}")
        if captured_id is not None and piece_symbol_for_identity(captured_id) != destination_symbol:
            raise ValueError(f"Captured identity is not reconciled at {dst}")
        return MoveContext(piece_id=piece_id, src=src, dst=dst, actor=actor,
                           captured_piece_id=captured_id)

    def commit_piece_identity(self, context: MoveContext):
        if self.piece_ids.get(context.src) != context.piece_id:
            raise ValueError("Moving piece identity changed before commit")
        if self.piece_ids.get(context.dst) != context.captured_piece_id:
            raise ValueError("Captured piece identity changed before commit")
        self.piece_ids.pop(context.src)
        self.piece_ids[context.dst] = context.piece_id
        self.last_committed_move = context
        self.last_execution_binding = deepcopy(self.pending_execution_binding)
        self.pending_move = None
        self.pending_execution_binding = None
        self.move_execution_status = "COMMITTED"
        self.move_execution_error = None

    @durable_transition
    def mark_move_pending(self, context: MoveContext):
        self.pending_move = context
        self.pending_execution_binding = self.make_execution_binding(context)
        self.move_execution_status = "PENDING"
        self.move_execution_error = None
        self._pending_verified = False
        self.persist_checkpoint("IDENTIFIED")

    def mark_move_failed(self, message: str):
        self.move_execution_status = "FAILED"
        self.move_execution_error = str(message)
        try:
            self.persist_checkpoint("RECOVERY_REQUIRED")
        except Exception as exc:
            from src.core.project_logging import event
            import logging
            event("session.persistence_failed", str(exc), level=logging.ERROR,
                  code="SESSION_PERSISTENCE_FAILED", operation="mark_move_failed")
            self.physical_sync_fault = True
            self.manual_override_active = True
            self.snapshot_continue_required = True

    def clear_move_sync_error(self):
        """Call only after explicitly reconciling the game and physical scene."""
        self.move_sync_error = None
        self.pending_move = None
        self.pending_execution_binding = None
        self.move_execution_status = "IDLE"
        self.move_execution_error = None

    def _require_scene_reconciliation(self, reason: str):
        if self._move_observer is not None or self._board_observer is not None:
            self.move_sync_error = reason
            self.set_status(reason, color=(180, 0, 0), duration=10.0)

    def _notify_human_commit(self, context: MoveContext):
        if self._projection_worker is not None:
            # Durable mode projects the entire identity map, idempotently. It
            # never replays a per-move animation to recover a lost callback.
            self._projection_worker.wake()
            return True
        if self._move_observer is None:
            return True
        try:
            if self._move_observer(context) is not True:
                raise RuntimeError("Digital Twin rejected committed human move")
        except Exception as exc:
            self.projection_error = f"Digital Twin sync failed: {exc}"
            return False
        return True

    @durable_transition
    def apply_confirmed_board(self, observed_board) -> bool:
        """Apply an approved complete camera board with canonical stable IDs.

        Retain IDs for unchanged cells, then assign unmatched same-type pieces
        from the remaining starting-layout IDs in sorted order. A full image
        cannot distinguish two identical physical pawns, so this is a logical
        deterministic identity assignment rather than visual re-identification.
        """
        from src.vision.cchess_recognizer import validate_board_sanity

        # A failed robot command leaves a pending semantic move. An explicit
        # complete rescan is the recovery path; the bridge itself rejects a
        # moving arm or attached payload before accepting the new board.
        if (not isinstance(observed_board, (list, tuple)) or len(observed_board) != 10
                or any(not isinstance(row, (list, tuple)) or len(row) != 9 for row in observed_board)):
            return False
        canonical = initial_piece_identities()
        allowed = Counter(piece_symbol_for_identity(pid) for pid in canonical.values())
        if any(not isinstance(cell, str) or (cell != "." and cell not in allowed)
               for row in observed_board for cell in row):
            return False
        seen = Counter(cell for row in observed_board for cell in row if cell != ".")
        if any(symbol not in allowed or count > allowed[symbol] for symbol, count in seen.items()):
            return False
        sane, _ = validate_board_sanity(observed_board)
        if not sane:
            return False

        # A full image says where pieces are, but not whose turn it is. Infer
        # only a single legal transition from the previously known board.
        # Interrupted robot motion may be observed at either endpoint.
        old_turn = self.turn
        board_changed = [list(row) for row in observed_board] != self.board
        next_turn = old_turn
        needs_turn_confirmation = False
        if board_changed:
            from src.vision.move_observation import derive_move_observation
            observation = derive_move_observation(self.board, observed_board, player_color=self.turn)
            if observation.success:
                expected, _ = xiangqi.make_temp_move(self.board, (observation.src, observation.dst))
                if expected == [list(row) for row in observed_board]:
                    next_turn = "b" if self.turn == "r" else "r"
                else:
                    needs_turn_confirmation = True
            else:
                needs_turn_confirmation = True

        remaining = defaultdict(list)
        new_ids = {}
        used = set()
        for row in range(10):
            for col in range(9):
                symbol = observed_board[row][col]
                old = self.piece_ids.get((row, col))
                if symbol != "." and old in canonical.values() and old not in used and piece_symbol_for_identity(old) == symbol:
                    new_ids[(row, col)] = old
                    used.add(old)
        for pid in sorted(canonical.values()):
            if pid not in used:
                remaining[piece_symbol_for_identity(pid)].append(pid)
        for row in range(10):
            for col in range(9):
                symbol = observed_board[row][col]
                if symbol != "." and (row, col) not in new_ids:
                    if not remaining[symbol]:
                        return False
                    new_ids[(row, col)] = remaining[symbol].pop(0)
        self.retire_ai_job()
        self.game_epoch += 1
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_results.clear()
        self.board = [list(row) for row in observed_board]
        self.piece_ids = new_ids
        self.turn = next_turn
        if board_changed and old_turn == "r" and next_turn == "b" and not needs_turn_confirmation:
            self.human_commit_generation += 1
        self.move_number += int(board_changed and next_turn != old_turn)
        self.update_fen_from_board()
        self.last_move = None
        self.last_committed_move = None
        self.pending_ai_move = None
        self.clear_visual_requests()
        self.history_snapshots.clear()
        self.move_history.clear()
        missing = allowed - seen
        self.r_captured = [symbol for symbol in sorted(missing) if symbol.startswith("r_")
                           for _ in range(missing[symbol])]
        self.b_captured = [symbol for symbol in sorted(missing) if symbol.startswith("b_")
                           for _ in range(missing[symbol])]
        self.move_sync_error = None
        self.physical_sync_fault = False
        self.clear_move_sync_error()
        self.turn_confirmation_required = needs_turn_confirmation
        self.board_revision += 1
        self._pending_verified = False
        self.persist_checkpoint("OPERATOR_RECONCILED_BOARD")
        if self._journal is not None:
            self._durable_commit_count += 1
        self.sync_current_board()
        if needs_turn_confirmation:
            self.move_sync_error = "Board synced; confirm the side to move with key 1 (Red) or 2 (Black)."
            self.set_status(self.move_sync_error, color=(180, 100, 0), duration=30.0)
        if self.api_client and not needs_turn_confirmation:
            try:
                self.publish_committed_fen()
            except Exception as exc:
                print(f"[API] Full-board rescan update failed: {exc}")
        return True

    @durable_transition
    def confirm_turn_after_rescan(self, color: str) -> bool:
        """Explicit operator confirmation after a multi-change recovery scan."""
        if not self.turn_confirmation_required or color not in ("r", "b"):
            return False
        self.turn = color
        self.update_fen_from_board()
        self.turn_confirmation_required = False
        self.move_sync_error = None
        self.physical_sync_fault = False
        self.board_revision += 1
        self.persist_checkpoint("OPERATOR_CONFIRMED_TURN")
        if self._journal is not None:
            self._durable_commit_count += 1
        if color == "b" and getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT") == "HUMAN_VS_ROBOT":
            self.ai_retry_requested = True
        if self.api_client:
            try:
                self.publish_committed_fen()
            except Exception as exc:
                print(f"[API] Confirmed-turn update failed: {exc}")
        self.set_status("Side to move confirmed.", color=(0, 120, 0), duration=5.0)
        return True

    @durable_transition
    def set_pending_physical_move(self, move, expected_board, captured_piece, moving_color="b"):
        """Remember a verified physical move without committing it yet."""
        self.visual_pick_retry = None
        self.visual_capture_checkpoint = None
        self.pending_ai_move = {
            "move": move,
            "expected_board": [row[:] for row in expected_board],
            "captured_piece": captured_piece,
            "moving_color": moving_color,
        }
        self._pending_verified = False
        self.persist_checkpoint("PREPARED")

    def sync_current_board(self):
        if self._projection_worker is not None:
            return self.request_current_projection()
        from src.core.project_logging import event
        import logging
        if self._board_observer is None:
            return True
        try:
            if self._board_observer(dict(self.piece_ids)) is not True:
                raise RuntimeError("Twin rejected board reconciliation")
        except Exception as exc:
            event("board.sync_failed", str(exc), level=logging.ERROR, code="BOARD_SYNC_FAILED",
                  exc_info=True, fen=self.current_fen, piece_count=len(self.piece_ids))
            self.projection_error = str(exc)
            self.set_status(f"Viewer not synced; the committed move is kept: {exc}", duration=30)
            return False
        self.projection_error = None
        return True

    def _record_commit_result(self, context, *, projection_pending=False):
        # Determine the business outcome before the atomic move/outbox write.
        # No observer, network queue or second terminal checkpoint is required
        # to recover a winning move correctly after a crash.
        if (not self.game_over and (xiangqi.get_king_pos(self.turn, self.board) is None
                                    or not xiangqi.find_all_valid_moves(self.turn, self.board))):
            self.game_over = True
            self.winner = "b" if self.turn == "r" else "r"
            self.game_over_reason = "CHECKMATE"
            self.ai_epoch += 1
            self.ai_job_token = None
            if self._journal is not None:
                self._match_end_intent = dict(winner="RED" if self.winner == "r" else "BLACK",
                                              reason="CHECKMATE")
        self.board_revision += 1
        self._pending_verified = False
        if self._journal is not None:
            self._journal.commit_move(self.persistence_snapshot(), context)
            self._durable_commit_count += 1
        self.last_commit_result = MoveCommitResult(
            committed=True, move_id=getattr(context, "move_id", None),
            board_revision=self.board_revision,
            projection_pending=projection_pending or self._projection_worker is not None,
            projection_error=self.projection_error if projection_pending else None)
        if self._projection_worker is not None:
            self._projection_worker.wake()

    def _set_commit_projection_pending(self):
        result = self.last_commit_result
        self.last_commit_result = MoveCommitResult(True, result.move_id, result.board_revision,
                                                   True, self.projection_error)

    def publish_committed_fen(self):
        if self._projection_worker is not None:
            self._projection_worker.wake()
            return True
        try:
            return self.api_client.send_move_update_board(self.current_fen)
        except Exception as exc:
            self.projection_error = f"Spectator update pending: {exc}"
            return False

    def _save_history_snapshot(self):
        self.history_snapshots.append({"board": [row[:] for row in self.board],
                                      "piece_ids": dict(self.piece_ids), "turn": self.turn,
                                      "game_over": self.game_over, "winner": self.winner,
                                      "game_over_reason": getattr(self, "game_over_reason", ""),
                                      "move_number": self.move_number, "last_move": self.last_move,
                                      "r_captured": list(self.r_captured), "b_captured": list(self.b_captured),
                                      "move_history": list(self.move_history), "move_log": list(self.move_log)})

    def _history_change_allowed(self, hw_manager):
        # Undo cannot erase an unresolved dispatch or resurrect an ended room.
        if (self.pending_move is not None or self.pending_ai_move is not None
                or self.pending_test_motion is not None or self.visual_capture_checkpoint is not None
                or self.pick_test_mode or self.pick_test_resume_required
                or self.recovery_required or self.mode_change_pending
                or self.physical_sync_fault or self.move_sync_error
                or self._match_end_intent is not None):
            self.set_status("Verify the move in progress before rolling back; a finished game needs New Game.", duration=20)
            return False
        if hw_manager is not None:
            worker = getattr(hw_manager, "motion_worker", None)
            lock = getattr(hw_manager, "_piece_move_lock", None)
            if ((worker is not None and worker.busy)
                    or (lock is not None and lock.locked())):
                self.set_status("Wait for the robot action to finish before rolling back.", duration=10)
                return False
        return True

    @durable_transition
    def undo_round(self, hw_manager=None):
        if not self._history_change_allowed(hw_manager):
            return False
        if self.ai_thinking:
            self.set_status("The AI is thinking; wait before rolling back.", duration=5)
            return False
        if not self.history_snapshots:
            self.set_status("There is no move to roll back.", duration=5)
            return False
        snapshot = self.history_snapshots.pop()
        for key, value in snapshot.items():
            setattr(self, key, value)
        self.game_epoch += 1
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_results.clear()
        self.ai_thinking = False
        self.pending_move = None
        self.pending_ai_move = None
        self.clear_visual_requests()
        self.update_fen_from_board()
        self.board_revision += 1
        self.persist_checkpoint("UNDO")
        if self._journal is not None:
            self._durable_commit_count += 1
        if hw_manager is not None and (getattr(hw_manager, "simulation_runtime", None) is not None
                                       or self._is_game_only(hw_manager)):
            self.sync_current_board()
            return True
        self.set_status("Rolled back; verify the board before continuing.", duration=10)
        self._require_scene_reconciliation("Undo requires board reconciliation")
        return True

    def get_legal_moves_for_selected(self) -> List[Tuple[int, int]]:
        """Trả về danh sách toạ độ (col, row) các ô hợp lệ mà quân cờ đang chọn có thể đi tới."""
        if not self.selected_pos:
            return []
        sc, sr = self.selected_pos
        p = self.board[sr][sc]
        if p == '.' or p[0] != self.turn:
            return []

        valid_dests = []
        for r in range(xiangqi.NUM_ROWS):
            for c in range(xiangqi.NUM_COLS):
                if xiangqi.is_valid_move((sc, sr), (c, r), self.board, self.turn):
                    valid_dests.append((c, r))
        return valid_dests
