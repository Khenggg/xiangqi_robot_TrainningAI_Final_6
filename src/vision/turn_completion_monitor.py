"""Hand-aware gate for safely auto-confirming a human Xiangqi move."""
from __future__ import annotations

import time


class TurnCompletionMonitor:
    """Emit one confirmation request after a hand enters then leaves the board.

    This class deliberately does not decide the move.  It only establishes that
    the player has finished interacting with the physical board; the existing
    snapshot detector and Xiangqi rule validation remain authoritative.
    """

    def __init__(self, absence_seconds=0.8, min_hand_seconds=0.25):
        self.absence_seconds = float(absence_seconds)
        self.min_hand_seconds = float(min_hand_seconds)
        self.reset()

    def reset(self):
        self._entered_at = None
        self._left_at = None
        self._emitted = False

    def observe(self, hand_on_board, now=None):
        """Return True once when a qualifying hand interaction has ended."""
        now = time.monotonic() if now is None else float(now)
        if hand_on_board:
            if self._entered_at is None:
                self._entered_at = now
            self._left_at = None
            return False

        if self._entered_at is None or self._emitted:
            return False
        if self._left_at is None:
            if now - self._entered_at < self.min_hand_seconds:
                # A one-frame false positive must not arm auto-confirmation.
                self.reset()
                return False
            self._left_at = now
            return False
        if (now - self._entered_at >= self.min_hand_seconds
                and now - self._left_at >= self.absence_seconds):
            self._emitted = True
            return True
        return False
