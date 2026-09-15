# =============================================================================
# === FILE: VIP/test_corners.py ===
# === Test di chuyển cánh tay Robot đến 4 góc của bàn cờ ===
# =============================================================================
#
# Cách chạy:
#   cd d:\Project\xiangqi_robot_TrainningAI_Final_6\VIP
#   python test_corners.py           → Di chuyển robot THẬT đến 4 góc
#   python test_corners.py --dry     → Chạy thử (không kết nối robot)
#   python test_corners.py --print   → Chỉ in tọa độ 4 góc (không di chuyển)
#   python test_corners.py --speed 20 --z 220
#
# ⚠️ QUAN TRỌNG: Robot dùng teaching points R1-R4 trên controller
#    (KHÔNG phải perspective.npy — cái đó chỉ cho camera detection)
#    Thứ tự dạy điểm:
#       R1 = (col=0, row=0) — Xe Đen Trái  (góc trái-trên)
#       R2 = (col=8, row=0) — Xe Đen Phải  (góc phải-trên)
#       R3 = (col=8, row=9) — Xe Đỏ Phải   (góc phải-dưới)
#       R4 = (col=0, row=9) — Xe Đỏ Trái   (góc trái-dưới)
# =============================================================================

import sys
import os
import time
import argparse
import numpy as np
import cv2

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_DIR)

import config

# =============================================================================
# 4 GÓC BÀN CỜ (theo tọa độ lưới logic)
# =============================================================================
CORNERS = [
    (0, 0, "R1 — Xe Đen Trái  (góc trái-trên)"),
    (8, 0, "R2 — Xe Đen Phải  (góc phải-trên)"),
    (8, 9, "R3 — Xe Đỏ Phải   (góc phải-dưới)"),
    (0, 9, "R4 — Xe Đỏ Trái   (góc trái-dưới)"),
]


def build_robot_matrix(robot_obj):
    """
    Đọc 4 teaching points R1-R4 từ robot controller và tạo perspective matrix
    (đúng theo cách main_VIP.py làm).

    Returns:
        M (3x3 numpy array) hoặc None nếu lỗi
    """
    dst_pts_logic = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
    pts_data = []
    for i in range(1, 5):
        err, data = robot_obj.robot.GetRobotTeachingPoint(f"R{i}")
        if err != 0:
            print(f"  ❌ Lỗi đọc teaching point R{i}: err={err}")
            return None
        x, y = float(data[0]), float(data[1])
        print(f"  📌 R{i}: X={x:.3f}, Y={y:.3f},  Z={float(data[2]):.3f}")
        pts_data.append([x, y])
    src_pts = np.array(pts_data, dtype=np.float32)
    M = cv2.getPerspectiveTransform(dst_pts_logic, src_pts)
    return M


def print_corner_coords(M):
    """In tọa độ robot (X, Y) tính toán được cho 4 góc bàn cờ."""
    print("\n  ┌─────────────────────────────────────────────────────┐")
    print("  │         TỌA ĐỘ ROBOT 4 GÓC BÀN CỜ (mm)            │")
    print("  ├────────────────┬───────┬───────────┬───────────────┤")
    print("  │ Góc            │ Grid  │   X (mm)  │   Y (mm)      │")
    print("  ├────────────────┼───────┼───────────┼───────────────┤")
    for col, row, label in CORNERS:
        pt = cv2.perspectiveTransform(
            np.array([[[float(col), float(row)]]], dtype=np.float32), M
        )[0][0]
        name = label.split("—")[1].strip()
        print(f"  │ {name:<14s} │ ({col},{row}) │ {pt[0]:>9.3f} │ {pt[1]:>13.3f} │")
    print("  └────────────────┴───────┴───────────┴───────────────┘")


def main():
    parser = argparse.ArgumentParser(description="Test di chuyển robot đến 4 góc bàn cờ")
    parser.add_argument("--dry",   action="store_true", help="Chạy thử không kết nối robot")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="Chỉ in tọa độ 4 góc, không di chuyển")
    parser.add_argument("--speed", type=int, default=25,
                        help="Tốc độ di chuyển 1–100 (mặc định: 25)")
    parser.add_argument("--z", type=float, default=None,
                        help=f"Chiều cao bay khi đến góc (mm). Mặc định: SAFE_Z={config.SAFE_Z}")
    args = parser.parse_args()

    if args.dry:
        config.DRY_RUN = True

    fly_z = args.z if args.z is not None else config.SAFE_Z

    print("=" * 60)
    print("  TEST DI CHUYỂN ĐẾN 4 GÓC BÀN CỜ")
    print("=" * 60)
    print(f"  DRY_RUN : {config.DRY_RUN}")
    print(f"  Speed   : {args.speed}")
    print(f"  Fly Z   : {fly_z:.3f} mm")
    print(f"  Rotation: {config.ROTATION}")
    print("=" * 60)

    # --- Import robot ---
    from src.hardware.robot_VIP import FR5Robot
    robot = FR5Robot()

    # ==========================================================================
    # MODE DRY: Dùng fake matrix (giống main_VIP.py DRY fallback)
    # ==========================================================================
    if config.DRY_RUN:
        print("\n[DRY] Dùng fake perspective matrix...")
        dst_pts_logic = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
        src_pts_fake  = np.array([[200, -100], [520, -100], [520, 260], [200, 260]], dtype=np.float32)
        M_fake = cv2.getPerspectiveTransform(dst_pts_logic, src_pts_fake)
        robot.set_perspective_matrix(M_fake)
        robot.connected = True  # Simulate connected

        print_corner_coords(robot.perspective_matrix)

        if args.print_only:
            print("\n[--print] Chỉ in tọa độ, không di chuyển (DRY).")
            return

        print("\n[DRY] Mô phỏng di chuyển đến 4 góc...")
        for idx, (col, row, label) in enumerate(CORNERS, start=1):
            pose = robot.board_to_pose(col, row, fly_z)
            print(f"\n  [{idx}/4] {label}")
            print(f"       → X={pose[0]:.2f}, Y={pose[1]:.2f}, Z={pose[2]:.2f}")
            robot.movej_pose(pose, speed=args.speed)
            time.sleep(0.3)
        robot.go_to_idle_home()
        print("\n✅ [DRY] Xong!")
        return

    # ==========================================================================
    # MODE REAL: Kết nối robot thật + đọc teaching points R1-R4
    # ==========================================================================
    print("\n[ROBOT] Đang kết nối...")
    try:
        robot.connect()
    except Exception as e:
        print(f"❌ Kết nối thất bại: {e}")
        sys.exit(1)

    print("\n[ROBOT] Đọc teaching points R1-R4 từ controller...")
    M_robot = build_robot_matrix(robot)
    if M_robot is None:
        print("\n❌ Không đọc được teaching points R1-R4!")
        print("   → Hãy dạy 4 điểm R1-R4 trên bộ điều khiển robot trước.")
        print("   Thứ tự dạy:")
        for col, row, label in CORNERS:
            print(f"   {label} → grid ({col},{row})")
        sys.exit(1)

    robot.set_perspective_matrix(M_robot)

    # In tọa độ tính toán được
    print_corner_coords(robot.perspective_matrix)

    if args.print_only:
        print("\n[--print] Chỉ in tọa độ, không di chuyển.")
        return

    # Xác nhận trước khi di chuyển
    print("\n⚠️  Robot sẽ di chuyển đến 4 góc bàn cờ.")
    print("   Đảm bảo bàn cờ và vùng xung quanh KHÔNG CÓ VẬT CẢN!")
    print("   Bấm Enter để tiếp tục, hoặc Ctrl+C để hủy...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nĐã hủy.")
        return

    # Về Home trước khi bắt đầu
    print("\n[BƯỚC 0] Về vị trí HOME an toàn...")
    robot.go_to_idle_home()
    time.sleep(1.5)

    # Lặp qua 4 góc
    for idx, (col, row, label) in enumerate(CORNERS, start=1):
        pose = robot.board_to_pose(col, row, fly_z)
        print(f"\n{'─'*55}")
        print(f"[BƯỚC {idx}/4] {label}")
        print(f"  Grid  : (col={col}, row={row})")
        print(f"  Robot : X={pose[0]:.3f}, Y={pose[1]:.3f}, Z={pose[2]:.3f}")
        print(f"  Rot   : Rx={pose[3]:.3f}, Ry={pose[4]:.3f}, Rz={pose[5]:.3f}")

        robot.movej_pose(pose, speed=args.speed)
        print(f"  ✅ Đã đến góc {idx}. Đợi 2 giây...")
        time.sleep(2.0)

    # Về Home sau khi xong
    print(f"\n{'─'*55}")
    print("[BƯỚC CUỐI] Về vị trí HOME...")
    robot.go_to_idle_home()

    print("\n" + "=" * 60)
    print("  ✅ HOÀN TẤT — Đã di chuyển xong 4 góc bàn cờ!")
    print("=" * 60)


if __name__ == "__main__":
    main()
