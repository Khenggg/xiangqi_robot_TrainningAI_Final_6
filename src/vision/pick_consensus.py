"""Bounded metric consensus; never turn a missing latest observation into motion."""
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from src.vision.visual_pick_estimator import GridTarget


class FreshPickTransientError(RuntimeError):
    """A failed acquisition attempt, not evidence of an empty board cell."""


class PickTargetUnavailable(RuntimeError):
    """Only consensus/deadline exhaustion at a known pre-pick checkpoint."""

    def __init__(self, reason, stage="pre_pick"):
        super().__init__(reason)
        self.reason = str(reason)
        self.stage = stage


@dataclass(frozen=True)
class ConsensusResult:
    target: GridTarget | None
    reason: str
    support: tuple = ()
    valid_count: int = 0


def select_consensus(targets, pitch_mm=(31.25, 31.25), min_samples=2, radius_mm=3.75):
    """Unique largest strict majority within a metric median *radius*.

    None attempts stay in sequence (especially the latest) but not in the valid
    majority denominator. No single-linkage growth or confidence tie-breaking.
    At most six attempts permits exhaustive, deterministic subset inspection.
    """
    targets = list(targets)
    pitch = np.asarray(pitch_mm, dtype=float)
    if (len(targets) > 6 or pitch.shape != (2,) or not np.isfinite(pitch).all()
            or np.any(pitch <= 0) or not np.isfinite(radius_mm) or radius_mm <= 0
            or isinstance(min_samples, bool) or int(min_samples) != min_samples
            or not 2 <= min_samples <= 6):
        raise ValueError("Invalid consensus limits")
    valid = [(index, target) for index, target in enumerate(targets) if target is not None]
    if any(not np.isfinite([t.col, t.row, t.confidence, t.offset_cells]).all()
           for _, t in valid):
        raise ValueError("Nonfinite measured target")
    count = len(valid)
    if count < min_samples:
        return ConsensusResult(None, "insufficient valid top-face observations", valid_count=count)
    xy = np.array([[t.col, t.row] for _, t in valid]) * pitch
    required = max(int(min_samples), count // 2 + 1)
    for size in range(count, required - 1, -1):
        winners = []
        for indices in combinations(range(count), size):
            center = np.median(xy[list(indices)], axis=0)
            if np.all(np.linalg.norm(xy[list(indices)] - center, axis=1) <= radius_mm + 1e-9):
                winners.append((indices, center))
        if not winners:
            continue
        if len(winners) != 1:
            return ConsensusResult(None, "tied maximum-support groups", valid_count=count)
        indices, center = winners[0]
        support = tuple(valid[i][0] for i in indices)
        if not targets or targets[-1] is None or len(targets) - 1 not in support:
            return ConsensusResult(None, "latest attempt does not support winning group", support, count)
        members = [valid[i][1] for i in indices]
        col, row = center / pitch
        result = GridTarget(float(col), float(row),
                            float(np.median([t.confidence for t in members])),
                            float(np.median([t.offset_cells for t in members])))
        return ConsensusResult(result, f"consensus {size}/{count}; latest supported", support, count)
    return ConsensusResult(None, "no spatially consistent strict majority", valid_count=count)


def require_pick_target(hardware, targets, name, stage="pre_pick"):
    """Translate only a soft resolution failure into an operator Retry option."""
    target = targets.get(name)
    if target is not None:
        if not np.isfinite([target.col, target.row]).all():
            raise RuntimeError(f"Nonfinite {name} measured target")
        return target
    resolution = getattr(hardware, "last_pick_resolution", {})
    reason = resolution.get("reason") or f"Missing/nonfinite {name} measured target"
    if resolution.get("failure") in {"consensus", "deadline"}:
        raise PickTargetUnavailable(reason, stage)
    raise RuntimeError(reason)
