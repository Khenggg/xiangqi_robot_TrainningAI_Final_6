"""Full-board identity proof for manual restoration; no arm access."""
import math
import numpy as np


def match_layout(expected_board, recognition, min_confidence=0.7):
    """Fail closed on any uncertain cell, including empty cells."""
    try:
        expected = np.asarray(expected_board)
        observed = np.asarray(recognition['board'])
        confidence = np.asarray(recognition['confidence'], dtype=float)
        if not recognition.get('success') or expected.shape != (10, 9):
            return False
        if observed.shape != (10, 9) or confidence.shape != (10, 9):
            return False
        if not np.all(np.isfinite(confidence)) or not np.all(confidence > min_confidence):
            return False
        valid = {'.'} | {side + '_' + piece for side in ('r', 'b') for piece in 'KAENCRP'}
        if any(piece not in valid for piece in expected.flat):
            return False
        return bool(np.array_equal(observed, expected))
    except (TypeError, ValueError, KeyError, IndexError):
        return False


class ManualRollbackVerifier:
    """Require consecutive new exposures over a real stable time window."""
    def __init__(self, min_samples=3, stable_seconds=1.0):
        self.min_samples = max(3, int(min_samples))
        self.stable_seconds = max(1.0, float(stable_seconds))
        self.reset()

    def reset(self):
        self._frames = []
        self._first_at = None
        self._last_at = None

    @property
    def samples(self):
        return len(self._frames)

    def observe(self, sample, now):
        frame = sample.get('frame')
        if (not sample.get('matched') or frame is None or not math.isfinite(now)
                or (self._last_at is not None and now <= self._last_at)
                or any(frame is previous for previous in self._frames)):
            self.reset()
            return False
        # Retain references to prevent recycled object ids/cached frame reuse.
        if self._first_at is None:
            self._first_at = now
        self._frames.append(frame)
        self._last_at = now
        complete = self.samples >= self.min_samples and now - self._first_at >= self.stable_seconds
        if not complete and len(self._frames) >= 64:
            self.reset()
        return complete
