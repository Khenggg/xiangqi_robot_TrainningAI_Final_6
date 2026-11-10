"""One automatic enable attempt for a newly selected physical session."""
import logging
import time

from src.core.project_logging import event


class AutomaticPhysicalStartup:
    def __init__(self, state, hardware):
        self.state = state
        self.hardware = hardware
        self.baseline_checked = False
        self.finished = False
        self.cancelled = False
        self.retry_after = 0.0
        self.retry_interval = max(0.1, float(getattr(
            getattr(hardware, "config", None), "AUTO_ENABLE_RETRY_INTERVAL_SEC", 2.0)))

    def cancel(self):
        self.cancelled = True
        self.finished = True

    def ensure_active(self):
        if self.cancelled:
            raise RuntimeError("Automatic enable cancelled")

    def tick(self):
        if self.finished:
            return
        if time.monotonic() < self.retry_after:
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
        if (getattr(hw, "_closing", False)
                or (stop is not None and (stop.generation != 0 or stop.blocked))
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
        if (not self.baseline_checked or hw.motion_worker.busy
                or getattr(state, "snapshot_continue_required", False)
                or getattr(state, "manual_override_active", False)
                or getattr(state, "ai_thinking", False)):
            return

        def completed(result, error):
            if error is not None or not result:
                error = error or "Controller chưa xác nhận enable"
                # Robot PvP may reach this gate before camera/telemetry has
                # settled. Retry only a preflight rejection. Once the enable
                # command is dispatched, an uncertain reply must never replay.
                command_started = bool(getattr(hw, "_physical_enable_command_started", False))
                is_robot_pvp = getattr(profile, "game_mode", None) == "HUMAN_VS_HUMAN_ROBOT"
                if is_robot_pvp and not command_started and not self.cancelled:
                    self.finished = False
                    self.retry_after = time.monotonic() + self.retry_interval
                    state.set_status(
                        f"Robot đang chờ điều kiện startup: {error}. Hệ thống sẽ tự kiểm tra lại.",
                        duration=15)
                    event("physical.auto_enable_deferred", str(error), level=logging.WARNING)
                else:
                    fallback = ("Khởi động lại phiên để thử lại."
                                if is_robot_pvp else "Khắc phục rồi F9/F10 thử lại.")
                    state.set_status(f"Chưa tự bật được robot: {error}. {fallback}", duration=60)
                    event("physical.auto_enable_failed", str(error), level=logging.ERROR)
            else:
                state.set_status("Robot đã tự bật quyền chuyển động. Không chạy HOME hay chỉnh kẹp.", duration=30)
                event("physical.auto_enabled", "Đã bật quyền qua kiểm tra khởi động")

        # Never automatically replay an enable whose reply may have been lost.
        self.finished = True
        if getattr(profile, "game_mode", None) == "HUMAN_VS_HUMAN_ROBOT":
            hw._physical_enable_command_started = False
        if not hw.motion_worker.start(
                lambda: hw.activate_physical_game(
                    state, commissioned=True, expected_stop_generation=0,
                    startup_guard=self.ensure_active), completed):
            self.finished = False
