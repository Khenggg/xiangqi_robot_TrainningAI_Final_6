"""
File: tools/hardware_tests/test_gripper_diagnose.py
Mục đích: Chẩn đoán và kiểm tra toàn bộ các cổng I/O kích hoạt Gripper trên robot Fairino FR3:
- Tool DO0, Tool DO1 (trên đầu cánh tay - giắc M12)
- Controller DO0 -> DO7 (tủ điều khiển)
"""
import sys
import os
import time

# Thêm thư mục gốc vào path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_DIR)

import config

try:
    from src.hardware import robot_sdk_core
except ImportError:
    print("❌ ERROR: Không tìm thấy robot_sdk_core!")
    sys.exit(1)


def main():
    print("=" * 60)
    print("🛠️  CÔNG CỤ CHẨN ĐOÁN & TEST I/O GRIPPER FAIRINO FR3")
    print("=" * 60)
    print(f"📡 Đang kết nối tới Robot tại {config.ROBOT_IP}...")

    robot = robot_sdk_core.RPC(config.ROBOT_IP)
    time.sleep(1.5)

    if not robot.SDK_state:
        print("❌ Lỗi: Không thể kết nối tới Robot! Hãy kiểm tra cáp mạng và IP.")
        sys.exit(1)

    print("✅ Kết nối Robot thành công!\n")

    while True:
        print("-" * 50)
        print("Chọn chức năng kiểm tra:")
        print("1. Test Tool DO0 (Chân DO0 trên đầu cánh tay)")
        print("2. Test Tool DO1 (Chân DO1 trên đầu cánh tay)")
        print("3. Quét tự động tất cả Tool DO (0 và 1)")
        print("4. Quét tự động Controller DO (DO0 -> DO7 trong tủ điều khiển)")
        print("5. Bật/Tắt thủ công 1 cổng bất kỳ (Interactive)")
        print("0. Thoát")
        print("-" * 50)

        choice = input("Nhập lựa chọn (0-5): ").strip()

        if choice == "0":
            print("Đang reset các cổng DO về 0 an toàn...")
            robot.SetToolDO(0, 0, block=1)
            robot.SetToolDO(1, 0, block=1)
            print("Tạm biệt!")
            break

        elif choice == "1":
            test_single_tool_do(robot, do_id=0)

        elif choice == "2":
            test_single_tool_do(robot, do_id=1)

        elif choice == "3":
            print("\n🔄 Bắt đầu quét Tool DO (0 và 1)...")
            for do_id in [0, 1]:
                print(f"\n👉 Kích hoạt Tool DO{do_id}:")
                print(f"   [ON]  Tool DO{do_id} = 1 (trong 3s)")
                robot.SetToolDO(do_id, 1, block=1)
                time.sleep(3)
                print(f"   [OFF] Tool DO{do_id} = 0")
                robot.SetToolDO(do_id, 0, block=1)
                time.sleep(1)
            print("\n✅ Hoàn tất quét Tool DO!")

        elif choice == "4":
            print("\n🔄 Bắt đầu quét Controller DO (0 -> 7)...")
            for do_id in range(8):
                print(f"👉 Kích hoạt Controller DO{do_id} = 1 trong 1.5s...")
                robot.SetDO(do_id, 1, block=1)
                time.sleep(1.5)
                robot.SetDO(do_id, 0, block=1)
                time.sleep(0.5)
            print("\n✅ Hoàn tất quét Controller DO!")

        elif choice == "5":
            interactive_toggle(robot)


def test_single_tool_do(robot, do_id):
    print(f"\n--- Test Tool DO{do_id} ---")
    for cycle in range(1, 4):
        print(f"  Chu kỳ {cycle}/3:")
        print(f"    🔴 Tool DO{do_id} = ON (1)")
        err = robot.SetToolDO(do_id, 1, block=1)
        if err != 0:
            print(f"    ❌ Lỗi SetToolDO code {err}")
        time.sleep(2.5)

        print(f"    🟢 Tool DO{do_id} = OFF (0)")
        err = robot.SetToolDO(do_id, 0, block=1)
        if err != 0:
            print(f"    ❌ Lỗi SetToolDO code {err}")
        time.sleep(1.5)
    print(f"✅ Hoàn tất test Tool DO{do_id}.\n")


def interactive_toggle(robot):
    print("\n--- BẬT/TẮT THỦ CÔNG ---")
    io_type = input("Loại IO (1: Tool DO trên cánh tay, 2: Controller DO trong tủ): ").strip()
    do_id = int(input("Nhập ID cổng (ví dụ 0, 1, 2...): ").strip())
    state = int(input("Nhập trạng thái (1: BẬT, 0: TẮT): ").strip())

    if io_type == "1":
        err = robot.SetToolDO(do_id, state, block=1)
        print(f"Set Tool DO{do_id} = {state} (kết quả err={err})")
    else:
        err = robot.SetDO(do_id, state, block=1)
        print(f"Set Controller DO{do_id} = {state} (kết quả err={err})")


if __name__ == "__main__":
    main()
