# =============================================================================
# === FILE: src/core/self_play_controller.py ===
# === Unified Autonomous Robot-vs-Robot Controller for Physical & Virtual Modes ===
# =============================================================================
from enum import Enum
import threading
import time
import inspect
from typing import Any, Optional, Tuple
from src.core import xiangqi
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

    def _current_token(self):
        return (self._epoch, getattr(self.state,"game_epoch",0),
                getattr(self.state,"ai_epoch",0),getattr(self.state,"move_number",1),
                self.state.turn,len(self.state.move_history))

    def _is_physical(self):
        return getattr(self.hw,"simulation_runtime",None) is None and not getattr(self.hw,"dry_run",False)

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
        return (self.status is SelfPlayStatus.READY
                and not getattr(self.state, "game_over", False)
                and not getattr(self.state, "turn_confirmation_required", False)
                and (self._thread is None or not self._thread.is_alive()))

    @property
    def human_input_disabled(self) -> bool:
        return self.active or self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED}

    @property
    def recovery_input_allowed(self):
        return (self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}
                and (self._thread is None or not self._thread.is_alive()))

    def finish_recovery(self):
        if (not self.recovery_input_allowed or self.state.physical_sync_fault
                or self.state.move_sync_error or self.state.pending_ai_move is not None):
            return False
        self.status = SelfPlayStatus.IDLE
        return True

    def retry_visual_pick(self):
        from src.core.visual_move_coordinator import retry_is_current, execute_pending_ai_motion
        if self.status is not SelfPlayStatus.PICK_PAUSED or not retry_is_current(self.state):
            return False
        request = self.state.visual_pick_retry
        token = self._current_token()
        if token != self._token:
            self._fault("Retry belongs to a stale self-play epoch")
            return False
        expected = self.state.pending_ai_move["expected_board"]
        color = self.state.turn
        def run():
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

    def start(self, red_difficulty: str = "medium", black_difficulty: str = "medium", run_mode: str = "step") -> bool:
        """Initialize and start an autonomous self-play match."""
        if self._thread is not None and self._thread.is_alive():
            self.state.set_status("Wait for the previous self-play worker before restarting.",
                                  color=(180, 100, 0), duration=8.0)
            return False
        if getattr(self.state, "game_over", False):
            self.status = SelfPlayStatus.FINISHED
            self.state.set_status("Ván đã kết thúc. Chọn New Game trước khi bắt đầu self-play.",
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
        if not getattr(self.hw, "dry_run", True):
            self.state.api_client.ensure_match(red_name="Người chơi Thật", black_name="Robot AI",
                                               initial_fen=self.state.current_fen)
        print(f"[SELF-PLAY] 🚀 Started! Red: {red_difficulty}, Black: {black_difficulty}, Mode: {run_mode}")
        return True

    def set_run_mode(self, run_mode: str) -> bool:
        if self.status not in {SelfPlayStatus.READY, SelfPlayStatus.IDLE} or run_mode not in {"step", "continuous"}:
            return False
        self.run_mode = run_mode
        print(f"[SELF-PLAY] Cadence switched to: {run_mode.upper()}")
        return True

    def request_next_move(self) -> bool:
        if self.status is not SelfPlayStatus.READY:
            return False
        if getattr(self.state, "game_over", False):
            self.status = SelfPlayStatus.FINISHED
            return False
        if getattr(self.state, "turn_confirmation_required", False):
            return self._start_fault("Xác nhận lượt Đỏ/Đen trước khi đi tiếp.")
        if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
            return False
        if (not getattr(self.hw, "is_robot_ready", False)
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

        self._thread = threading.Thread(target=think, daemon=True)
        self._thread.start()
        return True

    def tick(self):
        """Poll the self-play lifecycle thread."""
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
                    self.state.api_client.end_match(winner='RED' if winner == 'r' else 'BLACK', reason='CHECKMATE')
                    self.status = SelfPlayStatus.FINISHED
                else:
                    self._fault(f"Engine failed to produce a legal move: {error}")
                return

            if not xiangqi.is_valid_move(move[0], move[1], snapshot, color):
                self._fault(f"Engine produced illegal move: {move}")
                return

            # Destination & piece captured
            destination = snapshot[move[1][1]][move[1][0]]
            expected_after, _ = xiangqi.make_temp_move(snapshot, move)
            try:
                move_ctx = self.state.create_move_context(move[0], move[1], MoveActor.ROBOT)
                self.state.mark_move_pending(move_ctx)
            except Exception as exc:
                self._fault(f"Cannot identify the robot's piece: {exc}")
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

            self._thread = threading.Thread(target=move_robot, daemon=True)
            self._thread.start()

        # Handle Moving completion
        elif self.status in {SelfPlayStatus.MOVING, SelfPlayStatus.ENDING} and self._thread is not None and not self._thread.is_alive():
            token, expected_after, color, result, error = self._result
            self._thread = None

            if self.status is SelfPlayStatus.ENDING:
                self.state.mark_move_failed("Self-play ended during motion; camera reconciliation required")
                self.state.move_sync_error = self.state.move_execution_error
                self.state.set_status("Self-play ended after motion.", color=(180, 100, 0), duration=10.0)
                self.status = SelfPlayStatus.ENDED
                return
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
            self.state.api_client.send_move_update_board(self.state.current_fen)
            if self.state.move_sync_error or self.state.physical_sync_fault:
                self._fault("Move committed; repair the board mirror before continuing")
                return

            # Check game termination
            next_turn = self.state.turn
            if (xiangqi.get_king_pos(next_turn,self.state.board) is None
                    or not xiangqi.find_all_valid_moves(next_turn,self.state.board)):
                winner = color
                reason = "CHIẾU BÍ"
                self.state.handle_game_over(winner)
                self.state.api_client.end_match(winner='RED' if winner == 'r' else 'BLACK', reason='CHECKMATE')
                self.status = SelfPlayStatus.FINISHED
                print(f"[SELF-PLAY] 🏁 Game Over! Winner: {winner.upper()}")
            else:
                self.status = SelfPlayStatus.READY

    def end_match(self, *, winner="DRAW", reason="OTHER") -> bool:
        """Stop scheduling moves; never issue an implicit hardware retreat."""
        if self.status in {SelfPlayStatus.IDLE, SelfPlayStatus.ENDING, SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}:
            return False
        self._epoch += 1
        self.state.api_client.end_match(winner=winner, reason=reason)
        if self.status is SelfPlayStatus.MOVING and self._thread is not None and self._thread.is_alive():
            self.status = SelfPlayStatus.ENDING
            return True
        if self.status in {SelfPlayStatus.MOVING, SelfPlayStatus.PICK_PAUSED}:
            self.state.mark_move_failed("Self-play stopped before camera confirmation")
            self.state.move_sync_error = self.state.move_execution_error
            self.state.visual_pick_retry = None
        self.status = SelfPlayStatus.ENDED
        self.state.set_status("Self-play match ended.", color=(180, 100, 0), duration=6.0)
        return True

    def _start_fault(self, message: str) -> bool:
        self.status = SelfPlayStatus.FAULTED
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Start Fault: {message}")
        return False

    def _fault(self, message: str):
        from src.core.project_logging import event
        import logging
        event("self_play.fault", message, level=logging.ERROR, code="MOVE_REJECTED",
              fen=self.state.current_fen, move_id=getattr(getattr(self.state, "pending_move", None), "move_id", None))
        self.status = SelfPlayStatus.FAULTED
        self.state.physical_sync_fault = True
        self.state.snapshot_continue_required = True
        self.state.snapshot_continue_can_commit_pending = False
        if hasattr(self.state, "mark_move_failed"):
            self.state.mark_move_failed(message)
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Runtime Fault: {message}")
