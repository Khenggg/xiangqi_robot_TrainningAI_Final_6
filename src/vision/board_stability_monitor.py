"""Confirm a candidate physical move only after the board has settled."""
from __future__ import annotations

import time


class BoardStabilityMonitor:
    """Emit a candidate once it has repeated across a stability window."""

    def __init__(self, stability_seconds=1.2, min_samples=3):
        self.stability_seconds = float(stability_seconds)
        self.min_samples = int(min_samples)
        if not 1.0 <= self.stability_seconds <= 1.5:
            raise ValueError("stability_seconds must be between 1.0 and 1.5 seconds")
        if self.min_samples < 1:
            raise ValueError("min_samples must be at least one")
        self.reset()

    def reset(self):
        self._candidate = None
        self._started_at = None
        self._sample_count = 0
        self._emitted = False

    @property
    def candidate(self):
        return self._candidate

    @property
    def sample_count(self):
        return self._sample_count

    def elapsed_seconds(self, now=None):
        if self._started_at is None:
            return 0.0
        now = time.monotonic() if now is None else float(now)
        return max(0.0, now - self._started_at)

    def observe(self, candidate, now=None):
        """Return a stable candidate exactly once, otherwise ``None``.

        ``candidate`` must be a hashable representation of an already legal
        move. Passing ``None`` clears any in-progress candidate because the
        physical board is still changing or cannot be read reliably.
        """
        now = time.monotonic() if now is None else float(now)
        if candidate is None:
            self.reset()
            return None

        if candidate != self._candidate:
            self._candidate = candidate
            self._started_at = now
            self._sample_count = 1
            self._emitted = False
            return None

        self._sample_count += 1
        if (not self._emitted
                and self._sample_count >= self.min_samples
                and now - self._started_at >= self.stability_seconds):
            self._emitted = True
            return self._candidate
        return None
