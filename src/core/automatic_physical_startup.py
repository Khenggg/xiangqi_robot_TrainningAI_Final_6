"""One automatic enable attempt for a newly selected physical session."""
import logging

from src.core.project_logging import event


class AutomaticPhysicalStartup:
    def __init__(self, state, hardware):
        self.state = state
        self.hardware = hardware
        self.baseline_checked = False
        self.finished = False
        self.cancelled = False
        self.attempts = 0
        self.MAX_ATTEMPTS = 10

    def cancel(self):
        self.cancelled = True
        self.finished = True

    def ensure_active(self):
        if self.cancelled:
            raise RuntimeError("Automatic enable cancelled")

    def tick(self):
        if self.finished:
            return
        state, hw = self.state, self.hardware
        profile = getattr(hw, "profile", None)
        if (not getattr(profile, "physical_robot_enabled", False)
                or getattr(hw, "dry_run", True)
                or not getattr(hw.config, "AUTO_ENABLE_PHYSICAL_ON_STARTUP", True)):
            self.cancel()
            return
        stop = getattr(hw, "stop_coordinator", None)
        controls = getattr(hw, "session_control", None)
        # A stop only pauses the attempt while it is actually running; the app no
        # longer waits for an operator to re-enable the robot by hand.
        if (getattr(hw, "_closing", False)
                or getattr(controls, "action", None)
                or any(getattr(state, name, False) for name in (
                    "recovery_required", "mode_change_pending", "physical_sync_fault",
                    "move_sync_error", "game_over", "pick_test_mode", "pick_test_fault",
                    "pick_test_resume_required", "emergency_mode"))
                or any(getattr(state, name, None) is not None for name in (
                    "pending_move", "pending_ai_move", "pending_test_motion",
                    "visual_capture_checkpoint", "visual_pick_retry"))):
            self.cancel()
            return
        if hw.is_robot_ready:
            self.cancel()
            return
        if stop is not None and stop.blocked:
            # Wait for the in-flight stop; do not retire the automatic attempt.
            return
        if (not self.baseline_checked or hw.motion_worker.busy
                or getattr(state, "snapshot_continue_required", False)
                or getattr(state, "manual_override_active", False)
                or getattr(state, "ai_thinking", False)):
            return

        def completed(result, error):
            if error is not None or not result:
                error = error or "Controller has not confirmed enable"
                self.attempts += 1
                event("physical.auto_enable_failed", str(error), level=logging.ERROR,
                      attempt=self.attempts)
                if self.attempts >= self.MAX_ATTEMPTS:
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
        if not hw.motion_worker.start(
                lambda: hw.activate_physical_game(
                    state, commissioned=True,
                    expected_stop_generation=(stop.generation if stop is not None else 0),
                    startup_guard=self.ensure_active), completed):
            self.finished = False
