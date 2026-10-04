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
        }

    @property
    def accepts_next(self) -> bool:
        return self.status is SelfPlayStatus.READY and self.run_mode == "step"

    @property
    def human_input_disabled(self) -> bool:
        return self.active or self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED}

    def start(self, red_difficulty: str = "medium", black_difficulty: str = "medium", run_mode: str = "step") -> bool:
        """Initialize and start an autonomous self-play match."""
        if self._thread is not None and self._thread.is_alive():
            self.state.set_status("Wait for the previous self-play worker before restarting.",
                                  color=(180, 100, 0), duration=8.0)
            return False
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
        if (not getattr(self.hw, "is_robot_ready", False)
                or getattr(self.state, "move_sync_error", None)
                or getattr(self.state, "physical_sync_fault", False)):
            self._fault("Self-play blocked by robot readiness or board synchronization fault.")
            return False
        if self._is_physical():
            try:
                if not self.hw.verify_physical_board(self.state.board):
                    self._fault("Pre-motion full-board camera verification failed.")
                    return False
            except Exception as exc:
                self._fault(f"Pre-motion camera verification failed: {exc}")
                return False
        snapshot = [row[:] for row in self.state.board]
        color = self.state.turn
        difficulty = self.red_difficulty if color == "r" else self.black_difficulty
        token = self._current_token()
        self._token = token
        self.status = SelfPlayStatus.THINKING

        def think():
            try:
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
                    if physical and not self.hw.verify_physical_board(snapshot):
                        raise RuntimeError("Pre-motion full-board camera verification failed")
                    visual = bool(getattr(getattr(self.hw,"config",None),"VISUAL_PICK_ENABLED",False))
                    if physical and visual and hasattr(self.hw, "get_robot_center_pick_targets"):
                        targets = self.hw.get_robot_center_pick_targets(
                            {"captured": move[1]} if is_capture else {"moving": move[0]}
                        )

                    if token != self._current_token() or self.state.board != snapshot:
                        raise RuntimeError("Game changed during pre-motion camera verification")
                    exec_res = self.hw.execute_piece_move(
                            s_col=move[0][0],
                            s_row=move[0][1],
                            d_col=move[1][0],
                            d_row=move[1][1],
                            is_capture=is_capture,
                            moving_visual_target=targets.get("moving"),
                            captured_visual_target=targets.get("captured"),
                            refresh_moving_visual_target=(lambda: self.hw.get_robot_center_pick_targets(
                                {"moving":move[0]}).get("moving")) if physical and visual and is_capture else None,
                            verify_capture_cleared=(lambda:self.hw.is_cell_visually_clear(move[1])) if physical and is_capture else None,
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

            if self.status is SelfPlayStatus.ENDING or token != self._token or token != self._current_token():
                self.state.mark_move_failed("Self-play ended during motion; camera reconciliation required")
                self.state.move_sync_error = self.state.move_execution_error
                self.state.set_status("Self-play ended after motion.", color=(180, 100, 0), duration=10.0)
                self.status = SelfPlayStatus.ENDED
                return

            if error or not isinstance(result, MotionExecutionResult) or not result.success:
                self._fault(f"Robot motion failed: {error or getattr(result, 'message', 'Motion rejected')}")
                return

            if self.state.turn != color or self.state.board != self._moving_before_board:
                self._fault("Game board changed during robot execution.")
                return

            # Camera verification on physical hardware
            if self._is_physical():
                try:
                    verified = self.hw.verify_physical_board(expected_after)
                except Exception as exc:
                    self._fault(f"Post-motion camera verification failed: {exc}")
                    return
                if not verified:
                    self._fault("Post-motion physical board verification failed.")
                    return
            if token != self._current_token() or self.state.board != self._moving_before_board:
                self._fault("Game changed during camera verification.")
                return

            if not self.state.commit_pending_physical_move():
                self._fault("State commit rejected.")
                return

            # Check game termination
            next_turn = self.state.turn
            if (xiangqi.get_king_pos(next_turn,self.state.board) is None
                    or not xiangqi.find_all_valid_moves(next_turn,self.state.board)):
                winner = color
                reason = "CHIẾU BÍ"
                self.state.handle_game_over(winner)
                self.status = SelfPlayStatus.FINISHED
                print(f"[SELF-PLAY] 🏁 Game Over! Winner: {winner.upper()}")
            else:
                self.status = SelfPlayStatus.READY

    def end_match(self) -> bool:
        """Stop scheduling moves; never issue an implicit hardware retreat."""
        if self.status in {SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}:
            return False
        self._epoch += 1
        if self.status is SelfPlayStatus.MOVING and self._thread is not None and self._thread.is_alive():
            self.status = SelfPlayStatus.ENDING
            return True
        if self.status is SelfPlayStatus.MOVING:
            self.state.mark_move_failed("Self-play stopped before camera confirmation")
            self.state.move_sync_error = self.state.move_execution_error
        self.status = SelfPlayStatus.ENDED
        self.state.set_status("Self-play match ended.", color=(180, 100, 0), duration=6.0)
        return True

    def _start_fault(self, message: str) -> bool:
        self.status = SelfPlayStatus.FAULTED
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Start Fault: {message}")
        return False

    def _fault(self, message: str):
        self.status = SelfPlayStatus.FAULTED
        self.state.physical_sync_fault = True
        self.state.snapshot_continue_required = True
        self.state.snapshot_continue_can_commit_pending = False
        if hasattr(self.state, "mark_move_failed"):
            self.state.mark_move_failed(message)
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Runtime Fault: {message}")
