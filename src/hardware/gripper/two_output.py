"""
Two-Output Direct-Drive Motor Gripper Driver.

Verified hardware wiring:
- Tool DO1: Motor Open direction
- Tool DO0: Motor Close direction

Critical safety invariants:
1. DO0 and DO1 must NEVER be active simultaneously (would short or damage motor driver).
2. Motor has no limit switch: only pulsed for short duration, then both outputs returned to OFF.
3. Deadtime enforced when reversing direction.
4. Safe idle (both outputs OFF) guaranteed via try/finally blocks.
"""

from typing import Callable, Optional
import logging
import math
import threading
import time

from src.hardware.gripper.base import GripperDriver

logger = logging.getLogger(__name__)


class GripperSafetyError(RuntimeError):
    """Raised when an unsafe gripper command or state is detected."""


class TwoOutputGripperDriver(GripperDriver):
    """
    Driver for 2-output direct-drive DC motor gripper on robot tool flange.
    """

    def __init__(
        self,
        set_do_fn: Optional[Callable[[int, int], int]] = None,
        open_do_id: int = 1,
        close_do_id: int = 0,
        open_pulse_sec: float = 0.30,
        close_pulse_sec: float = 0.30,
        open_settle_sec: float = 0.25,
        close_settle_sec: float = 0.25,
        deadtime_sec: float = 0.10,
        dry_run: bool = False,
    ):
        self._set_do_fn = set_do_fn
        self.open_do_id = int(open_do_id)
        self.close_do_id = int(close_do_id)
        self.open_pulse_sec = float(open_pulse_sec)
        self.close_pulse_sec = float(close_pulse_sec)
        self.open_settle_sec = float(open_settle_sec)
        self.close_settle_sec = float(close_settle_sec)
        self.deadtime_sec = float(deadtime_sec)
        self.dry_run = bool(dry_run)

        self._lock = threading.RLock()
        self._is_closed = False
        self._active_outputs = set()

        self._validate_config()
        self._set_safe_idle()

    def _validate_config(self) -> None:
        if self.open_do_id == self.close_do_id:
            raise GripperSafetyError(
                f"open_do_id ({self.open_do_id}) and close_do_id ({self.close_do_id}) must differ"
            )
        timings = (
            self.open_pulse_sec,
            self.close_pulse_sec,
            self.open_settle_sec,
            self.close_settle_sec,
            self.deadtime_sec,
        )
        if any(not math.isfinite(t) or t < 0 for t in timings):
            raise GripperSafetyError("Gripper timing parameters must be non-negative finite numbers")

    def _set_output(self, do_id: int, status: int) -> int:
        status_int = 1 if status else 0
        if status_int == 1:
            # Enforce mutual exclusion: cannot activate if another output is active
            other_id = self.close_do_id if do_id == self.open_do_id else self.open_do_id
            if other_id in self._active_outputs:
                raise GripperSafetyError(
                    f"Refusing to activate Tool DO{do_id}: DO{other_id} is already active!"
                )
            self._active_outputs.add(do_id)
        else:
            self._active_outputs.discard(do_id)

        if self.dry_run or self._set_do_fn is None:
            logger.debug(f"[TwoOutputGripper] DRY Tool DO{do_id} -> {'ON' if status_int else 'OFF'}")
            return 0

        try:
            err = self._set_do_fn(do_id, status_int)
            if err != 0:
                raise RuntimeError(f"Tool SetDO(DO{do_id}, {status_int}) failed with code {err}")
            return err
        except Exception as exc:
            self._active_outputs.discard(do_id)
            raise GripperSafetyError(f"Failed to set Tool DO{do_id}: {exc}") from exc

    def _set_safe_idle(self) -> None:
        """Force both gripper outputs to LOW (0)."""
        errors = []
        for output_id in (self.open_do_id, self.close_do_id):
            try:
                self._set_output(output_id, 0)
            except Exception as exc:
                errors.append(exc)
        self._active_outputs.clear()
        if errors:
            raise GripperSafetyError("Could not set both gripper outputs to safe idle (LOW)") from errors[0]

    def open(self) -> bool:
        """Pulse the open motor direction, then return both outputs to safe idle."""
        self._validate_config()
        with self._lock:
            self._set_safe_idle()
            time.sleep(self.deadtime_sec)
            try:
                logger.info(f"[TwoOutputGripper] OPEN: DO{self.open_do_id} ON for {self.open_pulse_sec:.2f}s")
                self._set_output(self.open_do_id, 1)
                time.sleep(self.open_pulse_sec)
            finally:
                self._set_safe_idle()
            time.sleep(self.open_settle_sec)
            self._is_closed = False
            return True

    def close(self) -> bool:
        """Pulse the close motor direction, then return both outputs to safe idle."""
        self._validate_config()
        with self._lock:
            self._set_safe_idle()
            time.sleep(self.deadtime_sec)
            try:
                logger.info(f"[TwoOutputGripper] CLOSE: DO{self.close_do_id} ON for {self.close_pulse_sec:.2f}s")
                self._set_output(self.close_do_id, 1)
                time.sleep(self.close_pulse_sec)
            finally:
                self._set_safe_idle()
            time.sleep(self.close_settle_sec)
            self._is_closed = True
            return True

    def stop(self) -> bool:
        with self._lock:
            self._set_safe_idle()
            return True

    def is_closed(self) -> bool:
        return self._is_closed
