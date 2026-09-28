# =============================================================================
# === FILE: src/core/self_play_controller.py ===
# === Unified Autonomous Robot-vs-Robot Controller for Physical & Virtual Modes ===
# =============================================================================
from enum import Enum
import threading
import time
from typing import Any, Optional, Tuple
from src.core import xiangqi
from src.hardware.robot_VIP import MotionResult, MotionStage


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
        # 1. Readiness check across Physical and Virtual backends
        backend_type = getattr(getattr(self.hw, "config", None), "ROBOT_BACKEND", "PHYSICAL").upper()
        dry_run = getattr(self.hw, "dry_run", False)

        if backend_type == "PHYSICAL" and not dry_run:
            robot = getattr(self.hw, "robot", None)
            backend = getattr(self.hw, "backend", None)
            if backend is None and (robot is None or not robot.connected):
                return self._start_fault("Self-play requires a connected physical robot in live mode.")
        elif not getattr(self.hw, "is_robot_ready", True):
            # In Virtual or Dry-run mode, check if robot/virtual backend is ready
            return self._start_fault("Robot backend is not ready for self-play.")

        if run_mode not in {"step", "continuous"}:
            return self._start_fault("Choose Step or Continuous mode.")

        # 2. Check engine availability if controller supports it
        if hasattr(self.hw, "difficulty_availability"):
            avail = self.hw.difficulty_availability()
            if avail and (not avail.get(red_difficulty) or not avail.get(black_difficulty)):
                return self._start_fault("Both selected engine difficulties must be ready.")

        # 3. Camera baseline verification (if physical camera is active)
        if hasattr(self.hw, "cam_monitor") and self.hw.cam_monitor is not None and not dry_run:
            if hasattr(self.hw, "capture_baseline_if_needed"):
                self.hw.capture_baseline_if_needed(force_delay=1.0)
            if hasattr(self.hw, "verify_physical_board") and callable(self.hw.verify_physical_board):
                if not self.hw.verify_physical_board(self.state.board):
                    return self._start_fault("Camera board check failed. Arrange all pieces, then retry.")

        self.state.physical_sync_fault = False
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
        snapshot = [row[:] for row in self.state.board]
        color = self.state.turn
        difficulty = self.red_difficulty if color == "r" else self.black_difficulty
        token = (self._epoch, getattr(self.state, "move_number", 1), color, len(self.state.move_history))
        self._token = token
        self.status = SelfPlayStatus.THINKING

        def think():
            try:
                move = None
                if hasattr(self.hw, "ai_ctrl") and self.hw.ai_ctrl is not None:
                    # Check if pick_move accepts difficulty parameter
                    try:
                        move = self.hw.ai_ctrl.pick_move(snapshot, color=color, difficulty=difficulty)
                    except TypeError:
                        move = self.hw.ai_ctrl.pick_move(snapshot, color=color)
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
            if token != self._token or self.status is not SelfPlayStatus.THINKING:
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
            self.state.set_pending_physical_move(move, expected_after, destination, color)
            self.status = SelfPlayStatus.MOVING

            def move_robot():
                try:
                    is_capture = destination != "."
                    targets = {}
                    if hasattr(self.hw, "get_robot_center_pick_targets"):
                        targets = self.hw.get_robot_center_pick_targets(
                            {"captured": move[1]} if is_capture else {"moving": move[0]}
                        )

                    # Unified motion execution: use execute_piece_move or robot.move_piece
                    if hasattr(self.hw, "execute_piece_move"):
                        move_ctx = None
                        p_id = None
                        cap_p_id = None
                        if hasattr(self.state, "create_move_context"):
                            try:
                                move_ctx = self.state.create_move_context(move[0], move[1], actor="ROBOT")
                                p_id = getattr(move_ctx, "piece_id", None)
                                cap_p_id = getattr(move_ctx, "captured_piece_id", None)
                                if hasattr(self.state, "mark_move_pending"):
                                    self.state.mark_move_pending(move_ctx)
                            except Exception as e:
                                print(f"[SELF-PLAY] MoveContext build: {e}")

                        exec_res = self.hw.execute_piece_move(
                            s_col=move[0][0],
                            s_row=move[0][1],
                            d_col=move[1][0],
                            d_row=move[1][1],
                            is_capture=is_capture,
                            moving_visual_target=targets.get("moving"),
                            captured_visual_target=targets.get("captured"),
                            piece_id=p_id,
                            captured_piece_id=cap_p_id,
                            move_context=move_ctx,
                        )
                        success = getattr(exec_res, "success", bool(exec_res))
                        result = MotionResult(success, MotionStage.COMPLETED if success else MotionStage.PLACE)
                    elif hasattr(self.hw, "robot") and hasattr(self.hw.robot, "move_piece"):
                        result = self.hw.robot.move_piece(
                            move[0][0], move[0][1], move[1][0], move[1][1], is_capture,
                            moving_visual_target=targets.get("moving"),
                            captured_visual_target=targets.get("captured"),
                        )
                        if not isinstance(result, MotionResult):
                            result = MotionResult(bool(result), MotionStage.COMPLETED)
                    elif hasattr(self.hw, "move_piece"):
                        ok = self.hw.move_piece(move[0][0], move[0][1], move[1][0], move[1][1], is_capture)
                        result = MotionResult(bool(ok), MotionStage.COMPLETED if ok else MotionStage.PLACE)
                    else:
                        result = MotionResult(True, MotionStage.COMPLETED)

                    self._result = (token, expected_after, color, result, None)
                except Exception as exc:
                    self._result = (token, expected_after, color, None, exc)

            self._thread = threading.Thread(target=move_robot, daemon=True)
            self._thread.start()

        # Handle Moving completion
        elif self.status in {SelfPlayStatus.MOVING, SelfPlayStatus.ENDING} and self._thread is not None and not self._thread.is_alive():
            token, expected_after, color, result, error = self._result
            self._thread = None

            if self.status is SelfPlayStatus.ENDING or token != self._token:
                if hasattr(self.hw, "robot") and hasattr(self.hw.robot, "go_to_home_chess"):
                    self.hw.robot.go_to_home_chess()
                self.state.set_status("Self-play ended after motion.", color=(180, 100, 0), duration=10.0)
                self.status = SelfPlayStatus.ENDED
                return

            if error or not isinstance(result, MotionResult) or not result.success:
                self._fault(f"Robot motion failed: {error or getattr(result, 'error', 'Motion rejected')}")
                return

            # Camera verification on physical hardware
            if not getattr(self.hw, "dry_run", False) and hasattr(self.hw, "verify_physical_board"):
                if not self.hw.verify_physical_board(expected_after):
                    self._fault("Post-motion physical board verification failed.")
                    return

            if not self.state.commit_pending_physical_move():
                self._fault("State commit rejected.")
                return

            # Update Digital Twin scene if available
            if hasattr(self.hw, "reconcile_human_move") and hasattr(self.state, "last_committed_move"):
                try:
                    self.hw.reconcile_human_move(self.state.last_committed_move)
                except Exception:
                    pass

            # Check game termination
            next_turn = self.state.turn
            if xiangqi.is_checkmate(next_turn, self.state.board):
                winner = color
                reason = "CHIẾU BÍ"
                self.state.handle_game_over(winner, reason=reason)
                self.status = SelfPlayStatus.FINISHED
                print(f"[SELF-PLAY] 🏁 Game Over! Winner: {winner.upper()}")
            else:
                self.status = SelfPlayStatus.READY

    def end_match(self) -> bool:
        """Safely terminate the autonomous match and park the arm."""
        if self.status in {SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}:
            return False
        self._epoch += 1
        if self._thread is not None and self._thread.is_alive():
            self.status = SelfPlayStatus.ENDING
            return True
        if hasattr(self.hw, "robot") and hasattr(self.hw.robot, "go_to_home_chess"):
            try:
                self.hw.robot.go_to_home_chess()
            except Exception:
                pass
        self.status = SelfPlayStatus.ENDED
        self.state.set_status("Self-play match ended.", color=(180, 100, 0), duration=6.0)
        return True

    def _start_fault(self, message: str) -> bool:
        self.status = SelfPlayStatus.FAULTED
        self.state.physical_sync_fault = True
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Start Fault: {message}")
        return False

    def _fault(self, message: str):
        self.status = SelfPlayStatus.FAULTED
        self.state.physical_sync_fault = True
        self.state.set_status(message, color=(180, 0, 0), duration=15.0)
        print(f"[SELF-PLAY] ❌ Runtime Fault: {message}")
