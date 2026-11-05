"""Bounded retry for transient pick-target acquisition failures."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.visual_move_coordinator import acquire_pick_targets
from src.vision.pick_consensus import PickTargetUnavailable


def _events(caplog):
    return [record for record in caplog.records if getattr(record, "event", None)]


def test_pick_target_retry_succeeds_without_pausing(caplog):
    target = object()
    hw = SimpleNamespace(get_robot_center_pick_targets=Mock(
        side_effect=[PickTargetUnavailable("no stable", resolution={"attempts": 1}),
                     {"moving": target}]))
    cfg = SimpleNamespace(VISUAL_PICK_RETRY_ATTEMPTS=2, VISUAL_PICK_RETRY_INTERVAL_SEC=0.0)

    with caplog.at_level("INFO", logger="xiangqi"):
        result = acquire_pick_targets(hw, {"moving": (4, 5)}, "pre_pick", cfg)

    assert result["moving"] is target
    assert hw.get_robot_center_pick_targets.call_count == 2
    retry = next(record for record in _events(caplog) if record.event == "vision.pick_retry")
    assert retry.event_data["attempt"] == 1
    assert retry.event_data["attempts"] == 2
    assert retry.event_data["stage"] == "pre_pick"


def test_pick_target_retry_exhaustion_preserves_last_resolution():
    hw = SimpleNamespace(get_robot_center_pick_targets=Mock(side_effect=[
        PickTargetUnavailable("first", resolution={"attempts": 1}),
        PickTargetUnavailable("last", resolution={"attempts": 2, "reason": "no_valid_detection"}),
    ]))
    cfg = SimpleNamespace(VISUAL_PICK_RETRY_ATTEMPTS=2, VISUAL_PICK_RETRY_INTERVAL_SEC=0.0)

    with pytest.raises(PickTargetUnavailable) as error:
        acquire_pick_targets(hw, {"moving": (4, 5)}, "pre_pick", cfg)

    assert str(error.value) == "last"
    assert error.value.resolution["reason"] == "no_valid_detection"
    assert hw.get_robot_center_pick_targets.call_count == 2


def test_pick_target_retry_defaults_to_single_attempt():
    hw = SimpleNamespace(get_robot_center_pick_targets=Mock(
        side_effect=PickTargetUnavailable("only", resolution={})))
    cfg = SimpleNamespace()

    with pytest.raises(PickTargetUnavailable):
        acquire_pick_targets(hw, {"moving": (4, 5)}, "pre_pick", cfg)

    assert hw.get_robot_center_pick_targets.call_count == 1
