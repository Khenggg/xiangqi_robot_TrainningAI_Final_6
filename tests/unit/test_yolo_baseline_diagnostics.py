"""An ONNX-verified board and YOLO occupancy are distinct observations."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.core import xiangqi
from src.hardware.hardware_manager import HardwareManager
from src.vision.snapshot_detector import SnapshotDetector


@pytest.mark.parametrize('duplicate', [False, True])
def test_verified_32_piece_board_can_have_31_yolo_cells_without_fen_failure(tmp_path, caplog, duplicate):
    matrix = tmp_path/'perspective.npy'
    np.save(matrix,np.eye(3))  # Fixture: one image_px unit per board_grid interval.
    detector = SnapshotDetector(matrix,{0:'piece'},foot_ratio=.5)
    board = xiangqi.get_board()
    detections = [(0,.99,(c-.2,r-.2,c+.2,r+.2)) for r in range(10) for c in range(9)
                  if board[r][c] != '.' and (r,c) != (6,4)]
    if duplicate:
        detections.append(detections[0])  # 32 boxes can still occupy only 31 cells.
    manager = SimpleNamespace(cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(
        return_value=(np.zeros((20,20,3),dtype=np.uint8),detections))),
        yolo_detector=detector,dry_run=False,verify_physical_board=Mock(return_value=True))
    with caplog.at_level('INFO',logger='xiangqi'):
        assert HardwareManager.capture_baseline_if_needed(manager,expected_board=board)
    manager.verify_physical_board.assert_called_once_with(board)
    assert sum(bool(c) for row in detector._baseline_occ for c in row) == 31
    record = next(r for r in caplog.records if getattr(r,'event',None) == 'camera.yolo_baseline')
    assert record.event_data['raw_detection_count'] == (32 if duplicate else 31)
    assert record.event_data['expected_piece_count'] == 32
    assert record.event_data['yolo_occupied_count'] == 31
    assert record.event_data['occupancy_diff_cells'] == [dict(row=6,col=4,expected_piece='r_P',yolo_occupied=False)]
    assert 'Ô e6 (hàng=6, cột=4): YOLO chưa thấy Tốt Đỏ (r_P) theo FEN dự kiến.' in record.getMessage()
    assert 'Chưa kết luận quân thật bị thiếu' in record.getMessage()
    assert not any(getattr(r,'error_code',None) == 'CAMERA_VERIFY_FAILED' for r in caplog.records)
    assert board[6][4] == 'r_P'  # Logging must not replace the game board with YOLO occupancy.


def test_mismatched_fen_still_rejects_baseline_before_yolo_capture():
    detector = SimpleNamespace(clear_baseline=Mock(),capture_baseline=Mock())
    manager = SimpleNamespace(cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock()),
        yolo_detector=detector,dry_run=False,verify_physical_board=Mock(return_value=False))
    assert not HardwareManager.capture_baseline_if_needed(manager,expected_board=xiangqi.get_board())
    detector.clear_baseline.assert_called_once()
    detector.capture_baseline.assert_not_called()
    manager.cam_monitor.get_fresh_snapshot.assert_not_called()


def test_same_count_shift_names_missing_piece_and_extra_occupied_cell(caplog):
    board = xiangqi.get_board()
    occupancy = [[piece != '.' for piece in row] for row in board]
    occupancy[6][4], occupancy[5][4] = False, True
    detector = SimpleNamespace(_baseline_occ=occupancy,capture_baseline=Mock(return_value=True))
    manager = SimpleNamespace(cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(),[]))),
        yolo_detector=detector,dry_run=False,game_state=SimpleNamespace(board=board))
    with caplog.at_level('INFO',logger='xiangqi'):
        assert HardwareManager.capture_baseline_if_needed(manager)
    record = next(r for r in caplog.records if getattr(r,'event',None) == 'camera.yolo_baseline')
    assert record.event_data['yolo_occupied_count'] == record.event_data['expected_piece_count'] == 32
    assert record.event_data['occupancy_diff_count'] == 2
    assert 'Ô e6 (hàng=6, cột=4): YOLO chưa thấy Tốt Đỏ (r_P)' in record.getMessage()
    assert 'Ô e5 (hàng=5, cột=4): YOLO báo có quân; FEN dự kiến ô trống (.).' in record.getMessage()
