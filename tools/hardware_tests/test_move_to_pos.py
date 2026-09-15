"""
TEST: Di chuyển cánh tay robot đến vị trí bàn cờ bất kỳ.
Dùng để kiểm tra calibration perspective matrix.

Chạy từ thư mục VIP/:
    python tests/test_move_to_pos.py
"""
import sys
import os
import time
import numpy as np
import cv2

# --- Setup path ---
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))   # VIP/tests/
_VIP_DIR    = os.path.dirname(_THIS_DIR)                   # VIP/
_PROJ_DIR   = os.path.dirname(_VIP_DIR)                    # project root
sys.path.insert(0, _PROJ_DIR)
sys.path.insert(0, _VIP_DIR)

import config
from src.hardware import robot_sdk_core

# ============================================================
# ⚙️  CẤU HÌNH — THAY ĐỔI TẠI ĐÂY
# ============================================================
TEST_POSITIONS = [
    # (col, row, z_mm, mô tả)
    (8, 0, 200.0, "Xe Đen góc phải (8,0)"),
    (7, 0, 200.0, "Vị trí pháo đỏ    (7,0)"),
    (0, 0, 200.0, "Xe Đen góc trái   (0,0)"),
    (4, 4, 200.0, "Trung tâm bàn cờ  (4,4)"),
]
PERSPECTIVE_PATH = os.path.join(_VIP_DIR, "perspective.npy")
# ============================================================


def load_perspective():
    if not os.path.exists(PERSPECTIVE_PATH):
        print(f"❌ Không tìm thấy perspective.npy: {PERSPECTIVE_PATH}")
        sys.exit(1)
    M = np.load(PERSPECTIVE_PATH)
    print(f"✅ Perspective matrix loaded.")
    return M


def calc_pose(col, row, z_mm, M):
    """Tính tọa độ robot từ (col, row) bàn cờ."""
    logic_pt = np.array([[[float(col), float(row)]]], dtype=np.float32)
    real_pt  = cv2.perspectiveTransform(logic_pt, M)
    x_mm = float(real_pt[0][0][0])
    y_mm = float(real_pt[0][0][1])
    return [x_mm, y_mm, z_mm] + list(config.ROTATION)


def connect_robot():
    print(f"\nĐang kết nối tới robot {config.ROBOT_IP}...")
    robot = robot_sdk_core.RPC(config.ROBOT_IP)
    time.sleep(2)
    if not robot.SDK_state:
        print("❌ Không kết nối được robot!")
        sys.exit(1)
    print("✅ Kết nối thành công!")
    robot.RobotEnable(1)
    robot.Mode(0)
    time.sleep(0.5)
    return robot


def move_to(robot, pose, label=""):
    print(f"\n🤖 Di chuyển → {label}")
    print(f"   Pose: {[round(v, 2) for v in pose]}")
    err = robot.MoveCart(
        desc_pos=pose, tool=0, user=1,
        vel=config.MOVE_SPEED,
        acc=0.0, ovl=100.0, blendT=-1.0, config=-1
    )
    if err in (0, 112):
        print(f"   ✅ Đến nơi! (err={err})")
    else:
        print(f"   ❌ Lỗi MoveCart: {err}")
    return err


def go_idle(robot):
    idle = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z] + list(config.ROTATION)
    print("\n🏠 Về IDLE...")
    robot.MoveCart(desc_pos=idle, tool=0, user=1,
                   vel=config.MOVE_SPEED, acc=0.0,
                   ovl=100.0, blendT=-1.0, config=-1)
    print("✅ Về IDLE xong.")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*55)
    print("  TEST: DI CHUYỂN CÁNH TAY ĐẾN VỊ TRÍ BÀN CỜ")
    print("="*55)

    M = load_perspective()

    # In tất cả tọa độ trước
    print("\n📋 Danh sách vị trí sẽ test:")
    for i, (col, row, z, desc) in enumerate(TEST_POSITIONS):
        pose = calc_pose(col, row, z, M)
        print(f"  [{i}] {desc}")
        print(f"       X={pose[0]:.1f}mm, Y={pose[1]:.1f}mm, Z={z:.1f}mm")

    print()
    choice = input("Nhập số vị trí muốn test (hoặc 'all' để test lần lượt): ").strip()

    robot = connect_robot()

    if choice == "all":
        selected = list(range(len(TEST_POSITIONS)))
    else:
        try:
            selected = [int(choice)]
        except ValueError:
            print("❌ Lựa chọn không hợp lệ.")
            sys.exit(1)

    for idx in selected:
        col, row, z, desc = TEST_POSITIONS[idx]
        pose = calc_pose(col, row, z, M)
        move_to(robot, pose, label=f"{desc}  → X={pose[0]:.1f}, Y={pose[1]:.1f}, Z={z}")
        input("  → Kiểm tra vị trí xong, nhấn ENTER để tiếp tục...")

    go_idle(robot)
    print("\n✅ Test hoàn tất!")
