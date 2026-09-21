import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from pathlib import Path
import numpy as np
import cv2

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from src.vision.cchess_recognizer import (
    CChessRecognizer,
    BONE_NAMES,
    CLASS_NAMES,
    SHORT_TO_PROJECT,
    PROJECT_TO_SHORT
)
from src.vision.snapshot_detector import SnapshotDetector
from src.core import xiangqi

def test_constants_and_mappings():
    print("[TEST] 1. Checking constants and mappings...")
    assert len(BONE_NAMES) == 4
    assert len(CLASS_NAMES) == 16
    assert SHORT_TO_PROJECT["K"] == "r_K"
    assert SHORT_TO_PROJECT["k"] == "b_K"
    assert SHORT_TO_PROJECT["B"] == "r_E"
    assert SHORT_TO_PROJECT["b"] == "b_E"
    assert SHORT_TO_PROJECT["."] == "."
    print("  --> Mapping verified successfully!")

def test_model_loading_and_inference():
    print("[TEST] 2. Checking ONNX model loading and inference...")
    pose_path = PROJECT_ROOT / "models" / "cchess" / "pose_4_v6.onnx"
    layout_path = PROJECT_ROOT / "models" / "cchess" / "layout_nano_v3.onnx"

    assert pose_path.exists(), f"Missing {pose_path}"
    assert layout_path.exists(), f"Missing {layout_path}"

    recognizer = CChessRecognizer(pose_path, layout_path)
    assert recognizer.pose_session is not None
    assert recognizer.layout_session is not None

    # Test full pipeline with a mock image
    mock_frame = np.full((720, 1280, 3), 128, dtype=np.uint8)
    res = recognizer.full_recognize(mock_frame)
    assert res["success"] is True
    assert res["keypoints"].shape == (4, 2)
    assert len(res["board"]) == 10
    assert len(res["board"][0]) == 9
    assert len(res["confidence"]) == 10
    assert len(res["confidence"][0]) == 9

    # Test visualization
    vis = recognizer.draw_visualization(mock_frame, res)
    assert vis.shape == mock_frame.shape
    print("  --> Model loading and pipeline inference verified!")

def test_snapshot_detector_tiebreaker():
    print("[TEST] 3. Checking SnapshotDetector with CChess tiebreaker...")
    perspective_path = PROJECT_ROOT / "perspective.npy"
    detector = SnapshotDetector(perspective_path, {})

    # Mock board: Pháo đỏ ở (1, 7)
    board = [["." for _ in range(9)] for _ in range(10)]
    board[7][1] = "r_C"
    # Giả sử quân đen ở (1, 2) và (1, 0)
    board[2][1] = "b_P"
    board[0][1] = "b_N"

    # Mock CChess result pointing to (1, 2)
    cchess_board = [["." for _ in range(9)] for _ in range(10)]
    cchess_board[2][1] = "r_C"

    cchess_result = {
        "success": True,
        "board": cchess_board
    }

    # Hai valid moves: (1, 7) -> (1, 2) [ăn tốt] và (1, 7) -> (1, 0) [ăn mã]
    valid_moves = [
        ((1, 7), (1, 2), "r_C", "ăn quân"),
        ((1, 7), (1, 0), "r_C", "ăn quân")
    ]

    # Test tiebreaker logic
    rec_board = cchess_result["board"]
    matched = [m for m in valid_moves if rec_board[m[1][1]][m[1][0]] == m[2]]
    assert len(matched) == 1
    assert matched[0][1] == (1, 2)
    print("  --> SnapshotDetector CChess tiebreaker verified!")

def test_snapshot_detector_recovery():
    print("[TEST] 4. Checking SnapshotDetector CChess recovery fallback...")
    # Initial board: Tướng 2 bên và Tốt đỏ ở (4, 6)
    board = [["." for _ in range(9)] for _ in range(10)]
    board[9][4] = "r_K"
    board[0][4] = "b_K"
    board[6][4] = "r_P"

    # CChess result detects Tốt đỏ moved to (4, 5)
    rec_board = [["." for _ in range(9)] for _ in range(10)]
    rec_board[9][4] = "r_K"
    rec_board[0][4] = "b_K"
    rec_board[5][4] = "r_P"

    cchess_result = {
        "success": True,
        "board": rec_board
    }

    candidates_src = []
    candidates_dst = []
    for r in range(10):
        for c in range(9):
            orig_p = board[r][c]
            rec_p = rec_board[r][c]
            if orig_p.startswith("r") and rec_p != orig_p:
                candidates_src.append(((c, r), orig_p))
            elif rec_p.startswith("r") and orig_p != rec_p:
                candidates_dst.append(((c, r), rec_p))

    recovered_moves = []
    for (s_c, s_r), p_src in candidates_src:
        for (d_c, d_r), p_dst in candidates_dst:
            if p_src == p_dst and xiangqi.is_valid_move((s_c, s_r), (d_c, d_r), board, "r"):
                recovered_moves.append(((s_c, s_r), (d_c, d_r), p_src))

    assert len(recovered_moves) == 1
    assert recovered_moves[0] == ((4, 6), (4, 5), "r_P")
    print("  --> SnapshotDetector CChess recovery fallback verified!")

def test_snapshot_detector_direct_cchess_move():
    print("[TEST] 5. Checking direct CChess move detection via detect_move()...")
    perspective_path = PROJECT_ROOT / "perspective.npy"
    detector = SnapshotDetector(perspective_path, {})

    board = xiangqi.get_board()
    # Move: Red cannon at (1, 7) moves to (4, 7)
    rec_board = [row[:] for row in board]
    rec_board[7][1] = "."
    rec_board[7][4] = "r_C"

    cchess_result = {
        "success": True,
        "board": rec_board
    }

    # Calling detect_move directly with cchess_result (even without T1 baseline!)
    src, dst, piece = detector.detect_move(None, [], board, cchess_result=cchess_result)
    assert src == (1, 7), f"Expected src (1, 7), got {src}"
    assert dst == (4, 7), f"Expected dst (4, 7), got {dst}"
    assert piece == "r_C", f"Expected piece r_C, got {piece}"
    print("  --> Direct CChess move detection verified successfully!")

def main():
    print("=" * 60)
    print("[TEST] RUNNING CCHESS RECOGNITION INTEGRATION TESTS")
    print("=" * 60)
    test_constants_and_mappings()
    test_model_loading_and_inference()
    test_snapshot_detector_tiebreaker()
    test_snapshot_detector_recovery()
    print("\n[SUCCESS] ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
