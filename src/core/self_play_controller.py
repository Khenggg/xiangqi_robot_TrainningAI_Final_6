# =============================================================================
# === FILE: src/core/self_play_controller.py ===
# === Unified Autonomous Robot-vs-Robot Controller for Physical & Virtual Modes ===
# =============================================================================
from enum import Enum
import logging
import threading
import time
import inspect
from typing import Any, Optional, Tuple
from src.core import xiangqi
from src.core.project_logging import event
from src.domain.game_move import MoveActor
from src.motion.result import MotionExecutionResult


class SelfPlayStatus(str, Enum):
    IDLE = "idle"
    READY = "ready"
    THINKING = "thinking"
    MOVING = "moving"
    FAULTED = "faulted"
    PICK_PAUSED = "pick_paused"
    ENDING = "ending"
    ENDED = "ended"
    FINISHED = "finished"


class SelfPlayController:
    """
    Orchestrates autonomous Robot-vs-Robot matches with strict safety guarantees.
    Compatible with both Live Physical Hardware (FR3/FR5) and Virtual PyBullet Twin.
    """

    def __init__(self, state: Any, hw: Any):
        self.state = state
        self.hw = hw
        self.status = SelfPlayStatus.IDLE
        self.red_difficulty: Optional[str] = None
        self.black_difficulty: Optional[str] = None
        self.run_mode = "step"  # "step" or "continuous"
        self._epoch = 0
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[Tuple] = None
        self._token: Optional[Tuple] = None
        self._moving_before_board = None
        self._end_request = None
        self._surrender_request = None
        self._stop_handle = None

    def _current_token(self):
        return (self._epoch, getattr(self.state,"game_epoch",0),
                getattr(self.state,"ai_epoch",0),getattr(self.state,"move_number",1),
                self.state.turn,len(self.state.move_history))

    def _is_physical(self):
        return getattr(self.hw,"simulation_runtime",None) is None and getattr(self.hw,"dry_run",True) is False

    def _ui_worker_busy(self):
        worker = getattr(self.hw, "motion_worker", None)
        return worker is not None and worker.busy is True

    @property
    def active(self) -> bool:
        return self.status in {
            SelfPlayStatus.READY,
            SelfPlayStatus.THINKING,
            SelfPlayStatus.MOVING,
            SelfPlayStatus.ENDING,
            SelfPlayStatus.PICK_PAUSED,
        }

    @property
    def accepts_next(self) -> bool:
        return self.status is SelfPlayStatus.READY and self.run_mode == "step"

    @property
    def accepts_surrender(self) -> bool:
        return (self.status in {SelfPlayStatus.READY, SelfPlayStatus.THINKING, SelfPlayStatus.MOVING}
                and not getattr(self.state, "game_over", False)
                and not getattr(self.state, "turn_confirmation_required", False)
                and self._surrender_request is None)

    def request_surrender(self, *, winner):
        """Receive the click now; finish a moving piece before ending its game."""
        if winner not in {"RED", "BLACK"} or not self.accepts_surrender:
            return False
        self._surrender_request = (winner, "RESIGN")
        if self.status is not SelfPlayStatus.MOVING:
            self.end_match(winner=winner, reason="RESIGN")
        self.state.set_status("Đã nhận đầu hàng; chờ hoàn tất thao tác đang chạy.", duration=30)
        return True

    @property
    def human_input_disabled(self) -> bool:
        return self.active or self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED}

    @property
    def recovery_input_allowed(self):
        return (self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}
                and (self._thread is None or not self._thread.is_alive()))

    def finish_recovery(self):
        if (not self.recovery_input_allowed or self.state.physical_sync_fault
                or self.state.move_sync_error or self.state.pending_ai_move is not None
                or getattr(self.state, "pending_move", None) is not None
                or getattr(self.state, "pending_test_motion", None) is not None
                or getattr(self.state, "pick_test_resume_required", False)
                or getattr(self.state, "visual_capture_checkpoint", None) is not None):
            return False
        if self._end_request is not None:
            stop = self._stop_handle
            if stop is not None and (not stop.done.is_set() or not stop.result.safe
                                    or not self.hw.stop_coordinator.safe_for_release()):
                return False
            self._finish_end()
            return True
        self.status = SelfPlayStatus.IDLE
        return True

    def retry_visual_pick(self, source="UNKNOWN"):
        from src.core.visual_move_coordinator import retry_is_current, execute_pending_ai_motion
        mode = getattr(getattr(self.state, "session_profile", None), "game_mode", "ROBOT_VS_ROBOT")
        if self._ui_worker_busy():
            event("ui.retry_rejected", f"Từ chối đo lại tâm quân ({source})", level=logging.WARNING,
                  source=source, mode=mode, reason="UI_WORKER_BUSY",
                  self_play_status=self.status.value)
            return False
        if self.status is not SelfPlayStatus.PICK_PAUSED:
            event("ui.retry_rejected", f"Từ chối đo lại tâm quân ({source})", level=logging.WARNING,
                  source=source, mode=mode, reason="NOT_PICK_PAUSED",
                  self_play_status=self.status.value)
            return False
        if not retry_is_current(self.state):
            event("ui.retry_rejected", f"Từ chối đo lại tâm quân ({source})", level=logging.WARNING,
                  source=source, mode=mode, reason="STALE_PENDING_MOVE",
                  self_play_status=self.status.value,
                  pending_move=(
                      self.state.pending_ai_move.get("move")
                      if isinstance(getattr(self.state, "pending_ai_move", None), dict) else None),
                  game_epoch=getattr(self.state, "game_epoch", None))
            return False
        request = self.state.visual_pick_retry
        token = self._current_token()
        if token != self._token:
            event("ui.retry_rejected", f"Từ chối đo lại tâm quân ({source})", level=logging.WARNING,
                  source=source, mode=mode, reason="STALE_SELF_PLAY_EPOCH",
                  self_play_status=self.status.value, token=token, expected_token=self._token)
            self._fault("Retry belongs to a stale self-play epoch")
            return False
        expected = self.state.pending_ai_move["expected_board"]
        color = self.state.turn
        event("ui.retry_pick_requested",
              f"Yêu cầu đo lại tâm quân từ {source} ({request.get('stage') or 'n/a'})",
              source=source, mode=mode, kind="self_play",
              move_id=getattr(self.state.pending_move, "move_id", None),
              stage=request.get("stage"), reason=request.get("reason"),
              move=self.state.pending_ai_move.get("move"), moving_color=color,
              game_epoch=getattr(self.state, "game_epoch", None),
              board_revision=getattr(self.state, "board_revision", None),
              resolution=request.get("resolution"))
        def run():
            event("vision.retry_started",
                  f"Bắt đầu đo lại tâm quân ({request.get('stage') or 'n/a'})",
                  source=source, mode=mode, kind="self_play",
                  move_id=getattr(self.state.pending_move, "move_id", None),
                  stage=request.get("stage"), reason=request.get("reason"),
                  resolution=request.get("resolution"))
            try:
                result = execute_pending_ai_motion(self.state, self.hw, stage=request["stage"])
                self._result = (token, expected, color, result, None)
            except Exception as exc:
                self._result = (token, expected, color, None, exc)
        self.status = SelfPlayStatus.MOVING
        self._thread = threading.Thread(target=run, name="self-play-retry", daemon=False)
        self._thread.start()
        return True

    def close(self, timeout=5.0):
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise RuntimeError("Self-play motion still running; hardware must remain open")

    def retire_settled_session(self):
        """Reset may retire callbacks only after the controlled-stop barrier."""
        if ((self._thread is not None and self._thread.is_alive()) or self._ui_worker_busy()
                or not self.hw.stop_coordinator.safe_for_release()):
            raise RuntimeError("Cannot retire self-play before verified stop")
        self._epoch += 1
        self._end_request = self._surrender_request = self._stop_handle = self._result = self._token = None
        self._thread = None
        self.status = SelfPlayStatus.IDLE

    def start(self, red_difficulty: str = "medium", black_difficulty: str = "medium", run_mode: str = "continuous") -> bool:
        """Initialize and start an autonomous self-play match."""
        if getattr(self.state, "recovery_required", False) or getattr(self.state, "mode_change_pending", False):
            return self._start_fault("Restored session requires explicit operator recovery first")
        if getattr(self.state, "_match_end_intent", None) is not None:
            return self._start_fault("Match ended; choose New Game before starting self-play")
        if getattr(self.state, "game_over", False):
            self.status = SelfPlayStatus.FINISHED
            self.state.set_status("Ván đã kết thúc. Chọn New Game trước khi bắt đầu self-play.",
                                  color=(180, 100, 0), duration=15.0)
            return False
        if getattr(getattr(self.hw, "config", None), "GAME_MODE", None) != "ROBOT_VS_ROBOT":
            return self._start_fault("Robot-vs-robot mode required; self-play is not authorized in this game mode.")
        if self._thread is not None and self._thread.is_alive():
            self.state.set_status("Wait for the previous self-play worker before restarting.",
                                  color=(180, 100, 0), duration=8.0)
            return False
        # A finished thread still owns a result until tick consumes it. A
        # paused capture also owns its checkpoint; F6 must not replace either.
        if (self.status in {SelfPlayStatus.THINKING, SelfPlayStatus.MOVING,
                            SelfPlayStatus.PICK_PAUSED, SelfPlayStatus.ENDING}
                or getattr(self.state, "pending_ai_move", None) is not None
                or getattr(self.state, "pending_move", None) is not None):
            self.state.set_status("Nước đang chờ xử lý hoặc retry. Chờ hoàn tất, dùng Y đo lại hoặc F8 dừng.",
                                  color=(180, 100, 0), duration=15.0)
            return False
        if getattr(self.state, "turn_confirmation_required", False):
            return self._start_fault("Xác nhận lượt Đỏ/Đen sau khi quét bàn trước khi self-play.")
        if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
            return self._start_fault("Khôi phục bàn và New Game sau test trước khi self-play.")
        # 1. Readiness check across Physical and Virtual backends
        backend_type = getattr(getattr(self.hw, "config", None), "ROBOT_BACKEND", "PHYSICAL").upper()
        dry_run = getattr(self.hw, "dry_run", False)

        if not getattr(self.hw, "is_robot_ready", False):
            return self._start_fault("Robot backend is not ready for self-play.")
        if getattr(self.state, "move_sync_error", None) or getattr(self.state, "physical_sync_fault", False):
            return self._start_fault("Reconcile the camera board before self-play.")
        if not callable(getattr(self.hw, "execute_piece_move", None)):
            return self._start_fault("Self-play requires the unified motion executor.")

        if run_mode not in {"step", "continuous"}:
            return self._start_fault("Choose Step or Continuous mode.")

        # 2. Check engine availability if controller supports it
        if hasattr(self.hw, "difficulty_availability"):
            avail = self.hw.difficulty_availability()
            if avail and (not avail.get(red_difficulty) or not avail.get(black_difficulty)):
                return self._start_fault("Both selected engine difficulties must be ready.")

        # 3. Camera baseline verification (if physical camera is active)
        if self._is_physical():
            if self.hw.cam_monitor is None or not callable(getattr(self.hw, "verify_physical_board", None)):
                return self._start_fault("Live self-play requires a full-board camera verifier.")
            if hasattr(self.hw, "capture_baseline_if_needed"):
                self.hw.capture_baseline_if_needed(force_delay=1.0)
            if not self.hw.verify_physical_board(self.state.board):
                return self._start_fault("Camera board check failed. Arrange all pieces, then retry.")

        self.red_difficulty = red_difficulty
        self.black_difficulty = black_difficulty
        self.run_mode = run_mode
        self.status = SelfPlayStatus.READY
        self._epoch += 1
        self.state.ensure_spectator_match()
        print(f"[SELF-PLAY] 🚀 Started! Red: {red_difficulty}, Black: {black_difficulty}, Mode: {run_mode}")
        return True

    def set_run_mode(self, run_mode: str) -> bool:
        if self.status not in {SelfPlayStatus.READY, SelfPlayStatus.IDLE} or run_mode not in {"step", "continuous"}:
            return False
        self.run_mode = run_mode
        print(f"[SELF-PLAY] Cadence switched to: {run_mode.upper()}")
        return True

    def request_next_move(self) -> bool:
        if self._ui_worker_busy() or self.status is not SelfPlayStatus.READY:
            return False
        if getattr(self.state, "game_over", False):
            self.status = SelfPlayStatus.FINISHED
            return False
        if getattr(self.state, "turn_confirmation_required", False):
            return self._start_fault("Xác nhận lượt Đỏ/Đen trước khi đi tiếp.")
        if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
            return False
        robot_ready = bool(getattr(self.hw, "is_robot_ready", False))
        if (not robot_ready and getattr(self.hw, "simulation_runtime", None) is not None
                and self.hw.backend.is_connected()):
            # Continuous virtual play waits for its executor's board snapshot;
            # an optional physical mirror never enters this readiness gate.
            return False
        if (not robot_ready
                or getattr(self.state, "move_sync_error", None)
                or getattr(self.state, "physical_sync_fault", False)):
            self._fault("Self-play blocked by robot readiness or board synchronization fault.")
            return False
        snapshot = [row[:] for row in self.state.board]
        color = self.state.turn
        difficulty = self.red_difficulty if color == "r" else self.black_difficulty
        token = self._current_token()
        self._token = token
        self.status = SelfPlayStatus.THINKING

        def think():
            try:
                if self._is_physical() and not self.hw.verify_physical_board(snapshot):
                    raise RuntimeError("Pre-motion full-board camera verification failed")
                move = None
                if hasattr(self.hw, "ai_ctrl") and self.hw.ai_ctrl is not None:
                    picker = self.hw.ai_ctrl.pick_move
                    params = inspect.signature(picker).parameters
                    if "difficulty" in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                        move = picker(snapshot,color=color,difficulty=difficulty)
                    else:
                        # Compatibility engines have no per-player difficulty API.
                        move = picker(snapshot,color=color)
                self._result = (token, snapshot, color, move, None)
            except Exception as exc:
                self._result = (token, snapshot, color, None, exc)

        self._thread = threading.Thread(target=think, name="self-play-think", daemon=False)
        self._thread.start()
        return True

    def tick(self):
        """Poll the self-play lifecycle thread."""
        if self.status is SelfPlayStatus.ENDING:
            self._poll_end()
            return
        # Startup/enable/reconciliation may run on the UI's separate worker.
        # Defer new dispatch and preserve any unconsumed result until it ends.
        if self._ui_worker_busy():
            return
        if self._surrender_request is not None and self.status is SelfPlayStatus.READY:
            winner, reason = self._surrender_request
            self.end_match(winner=winner, reason=reason)
            return
        if self.status is SelfPlayStatus.READY and self.run_mode == "continuous":
            self.request_next_move()

        # Handle Thinking completion
        if self.status is SelfPlayStatus.THINKING and self._thread is not None and not self._thread.is_alive():
            token, snapshot, color, move, error = self._result
            self._thread = None
            if (token != self._token or token != self._current_token() or self.status is not SelfPlayStatus.THINKING
                    or self.state.turn != color or self.state.board != snapshot):
                self._fault("Game board changed while the engine was thinking.")
                return

            if error or not move:
                if not xiangqi.find_all_valid_moves(color, snapshot):
                    winner = "b" if color == "r" else "r"
                    self.state.handle_game_over(winner, reason="CHIẾU BÍ")
                    self.state.publish_match_end(winner='RED' if winner == 'r' else 'BLACK', reason='CHECKMATE')
                    self.status = SelfPlayStatus.FINISHED
                else:
                    self._fault(f"Engine failed to produce a legal move: {error}", physical=False)
                return

            if not xiangqi.is_valid_move(move[0], move[1], snapshot, color):
                self._fault(f"Engine produced illegal move: {move}", physical=False)
                return

            # Destination & piece captured
            destination = snapshot[move[1][1]][move[1][0]]
            expected_after, _ = xiangqi.make_temp_move(snapshot, move)
            try:
                move_ctx = self.state.create_move_context(move[0], move[1], MoveActor.ROBOT)
                self.state.mark_move_pending(move_ctx)
            except Exception as exc:
                self._fault(f"Cannot identify the robot's piece: {exc}", physical=False)
                return
            self.state.set_pending_physical_move(move, expected_after, destination, color)
            self._moving_before_board = snapshot
            self.status = SelfPlayStatus.MOVING

            def move_robot():
                try:
                    is_capture = destination != "."
                    targets = {}
                    physical = self._is_physical()
                    if token != self._current_token() or self.state.board != snapshot:
                        raise RuntimeError("Game changed before robot motion")
                    if physical:
                        from src.core.visual_move_coordinator import execute_pending_ai_motion
                        exec_res = execute_pending_ai_motion(self.state, self.hw)
                    else:
                        exec_res = self.hw.execute_piece_move(
                                s_col=move[0][0],
                                s_row=move[0][1],
                                d_col=move[1][0],
                                d_row=move[1][1],
                                is_capture=is_capture,
                                moving_visual_target=None,
                                captured_visual_target=None,


                                piece_id=move_ctx.piece_id,
                                captured_piece_id=move_ctx.captured_piece_id,
                                move_context=move_ctx,
                            )
                    self._result = (token, expected_after, color, exec_res, None)
                except Exception as exc:
                    self._result = (token, expected_after, color, None, exc)

            self._thread = threading.Thread(target=move_robot, name="self-play-motion", daemon=False)
            self._thread.start()

        # Handle Moving completion
        elif self.status is SelfPlayStatus.MOVING and self._thread is not None and not self._thread.is_alive():
            token, expected_after, color, result, error = self._result
            self._thread = None

            if token != self._token or token != self._current_token():
                self._fault("Game epoch changed during motion or camera verification; reconcile board")
                return

            from src.vision.pick_consensus import PickTargetUnavailable
            if isinstance(error, PickTargetUnavailable):
                from src.core.visual_move_coordinator import pause_visual_pick
                pause_visual_pick(self.state, error)
                self.status = SelfPlayStatus.PICK_PAUSED
                return
            if error or not isinstance(result, MotionExecutionResult) or not result.success:
                self._fault(f"Robot motion failed: {error or getattr(result, 'message', 'Motion rejected')}")
                return

            if self.state.turn != color or self.state.board != self._moving_before_board:
                self._fault("Game board changed during robot execution.")
                return

            if token != self._current_token() or self.state.board != self._moving_before_board:
                self._fault("Game changed during camera verification.")
                return

            if not self.state.commit_pending_physical_move():
                self._fault("State commit rejected.")
                return
            self.state.publish_committed_fen()

            # Check game termination
            next_turn = self.state.turn
            if (xiangqi.get_king_pos(next_turn,self.state.board) is None
                    or not xiangqi.find_all_valid_moves(next_turn,self.state.board)):
                winner = color
                reason = "CHIẾU BÍ"
                self.state.handle_game_over(winner)
                self.state.publish_match_end(winner='RED' if winner == 'r' else 'BLACK', reason='CHECKMATE')
                self.status = SelfPlayStatus.FINISHED
                print(f"[SELF-PLAY] 🏁 Game Over! Winner: {winner.upper()}")
            else:
                self.status = SelfPlayStatus.READY

    def end_match(self, *, winner="DRAW", reason="OTHER") -> bool:
        """Accept immediately; publish the outcome only after motion is settled."""
        if self.status in {SelfPlayStatus.IDLE, SelfPlayStatus.ENDING, SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}:
            return False
        if self._end_request is not None:
            # Recovery owns the interrupted transaction; no repeated stop or discard.
            return False
        was_moving = self.status is SelfPlayStatus.MOVING
        self._end_request = (winner, reason, was_moving)
        self.status = SelfPlayStatus.ENDING
        stopper = getattr(self.hw, "request_controlled_stop", None)
        if callable(stopper):
            self._stop_handle = stopper("End self-play", workers_finished=lambda:
                                       self._thread is None or not self._thread.is_alive())
        elif self._is_physical():
            self._fault("RECOVERY_REQUIRED: controlled stop unavailable; verify pendant")
            return True
        self._poll_end()
        return True

    def _poll_end(self):
        if self._thread is not None and self._thread.is_alive():
            return
        if self._ui_worker_busy():
            return
        stop = self._stop_handle
        if stop is not None:
            if not stop.done.is_set():
                return
            if not stop.result.safe:
                self._fault(f"RECOVERY_REQUIRED: {stop.result.reason}")
                return
            if not self.hw.stop_coordinator.safe_for_release():
                self._fault("RECOVERY_REQUIRED: fresh idle evidence expired before end-match")
                return
        _, _, was_moving = self._end_request
        if was_moving:
            completion = self._result
            self._thread = None
            if completion is None:
                self._fault("RECOVERY_REQUIRED: motion completion unavailable")
                return
            token, expected_after, color, result, error = completion
            # Only a complete, camera-verified operation may be committed at End.
            if (error or not isinstance(result, MotionExecutionResult) or not result.success
                    or token != self._token or token != self._current_token()
                    or self.state.board != self._moving_before_board):
                self._fault("RECOVERY_REQUIRED: interrupted move; retain capture/pending checkpoint")
                return
            if not self.state.commit_pending_physical_move():
                self._fault("RECOVERY_REQUIRED: final move commit rejected")
                return
            self._end_request = (*self._end_request[:2], False)
            next_turn = self.state.turn
            if (xiangqi.get_king_pos(next_turn, self.state.board) is None
                    or not xiangqi.find_all_valid_moves(next_turn, self.state.board)):
                self.state.handle_game_over(color)
                self._end_request = ("RED" if color == "r" else "BLACK", "CHECKMATE", False)
        if getattr(self.state, "pending_ai_move", None) is not None or getattr(self.state, "pending_move", None) is not None:
            self._fault("RECOVERY_REQUIRED: pending transaction must be reconciled before ending")
            return
        self._thread = None
        self._finish_end()

    def _finish_end(self):
        winner, reason, _ = self._end_request
        if self.state.game_over and self.state.winner is not None:
            winner = "RED" if self.state.winner == "r" else "BLACK"
            reason = getattr(self.state, "game_over_reason", "") or "CHECKMATE"
        try:
            if reason == "RESIGN" and not self.state.game_over:
                self.state.handle_game_over("r" if winner == "RED" else "b", reason="RESIGN")
                if not self.state.game_over:
                    from src.core.session_journal import JournalError
                    raise JournalError("Surrender outcome was not saved")
            self.state.publish_match_end(winner=winner, reason=reason)
        except Exception as exc:
            from src.core.session_journal import JournalError
            if isinstance(exc, JournalError):
                self._fault(f"RECOVERY_REQUIRED: end-match state not saved: {exc}")
                return
            self.state.projection_error = f"End-match projection pending: {exc}"
        self._end_request = None
        self._surrender_request = None
        self._result = None
        self._epoch += 1
        self.status = SelfPlayStatus.ENDED
        # External projection errors must not undo local termination.
        try:
            self.state.publish_committed_fen()
        except Exception as exc:
            self.state.projection_error = f"End-match projection pending: {exc}"
        self.state.set_status("Self-play match ended.", color=(180, 100, 0), duration=6.0)

    def _start_fault(self, message: str) -> bool:
        self.status = SelfPlayStatus.FAULTED
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Start Fault: {message}")
        return False

    def _fault(self, message: str, *, physical: bool = True):
        from src.core.project_logging import event
        import logging
        event("self_play.fault", message, level=logging.ERROR,
              code="MOVE_REJECTED" if physical else "ENGINE_FAILED", physical=physical,
              fen=self.state.current_fen, move_id=getattr(getattr(self.state, "pending_move", None), "move_id", None))
        self.status = SelfPlayStatus.FAULTED
        if physical:
            self.state.physical_sync_fault = True
            self.state.snapshot_continue_required = True
            self.state.snapshot_continue_can_commit_pending = False
        if physical and hasattr(self.state, "mark_move_failed"):
            self.state.mark_move_failed(message)
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Runtime Fault: {message}")
