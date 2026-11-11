"""Wait for verified startup recovery, then enable a physical session."""
import logging

from src.core.project_logging import event


class AutomaticPhysicalStartup:
    WAIT_FLAGS = ("recovery_required", "physical_sync_fault", "move_sync_error",
                  "pick_test_mode", "pick_test_fault", "pick_test_resume_required", "emergency_mode",
                  "snapshot_continue_required", "manual_override_active", "ai_thinking")
    PENDING_FIELDS = ("pending_move", "pending_ai_move", "pending_test_motion",
                      "visual_capture_checkpoint", "visual_pick_retry")

    def __init__(self, state, hardware):
        self.state = state
        self.hardware = hardware
        self.baseline_checked = False
        self.finished = False
        self.cancelled = False
        self.attempts = 0
        self.MAX_ATTEMPTS = 10
        self.last_wait_reason = None
        self._scheduled_stop_generation = None

    def cancel(self, reason="session_cancelled"):
        if not self.cancelled:
            event("physical.auto_enable_cancelled", "Automatic enable cancelled", reason=reason)
        self.cancelled = True
        self.finished = True

    def ensure_active(self):
        if self.cancelled:
            raise RuntimeError("Automatic enable cancelled")
        stop = getattr(self.hardware, "stop_coordinator", None)
        if (self._scheduled_stop_generation is not None
                and getattr(stop, "generation", 0) != self._scheduled_stop_generation):
            raise RuntimeError("Automatic enable cancelled by a newer stop request")
        reason = self._terminal_reason() or self._state_wait_reason() or self._stop_wait_reason(in_worker=True)
        if reason:
            raise RuntimeError(f"Automatic enable cancelled by pending prerequisite: {reason}")

    def _terminal_reason(self):
        hw = self.hardware
        if not getattr(getattr(hw, "profile", None), "physical_robot_enabled", False):
            return "physical_session_disabled"
        if getattr(hw, "dry_run", True):
            return "dry_run"
        if not getattr(hw.config, "AUTO_ENABLE_PHYSICAL_ON_STARTUP", True):
            return "automatic_enable_disabled"
        if getattr(hw, "_closing", False):
            return "session_closing"
        if getattr(getattr(hw, "session_control", None), "action", None):
            return "session_control_pending"
        for name in ("mode_change_pending", "game_over"):
            if getattr(self.state, name, False):
                return name
        return None

    def _state_wait_reason(self):
        for name in self.WAIT_FLAGS:
            if getattr(self.state, name, False):
                return name
        for name in self.PENDING_FIELDS:
            if getattr(self.state, name, None) is not None:
                return name
        if not self.baseline_checked:
            return "baseline_not_checked"
        return None

    def _stop_wait_reason(self, *, in_worker=False):
        stop = getattr(self.hardware, "stop_coordinator", None)
        if stop is None:
            return None
        if stop.blocked:
            return "stop_in_progress"
        request = getattr(stop, "request", None)
        if request is not None:
            if not request.done.is_set():
                return "stop_in_progress"
            if not request.result.safe:
                return "stop_unverified"
            verified = getattr(stop, "safe_for_release", None)
            if not callable(verified) or not verified(ignore_current_worker=in_worker):
                return "stop_evidence_incomplete"
        return None

    def _wait(self, reason):
        if reason != self.last_wait_reason:
            self.last_wait_reason = reason
            event("physical.auto_enable_waiting", "Automatic enable is waiting for verification",
                  reason=reason, baseline_checked=self.baseline_checked,
                  stop_generation=getattr(getattr(self.hardware, "stop_coordinator", None), "generation", 0),
                  waiting_flags=[name for name in self.WAIT_FLAGS if getattr(self.state, name, False)],
                  pending_fields=[name for name in self.PENDING_FIELDS if getattr(self.state, name, None) is not None])

    @staticmethod
    def _unknown_enable_outcome(error):
        from src.hardware.rpc_transport import RpcOutcomeUnknown
        seen = set()
        while isinstance(error, BaseException) and id(error) not in seen:
            seen.add(id(error))
            if isinstance(error, (RpcOutcomeUnknown, OSError)):
                return True
            error = error.__cause__ or error.__context__
        return False

    def tick(self):
        if self.cancelled:
            self.finished = True
            return
        if self.finished:
            return
        state, hw = self.state, self.hardware
        terminal = self._terminal_reason()
        if terminal:
            self.cancel(terminal)
            return
        stop = getattr(hw, "stop_coordinator", None)
        if hw.is_robot_ready:
            self.cancel("already_ready")
            return
        waiting = self._state_wait_reason() or self._stop_wait_reason()
        if waiting:
            self._wait(waiting)
            return
        if hw.motion_worker.busy:
            self._wait("worker_busy")
            return

        def completed(result, error):
            if self.cancelled:
                self.finished = True
                return
            if error is not None or not result:
                error = error or "Controller has not confirmed enable"
                self.attempts += 1
                event("physical.auto_enable_failed", str(error), level=logging.ERROR,
                      attempt=self.attempts)
                if self._unknown_enable_outcome(error):
                    self.cancel("enable_outcome_unknown")
                    state.set_status(
                        f"Enable reply is unknown: {error}. Automatic retry blocked. "
                        "Inspect the controller before starting a new session.", duration=60)
                elif self.attempts >= self.MAX_ATTEMPTS:
                    self.finished = True
                    state.set_status(
                        f"Robot enable failed {self.attempts} times: {error}. "
                        "Restart the session to try again.", duration=60)
                else:
                    # Retry on the next tick instead of asking for a key press.
                    self.finished = False
                    state.set_status(f"Enabling the robot failed: {error}. Retrying...", duration=15)
            else:
                self.finished = True
                state.set_status("Robot motion authorization enabled automatically. No HOME run or gripper change.", duration=30)
                event("physical.auto_enabled", "Authorization enabled through startup checks")

        self.finished = True
        self.lined_up = True
        stop_generation = self._scheduled_stop_generation = getattr(stop, "generation", 0)
        if not hw.motion_worker.start(
                lambda: hw.activate_physical_game(
                    state, commissioned=True,
                    expected_stop_generation=stop_generation,
                    startup_guard=self.ensure_active), completed):
            self.finished = False
            self._wait("worker_submission_rejected")
        else:
            self.last_wait_reason = None
            event("physical.auto_enable_started", "Automatic enable submitted to the motion worker",
                  attempt=self.attempts + 1, stop_generation=self._scheduled_stop_generation)
