"""Fail-closed physical Robot-vs-Robot match orchestration."""
from __future__ import annotations

from enum import Enum
import threading

from src.core import xiangqi
from src.hardware.robot_VIP import MotionResult


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
    """One owner for all autonomous physical turns; no UI dependencies."""
    def __init__(self, state, hw):
        self.state, self.hw = state, hw
        self.status = SelfPlayStatus.IDLE
        self.red_difficulty = self.black_difficulty = None
        self.run_mode = "step"
        self._epoch = 0
        self._thread = None
        self._result = None
        self._token = None
        self._home_pending = False

    @property
    def active(self):
        return self.status in {SelfPlayStatus.READY, SelfPlayStatus.THINKING, SelfPlayStatus.MOVING, SelfPlayStatus.ENDING}

    @property
    def accepts_next(self):
        return self.status is SelfPlayStatus.READY and self.run_mode == "step"

    @property
    def human_input_disabled(self):
        return self.active or self.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED}

    def start(self, red_difficulty, black_difficulty, run_mode):
        robot = getattr(self.hw, "robot", None)
        if getattr(self.hw, "dry_run", False) or robot is None or not robot.connected:
            return self._start_fault("Self-play requires a connected physical robot.")
        if run_mode not in {"step", "continuous"}:
            return self._start_fault("Choose Step or Continuous mode.")
        if not self.hw.difficulty_availability().get(red_difficulty) or not self.hw.difficulty_availability().get(black_difficulty):
            return self._start_fault("Both selected engine difficulties must be ready.")
        # Give the camera a fresh baseline before requiring its strict board/FEN check.
        self.hw.capture_baseline_if_needed(force_delay=1.0)
        if not self.hw.verify_physical_board(self.state.board):
            return self._start_fault("Camera board check failed. Arrange all pieces, then recalibrate/retry self-play.")
        self.state.physical_sync_fault = False
        self.red_difficulty, self.black_difficulty, self.run_mode = red_difficulty, black_difficulty, run_mode
        self.status = SelfPlayStatus.READY
        self._epoch += 1
        return True

    def set_run_mode(self, run_mode):
        if self.status is not SelfPlayStatus.READY or run_mode not in {"step", "continuous"}:
            return False
        self.run_mode = run_mode
        return True

    def request_next_move(self):
        if self.status is not SelfPlayStatus.READY:
            return False
        snapshot = [row[:] for row in self.state.board]
        color = self.state.turn
        difficulty = self.red_difficulty if color == "r" else self.black_difficulty
        token = (self._epoch, self.state.game_epoch, color, len(self.state.move_history))
        self._token, self.status = token, SelfPlayStatus.THINKING
        def think():
            try:
                self._result = (token, snapshot, color, self.hw.ai_ctrl.pick_move(snapshot, color=color, difficulty=difficulty), None)
            except Exception as exc:
                self._result = (token, snapshot, color, None, exc)
        self._thread = threading.Thread(target=think, daemon=True)
        self._thread.start()
        return True

    def tick(self):
        if self.status is SelfPlayStatus.READY and self.run_mode == "continuous":
            self.request_next_move()
        if self.status is SelfPlayStatus.THINKING and self._thread is not None and not self._thread.is_alive():
            token, snapshot, color, move, error = self._result
            self._thread = None
            if token != self._token or self.status is not SelfPlayStatus.THINKING:
                return
            if error or not move:
                if not xiangqi.find_all_valid_moves(color, snapshot):
                    self.state.handle_game_over("b" if color == "r" else "r")
                    self.status = SelfPlayStatus.FINISHED
                else:
                    self._fault("Engine failed to produce a legal move")
                return
            if not xiangqi.is_valid_move(move[0], move[1], snapshot, color) or not self.hw.verify_physical_board(snapshot):
                self._fault("Pre-dispatch board verification failed")
                return
            destination = snapshot[move[1][1]][move[1][0]]
            expected_after, _ = xiangqi.make_temp_move(snapshot, move)
            self.state.set_pending_physical_move(move, expected_after, destination, color)
            self.status = SelfPlayStatus.MOVING
            def move_robot():
                try:
                    is_capture = destination != "."
                    targets = self.hw.get_robot_center_pick_targets(
                        {"captured": move[1]} if is_capture else {"moving": move[0]}
                    )
                    def refresh_moving_target():
                        if not is_capture:
                            return targets.get("moving")
                        return self.hw.get_robot_center_pick_targets({"moving": move[0]}).get("moving")
                    result = self.hw.robot.move_piece(
                        move[0][0], move[0][1], move[1][0], move[1][1], is_capture,
                        moving_visual_target=targets.get("moving"),
                        captured_visual_target=targets.get("captured"),
                        refresh_moving_visual_target=refresh_moving_target,
                        verify_capture_cleared=lambda: not is_capture or self.hw.is_cell_visually_clear(move[1]),
                    )
                    self._result = (token, expected_after, color, result, None)
                except Exception as exc:
                    self._result = (token, expected_after, color, None, exc)
            self._thread = threading.Thread(target=move_robot, daemon=True)
            self._thread.start()
        elif self.status in {SelfPlayStatus.MOVING, SelfPlayStatus.ENDING} and self._thread is not None and not self._thread.is_alive():
            token, expected_after, color, result, error = self._result
            self._thread = None
            if self.status is SelfPlayStatus.ENDING or token != self._token:
                self.hw.robot.go_to_home_chess()
                self.state.physical_sync_fault = True
                self.state.set_status("Self-play ended after motion; reconcile the physical board before continuing.", color=(180, 0, 0), duration=30.0)
                self.status = SelfPlayStatus.ENDED
                return
            if error or not isinstance(result, MotionResult) or not result.success or not self.hw.verify_physical_board(expected_after):
                self._fault("Robot motion or final board verification failed")
                return
            if not self.state.commit_pending_physical_move():
                self._fault("Physical move commit rejected")
                return
            self.hw.capture_baseline_if_needed(force_delay=1.0)
            if xiangqi.get_king_pos(self.state.turn, self.state.board) is None:
                self.state.handle_game_over(color)
                self.status = SelfPlayStatus.FINISHED
            else:
                self.status = SelfPlayStatus.READY

    def end_match(self):
        if self.status in {SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}:
            return False
        self._epoch += 1
        if self._thread is not None and self._thread.is_alive():
            self.status = SelfPlayStatus.ENDING
            return
        self.hw.robot.go_to_home_chess()
        self.status = SelfPlayStatus.ENDED
        return True

    def _start_fault(self, message):
        self.status = SelfPlayStatus.FAULTED
        self.state.physical_sync_fault = True
        self.state.set_status(message, color=(180, 0, 0), duration=30.0)
        return False

    def _fault(self, message):
        self.state.physical_sync_fault = True
        self.state.set_status(message, color=(180, 0, 0), duration=20.0)
        self.status = SelfPlayStatus.FAULTED
