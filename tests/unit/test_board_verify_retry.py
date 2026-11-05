"""Bounded retry for physical full-board verification; exact equality is kept."""
from types import SimpleNamespace
from unittest.mock import Mock

from src.core import xiangqi
from src.hardware.hardware_manager import HardwareManager


def _wrong_board(expected):
    wrong = [row[:] for row in expected]
    wrong[6][0], wrong[5][0] = ".", "r_P"
    return wrong


def _hw(config, boards):
    recognizer = Mock(side_effect=[{"success": True, "quality_ok": True, "board": board}
                                   for board in boards])
    camera = SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(), [])))
    return SimpleNamespace(config=config, camera_calibration_ready=True,
                           cam_monitor=camera, recognize_board_state=recognizer), camera, recognizer


def _events(caplog):
    return [record for record in caplog.records if getattr(record, "event", None)]


def test_verification_retries_until_two_consecutive_good_frames(caplog):
    expected = xiangqi.get_board()
    wrong = _wrong_board(expected)
    cfg = SimpleNamespace(VISUAL_PICK_SAMPLE_COUNT=2, VISUAL_PICK_MIN_STABLE_SAMPLES=2,
                          CCHESS_RECOVERY_MIN_CONFIDENCE=0.5,
                          VERIFY_BOARD_RETRY_TIMEOUT_SEC=0.5,
                          VERIFY_BOARD_RETRY_POLL_SEC=0.01)
    hw, camera, recognizer = _hw(cfg, [wrong, wrong, expected, expected])

    with caplog.at_level("DEBUG", logger="xiangqi"):
        assert HardwareManager.verify_physical_board(hw, expected) is True

    assert camera.get_fresh_snapshot.call_count == 4
    assert recognizer.call_count == 4
    assert any(record.event == "camera.verification_retry" for record in _events(caplog))
    assert any(record.event == "camera.verified" for record in _events(caplog))


def test_verification_failure_logs_differing_cells(caplog):
    expected = xiangqi.get_board()
    wrong = _wrong_board(expected)
    cfg = SimpleNamespace(VISUAL_PICK_SAMPLE_COUNT=2, VISUAL_PICK_MIN_STABLE_SAMPLES=2,
                          CCHESS_RECOVERY_MIN_CONFIDENCE=0.5,
                          VERIFY_BOARD_RETRY_TIMEOUT_SEC=0.05,
                          VERIFY_BOARD_RETRY_POLL_SEC=0.01)
    hw, camera, _ = _hw(cfg, [wrong, wrong, wrong, wrong, wrong, wrong])
    # A persistent wrong board stays available for the entire retry window;
    # exhausting a finite mock stream would instead be a recognition exception.
    hw.recognize_board_state.side_effect = None
    hw.recognize_board_state.return_value = {"success": True, "quality_ok": True, "board": wrong}

    with caplog.at_level("DEBUG", logger="xiangqi"):
        assert HardwareManager.verify_physical_board(hw, expected) is False

    failed = next(record for record in _events(caplog) if record.event == "camera.verification_failed")
    differences = failed.event_data["diff_cells"]
    assert {"row": 6, "col": 0, "expected": "r_P", "observed": "."} in differences
    assert camera.get_fresh_snapshot.call_count >= 2
    assert failed.event_data["attempts"] >= 2


def test_zero_timeout_keeps_existing_single_batch_behavior():
    expected = xiangqi.get_board()
    wrong = _wrong_board(expected)
    cfg = SimpleNamespace(VISUAL_PICK_SAMPLE_COUNT=2, VISUAL_PICK_MIN_STABLE_SAMPLES=2)
    hw, camera, _ = _hw(cfg, [wrong, wrong])

    assert HardwareManager.verify_physical_board(hw, expected) is False
    assert camera.get_fresh_snapshot.call_count == 2


def test_two_good_frames_return_without_retry(caplog):
    expected = xiangqi.get_board()
    cfg = SimpleNamespace(VISUAL_PICK_SAMPLE_COUNT=3, VISUAL_PICK_MIN_STABLE_SAMPLES=2,
                          CCHESS_RECOVERY_MIN_CONFIDENCE=0.5,
                          VERIFY_BOARD_RETRY_TIMEOUT_SEC=0.5,
                          VERIFY_BOARD_RETRY_POLL_SEC=0.01)
    hw, camera, _ = _hw(cfg, [expected, expected, expected])

    with caplog.at_level("DEBUG", logger="xiangqi"):
        assert HardwareManager.verify_physical_board(hw, expected) is True

    assert camera.get_fresh_snapshot.call_count == 2
    assert not any(record.event == "camera.verification_retry" for record in _events(caplog))
