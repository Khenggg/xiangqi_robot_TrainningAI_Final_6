"""
Unit test for Dual Geometry & Distance Gate filter in SnapshotDetector.
Verifies that:
1. Valid pieces on intersections are accepted.
2. Slightly off-center pieces (dist <= 0.32) are accepted.
3. Off-center circular objects in the middle of cells (dist > 0.32) are rejected.
4. Objects outside the board boundaries are rejected (NOT clamped to edge cells).
5. Objects with deformed aspect ratios (w/h < 0.55 or w/h > 1.80) are rejected.
"""

import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import cv2

# Add project root to sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.vision.snapshot_detector import SnapshotDetector


def create_test_perspective_matrix(save_path):
    # Virtual camera image: 1280x720
    # Board corners in pixels:
    # (0, 0) -> (200, 100)
    # (8, 0) -> (1000, 100)
    # (8, 9) -> (1000, 600)
    # (0, 9) -> (200, 600)
    src_px = np.array([
        [200.0, 100.0],
        [1000.0, 100.0],
        [1000.0, 600.0],
        [200.0, 600.0]
    ], dtype=np.float32)
    dst_grid = np.array([
        [0.0, 0.0],
        [8.0, 0.0],
        [8.0, 9.0],
        [0.0, 9.0]
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src_px, dst_grid)
    np.save(save_path, M)
    return M, np.linalg.inv(M)


def make_detection_at_grid(col, row, inv_M, box_w=40, box_h=40):
    """
    Creates a bounding box (x1, y1, x2, y2) such that its base contact point
    cx = (x1 + x2)/2, cy = y1 + 0.85*h projects exactly to (col, row) on the grid.
    """
    pt = np.array([[[float(col), float(row)]]], dtype=np.float32)
    px = cv2.perspectiveTransform(pt, inv_M)[0][0]
    cx, cy = float(px[0]), float(px[1])

    # cx = x1 + box_w / 2 -> x1 = cx - box_w / 2
    # cy = y1 + 0.85 * box_h -> y1 = cy - 0.85 * box_h
    x1 = int(round(cx - box_w / 2.0))
    y1 = int(round(cy - 0.85 * box_h))
    x2 = x1 + box_w
    y2 = y1 + box_h
    return (0, 0.90, (x1, y1, x2, y2))


def run_tests():
    test_npy = os.path.join(os.path.dirname(__file__), "test_perspective.npy")
    M, inv_M = create_test_perspective_matrix(test_npy)

    class_map = {0: "piece"}
    detector = SnapshotDetector(test_npy, class_map, max_dist_threshold=0.32)

    passed_count = 0
    total_tests = 5

    print("\n--- BẮT ĐẦU KIỂM THỬ BỘ LỌC HÌNH HỌC & KHOẢNG CÁCH (OPTION A) ---")

    # TEST 1: Quân cờ đặt chuẩn tại các giao điểm (4, 5) và (0, 0)
    det1 = make_detection_at_grid(4.0, 5.0, inv_M)
    det2 = make_detection_at_grid(0.0, 0.0, inv_M)
    grid1 = detector._build_occupancy([det1, det2])
    assert grid1[5][4] is True, "Lỗi Test 1: Quân tại (4, 5) không được nhận diện!"
    assert grid1[0][0] is True, "Lỗi Test 1: Quân tại (0, 0) không được nhận diện!"
    print("✅ Test 1: Quân cờ đặt chuẩn tại giao điểm -> Nhận diện chính xác.")
    passed_count += 1

    # TEST 2: Quân cờ đặt hơi lệch tay (dist <= 0.32)
    # Lệch (c = 4.15, r = 5.18), dist = sqrt(0.15^2 + 0.18^2) ≈ 0.234 <= 0.32
    det_offset = make_detection_at_grid(4.15, 5.18, inv_M)
    grid2 = detector._build_occupancy([det_offset])
    assert grid2[5][4] is True, "Lỗi Test 2: Quân hơi lệch tay bị loại nhầm!"
    print("✅ Test 2: Quân cờ hơi lệch tay (dist ≈ 0.23 <= 0.32) -> Vẫn nhận diện thành công.")
    passed_count += 1

    # TEST 3: Vật tròn nằm giữa ô cờ (c = 4.50, r = 5.50), dist ≈ 0.707 > 0.32
    det_middle = make_detection_at_grid(4.50, 5.50, inv_M)
    grid3 = detector._build_occupancy([det_middle])
    n_occupied_3 = sum(1 for r in grid3 for cell in r if cell)
    assert n_occupied_3 == 0, f"Lỗi Test 3: Vật tròn giữa ô bị nhận nhầm! (n={n_occupied_3})"
    print("✅ Test 3: Vật tròn nằm giữa ô cờ (dist = 0.71 > 0.32) -> Bị loại bỏ 100%.")
    passed_count += 1

    # TEST 4: Vật thể ngoài biên bàn cờ (c = -0.50, r = 2.00)
    # Code cũ từng clamp vào c = 0! Code mới phải loại bỏ hoàn toàn.
    det_outside = make_detection_at_grid(-0.50, 2.00, inv_M)
    grid4 = detector._build_occupancy([det_outside])
    n_occupied_4 = sum(1 for r in grid4 for cell in r if cell)
    assert n_occupied_4 == 0, f"Lỗi Test 4: Vật ngoài biên bị clamp vào bàn cờ! (n={n_occupied_4})"
    print("✅ Test 4: Vật thể ngoài biên bàn cờ (c = -0.5) -> Bị loại bỏ, không bị clamp biên.")
    passed_count += 1

    # TEST 5: Vật thể có tỷ lệ bất thường (Aspect Ratio w/h)
    # Quân cờ bình thường: w=40, h=40 (ratio 1.0)
    # Ngón tay hoặc bóng đổ kéo dài: w=15, h=50 (ratio 0.30 < 0.55)
    det_skinny = make_detection_at_grid(2.0, 3.0, inv_M, box_w=15, box_h=50)
    # Vệt dài ngang: w=70, h=20 (ratio 3.5 > 1.80)
    det_wide = make_detection_at_grid(3.0, 3.0, inv_M, box_w=70, box_h=20)
    grid5 = detector._build_occupancy([det_skinny, det_wide])
    n_occupied_5 = sum(1 for r in grid5 for cell in r if cell)
    assert n_occupied_5 == 0, f"Lỗi Test 5: Bbox tỷ lệ bất thường không bị loại! (n={n_occupied_5})"
    print("✅ Test 5: Vật thể tỷ lệ dị thường (ngón tay, vệt sáng) -> Bị loại bỏ 100%.")
    passed_count += 1

    # Clean up test .npy
    if os.path.exists(test_npy):
        try: os.remove(test_npy)
        except OSError:
            pass

    print(f"\n🎉 HOÀN THÀNH: {passed_count}/{total_tests} bài test đều ĐẠT (PASSED)!\n")


if __name__ == "__main__":
    run_tests()
