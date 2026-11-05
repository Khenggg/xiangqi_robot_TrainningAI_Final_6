"""Diagnostic evidence must explain rejection without weakening camera gates."""
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.core import xiangqi
from src.core.project_logging import LogSession
from src.hardware.hardware_manager import HardwareManager
from src.ui.input_handler import InputHandler


def hardware(results=None, *, camera=None, **options):
    cfg = SimpleNamespace(VISUAL_PICK_SAMPLE_COUNT=2, VISUAL_PICK_MIN_STABLE_SAMPLES=2,
                          CCHESS_RECOVERY_MIN_CONFIDENCE=.5, **options)
    camera = camera or SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(), [])))
    return SimpleNamespace(config=cfg, camera_calibration_ready=True, cam_monitor=camera,
                           recognize_board_state=Mock(side_effect=results))


def result(board=None, **values):
    return dict(success=True, board=board if board is not None else xiangqi.get_board(),
                **values)


def failed_record(caplog, event="camera.verification_failed"):
    return next(r for r in caplog.records if getattr(r, "event", None) == event)


def test_same_piece_counts_mismatch_explains_each_cell_in_plain_text(caplog):
    expected = xiangqi.get_board()
    observed = [row[:] for row in expected]
    observed[6][6], observed[5][6] = ".", "r_P"
    hw = hardware([result(observed, quality_ok=True)] * 2)
    assert not HardwareManager.verify_physical_board(hw, expected)
    log = failed_record(caplog)
    assert log.event_data["reason"] == "BOARD_MISMATCH"
    assert log.event_data["board_diff_count"] == 2
    assert log.event_data["observed_red_count"] == log.event_data["observed_black_count"] == 16
    assert "hàng=6, cột=6: dự kiến Tốt Đỏ (r_P); nhận ô trống (.)" in log.message
    assert "hàng=5, cột=6: dự kiến ô trống (.); nhận Tốt Đỏ (r_P)" in log.message
    assert log.event_data["cell_index_base"] == 0
    assert log.event_data["expected_board_fen"] != log.event_data["observed_board_fen"]


def test_low_piece_confidence_logs_actual_cell_score_and_threshold(caplog):
    confidence = np.full((10, 9), .99)
    confidence[6][0] = .21
    hw = hardware([result(confidence=confidence)] * 2)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "LOW_PIECE_CONFIDENCE"
    assert log.event_data["board_matches"] and log.event_data["board_diff_count"] == 0
    assert log.event_data["low_confidence_cells"] == [dict(row=6, col=0, piece="r_P", confidence=.21)]
    assert "confidence=0.210 < 0.500" in log.message


@pytest.mark.parametrize("confidence,detail", [
    (np.ones((9, 9)), "shape"), (np.full((10, 9), np.nan), "NaN"),
    (np.full((10, 9), 1.1), "[0, 1]"), (None, "shape"),
])
def test_invalid_confidence_is_not_mislabeled_as_a_board_mismatch(caplog, confidence, detail):
    hw = hardware([result(confidence=confidence)] * 2)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "CONFIDENCE_INVALID"
    assert detail in log.event_data["confidence_error"]


@pytest.mark.parametrize("minimum", [float("nan"), float("inf"), float("-inf")])
def test_invalid_confidence_threshold_remains_rejected_and_json_safe(caplog, minimum):
    hw = hardware([result(confidence=np.full((10, 9), .99))] * 2)
    hw.config.CCHESS_RECOVERY_MIN_CONFIDENCE = minimum
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    data = failed_record(caplog).event_data
    assert data["reason"] == "CONFIDENCE_INVALID" and data["confidence_threshold"] is None
    json.dumps(data, allow_nan=False)


def test_missing_general_logs_specific_sanity_error(caplog):
    board = xiangqi.get_board()
    board[0][4] = "."
    hw = hardware([result(board, quality_ok=True)] * 2)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "BOARD_SANITY_FAILED"
    assert "Tướng Đen" in log.message


def test_explicit_quality_rejection_preserves_model_error(caplog):
    hw = hardware([result(quality_ok=False, error="layout glare")] * 2)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "QUALITY_REJECTED" and "layout glare" in log.message


@pytest.mark.parametrize("timestamp,reason", [(lambda: time.monotonic() - 10, "STALE_FRAME"),
    (lambda: time.monotonic() + 10, "FUTURE_FRAME"), (lambda: float("nan"), "INVALID_TIMESTAMP")])
def test_discarded_timestamp_has_its_own_reason(caplog, timestamp, reason):
    camera = SimpleNamespace(get_fresh_observation=lambda: (timestamp(), object(), [], result(quality_ok=True)))
    hw = hardware(camera=camera)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == reason
    assert log.event_data["observed_board"] is None and not log.event_data["board_matches"]


def test_duplicate_latest_frame_does_not_report_previous_board_verdict(caplog):
    wrong = xiangqi.get_board()
    wrong[6][0], wrong[5][0] = ".", "r_P"
    observation = (time.monotonic(), object(), [], result(wrong, quality_ok=True, observation_id=7))
    hw = hardware(camera=SimpleNamespace(get_fresh_observation=lambda: observation))
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "DUPLICATE_FRAME"
    assert log.event_data["observed_board"] is None and log.event_data["diff_cells"] == []
    assert log.event_data["failure_counts"] == {"BOARD_MISMATCH": 1, "DUPLICATE_FRAME": 1}


def test_missing_observation_is_logged_instead_of_silent_continue(caplog):
    hw = hardware(camera=SimpleNamespace(get_fresh_observation=lambda: None))
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    assert failed_record(caplog).event_data["reason"] == "NO_FRESH_OBSERVATION"


def test_exception_logs_actual_error_and_traceback(caplog):
    hw = hardware([RuntimeError("layout runtime failed")] * 2)
    with caplog.at_level(logging.DEBUG, logger="xiangqi"):
        assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "EXCEPTION" and "layout runtime failed" in log.message
    assert any(r.exc_info for r in caplog.records if getattr(r, "event", None) == "camera.verification_sample")


def test_one_good_sample_before_deadline_reports_progress(caplog):
    def delayed_frame():
        time.sleep(.03)
        return object(), []
    camera = SimpleNamespace(get_fresh_snapshot=delayed_frame)
    hw = hardware([result(quality_ok=True)], camera=camera, VERIFY_BOARD_RETRY_TIMEOUT_SEC=.01)
    assert not HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    log = failed_record(caplog)
    assert log.event_data["reason"] == "INSUFFICIENT_STABLE_SAMPLES"
    assert log.event_data["consecutive"] == 1 and "1/2" in log.message


def test_full_scan_reports_difference_between_scans_not_against_old_game(caplog):
    first = xiangqi.get_board()
    second = [row[:] for row in first]
    second[6][0], second[5][0] = ".", "r_P"
    hw = hardware([result(first, quality_ok=True), result(second, quality_ok=True)])
    handler = SimpleNamespace(hw=hw, _physical_recovery_required=lambda: False)
    assert InputHandler._fresh_confirmed_layout(handler) is None
    log = failed_record(caplog, "camera.scan_failed")
    assert log.event_data["reason"] == "LAYOUT_UNSTABLE"
    assert log.event_data["comparison"] == "FIRST_SCAN_VS_SECOND_SCAN"
    assert log.event_data["board_diff_count"] == 2 and "Tốt Đỏ" in log.message


@pytest.mark.serial
def test_human_diagnostic_is_written_to_errors_log_and_correlated_json(tmp_path):
    wrong = xiangqi.get_board()
    wrong[6][0], wrong[5][0] = ".", "r_P"
    session = LogSession(tmp_path, capture=False)
    try:
        assert not HardwareManager.verify_physical_board(hardware([result(wrong, quality_ok=True)] * 2), xiangqi.get_board())
    finally:
        session.close()
    errors = (session.path / "errors.log").read_text(encoding="utf-8")
    assert "BOARD_MISMATCH" in errors and "Tốt Đỏ (r_P)" in errors and "hàng=6, cột=0" in errors
    rows = [json.loads(line) for line in (session.path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    records = [r for r in rows if r["event"] in ("camera.verification_sample", "camera.verification_failed")]
    assert len(records) == 3
    assert len({r["data"]["verification_id"] for r in records}) == 1
    assert records[-1]["data"]["reason"] == "BOARD_MISMATCH"


@pytest.mark.serial
@pytest.mark.parametrize("field,value", [(field, value)
    for field in ("observed_at", "observation_id")
    for value in (float("nan"), float("inf"), float("-inf"))])
def test_nonfinite_rejected_evidence_produces_strict_json(tmp_path, field, value):
    timestamp = value if field == "observed_at" else time.monotonic()
    evidence = result(quality_ok=True)
    if field == "observation_id":
        evidence["observation_id"] = value
    camera = SimpleNamespace(get_fresh_observation=lambda: (timestamp, object(), [], evidence))
    session = LogSession(tmp_path, capture=False)
    try:
        assert not HardwareManager.verify_physical_board(hardware(camera=camera), xiangqi.get_board())
    finally:
        session.close()
    def reject_constant(token):
        raise ValueError(f"Non-JSON token: {token}")
    records = [json.loads(line, parse_constant=reject_constant)
               for line in (session.path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    records = [r for r in records if r["event"] in ("camera.verification_sample", "camera.verification_failed")]
    assert len(records) == 3
    assert all(r["data"][field] is None and r["data"][f"{field}_repr"] for r in records)
