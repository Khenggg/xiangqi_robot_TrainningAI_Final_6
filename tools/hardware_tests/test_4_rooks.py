"""
TEST: Di chuyển cánh tay đến 2 vị trí Xe xa nhất (col=8).
Chắc chắn robot di chuyển: về IDLE trước, rồi mới đến đích.
In error code thực của MoveCart + sleep chờ robot.

Chạy từ thư mục VIP/:
    python tests/test_4_rooks.py
"""
import sys
import os
import time
import numpy as np
import cv2

# --- Setup path ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_VIP_DIR  = os.path.dirname(_THIS_DIR)
_PROJ_DIR = os.path.dirname(_VIP_DIR)
sys.path.insert(0, _PROJ_DIR)
sys.path.insert(0, _VIP_DIR)

import config
from src.hardware.robot_VIP import FR5Robot

# ============================================================
# 2 vị trí xa nhất (bên phải từ góc nhìn người dùng = col 8)
# ============================================================
ROOK_POSITIONS = [
    (8, 0, "Xe Den PHAI (8,0) — xa robot nhat phia den"),
    (8, 9, "Xe Do  PHAI (8,9) — xa robot nhat phia do"),
]
TEST_Z = 200.0   # mm


def build_perspective(robot_rpc):
    print("\n📡 Đọc điểm dạy R1-R4 từ robot...")
    dst_pts = np.array([[0,0],[8,0],[8,9],[0,9]], dtype=np.float32)
    pts_data = []
    for i in range(1, 5):
        err, data = robot_rpc.GetRobotTeachingPoint(f"R{i}")
        if err:
            raise Exception(f"Lỗi đọc điểm R{i}: err={err}")
        x_val, y_val = float(data[0]), float(data[1])
        pts_data.append([x_val, y_val])
        print(f"   R{i}: X={x_val:.2f}, Y={y_val:.2f}")
    M = cv2.getPerspectiveTransform(dst_pts, np.array(pts_data, dtype=np.float32))
    print("✅ Perspective matrix OK.")
    return M


def go_pose(robot_rpc, pose, label=""):
    """Gửi MoveCart, in err code, return err."""
    err = robot_rpc.MoveCart(
        desc_pos=pose, tool=0, user=1,
        vel=config.MOVE_SPEED, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
    )
    print(f"   [{label}] MoveCart err={err}  pose={[round(v,1) for v in pose]}")
    return err


def main():
    print("\n" + "="*55)
    print("  TEST XE XA NHAT — KIEM TRA CALIBRATION")
    print("="*55)

    # Kết nối
    robot = FR5Robot()
    print(f"\nKết nối {config.ROBOT_IP}...")
    robot.connect()
    if not robot.connected:
        print("❌ Không kết nối được!"); sys.exit(1)
    print("✅ Kết nối OK!")

    # Build perspective
    M = build_perspective(robot.robot)
    robot.set_perspective_matrix(M)

    # In tọa độ
    idle_pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z] + list(config.ROTATION)
    print(f"\n📋 IDLE pose: X={config.IDLE_X}, Y={config.IDLE_Y}, Z={config.IDLE_Z}")
    print(f"\n📋 Tọa độ vị trí test:")
    for col, row, label in ROOK_POSITIONS:
        pose = robot.board_to_pose(col, row, TEST_Z)
        print(f"   ({col},{row}) {label}")
        print(f"         → X={pose[0]:.1f}, Y={pose[1]:.1f}, Z={pose[2]:.1f}")

    print()
    input(">>> Nhấn ENTER để bắt đầu (robot sẽ di chuyển)...")

    for idx, (col, row, label) in enumerate(ROOK_POSITIONS):
        pose = robot.board_to_pose(col, row, TEST_Z)

        # Bước 1: Về IDLE để reset vị trí
        print(f"\n[{idx+1}/{len(ROOK_POSITIONS)}] 🏠 Về IDLE...")
        err = go_pose(robot.robot, idle_pose, "IDLE")
        print(f"   Chờ 4s để robot về IDLE...")
        time.sleep(4)

        # Bước 2: Đến vị trí test
        print(f"   🤖 Đến {label}...")
        err = go_pose(robot.robot, pose, f"({col},{row})")
        print(f"   Chờ 5s để robot đến nơi...")
        time.sleep(5)

        # Xác nhận
        print()
        print("   👁️  Kiểm tra đầu gripper có đúng vị trí quân Xe không?")
        print("   📏  Nếu lệch: ghi hướng lệch và khoảng cách (mm)")
        result = input("   Nhập kết quả → ENTER: ").strip()
        if result:
            print(f"   📝 Kết quả ({col},{row}): {result}")

    # Về IDLE lần cuối
    print(f"\n🏠 Về IDLE lần cuối...")
    go_pose(robot.robot, idle_pose, "IDLE-final")
    time.sleep(4)
    print("✅ Test xong!")


if __name__ == "__main__":
    main()
