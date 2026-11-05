"""Read-only measured arm telemetry without a physics/world dependency."""
import threading
from src.core.project_logging import event
import logging


class RawArmRelay:
    board_sync_available = False
    uncalibrated_board = True

    def __init__(self, backend, telemetry, reason, poll_hz=25.0):
        self.backend, self.telemetry = backend, telemetry
        self.last_error = str(reason)
        self.period_s = 1.0 / max(1.0, float(poll_hz))
        self._stop = threading.Event()
        self._thread = None
        self.latest_snapshot = None
        if telemetry is not None:
            telemetry.source = "PHYSICAL"
            telemetry.controller_ip = getattr(backend, "ip", None)
            telemetry.register_command_handler(self._reject_command)

    def _reject_command(self, _):
        if self.telemetry is not None:
            self.telemetry.broadcast_custom(dict(type="trajectory_result", success=False,
                error="Arm telemetry is read-only; physics/board mirror is unavailable."))

    def poll_once(self):
        snapshot = self.backend.get_state_snapshot()
        self.latest_snapshot = snapshot
        if self.telemetry is not None:
            self.telemetry.update_from_snapshot(snapshot)
        return snapshot

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        def run():
            last_error = None
            while not self._stop.is_set():
                try:
                    self.poll_once()
                    last_error = None
                except Exception as exc:
                    if str(exc) != last_error:
                        last_error = str(exc)
                        event("telemetry.raw_read_failed", last_error, level=logging.WARNING)
                self._stop.wait(self.period_s)
        self._thread = threading.Thread(target=run, name="raw-arm-relay", daemon=False)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
            if self._thread.is_alive():
                raise RuntimeError("Raw telemetry reader still running; retain SDK connection")
