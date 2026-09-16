# =============================================================================
# === FILE: test_goto_xe_den.py ===
# === Test di chuyển robot đến vị trí Xe Đen (0,0) ===
# =============================================================================
#
# Cách chạy:
#   cd D:\Project\xiangqi_robot_TrainningAI_Final_6
#   python tests/test_goto_xe_den.py
#
# Mục đích:
#   - Kiểm tra robot có đến đúng vị trí Xe Đen (0,0) không
#   - Xác minh teaching point R1 và công thức tính toán
#   - Điều chỉnh OFFSET nếu cần
# =============================================================================

import sys
import os
import time

# Add project root to path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_DIR)

import config
from src.hardware.robot_VIP import FR5Robot

def main():
    print("="*70)
    print("TEST: DI CHUYỂN ROBOT ĐẾN VỊ TRÍ XE ĐEN (0,0)")
    print("="*70)
    
    # Khởi tạo robot
    print("\n[1] Khởi tạo robot...")
    robot = FR5Robot()
    
    try:
        # Kết nối robot
        print("\n[2] Kết nối robot...")
        robot.connect()
        print("    ✅ Đã kết nối!")
        
        # Kiểm tra trạng thái robot
        print("\n[2.1] Kiểm tra trạng thái robot...")
        try:
            err, robot_state = robot.robot.GetRobotState()
            if err == 0:
                print(f"    Robot State: {robot_state}")
                if robot_state != 1:  # 1 = Running
                    print("    ⚠️  Robot không ở chế độ Running!")
                    print("    Hãy bật chế độ AUTO trên bộ điều khiển robot")
                    return
            else:
                print(f"    ⚠️  Không đọc được trạng thái robot (err={err})")
        except Exception as e:
            print(f"    ⚠️  Lỗi khi kiểm tra trạng thái: {e}")
        
        # Đọc vị trí hiện tại
        print("\n[2.2] Đọc vị trí hiện tại của robot...")
        try:
            err, current_pos = robot.robot.GetActualTCPPose(0)
            if err == 0:
                print(f"    Vị trí hiện tại:")
                print(f"      X = {current_pos[0]:.1f} mm")
                print(f"      Y = {current_pos[1]:.1f} mm")
                print(f"      Z = {current_pos[2]:.1f} mm")
            else:
                print(f"    ⚠️  Không đọc được vị trí (err={err})")
        except Exception as e:
            print(f"    ⚠️  Lỗi khi đọc vị trí: {e}")
        
        # Hiển thị thông tin
        print("\n[3] Thông tin cấu hình:")
        print(f"    BOARD_ORIGIN: X={config.BOARD_ORIGIN_X:.1f}, Y={config.BOARD_ORIGIN_Y:.1f}")
        print(f"    OFFSET:       X={config.OFFSET_X:.1f}, Y={config.OFFSET_Y:.1f}")
        print(f"    CELL_SIZE:    X={config.CELL_SIZE_X:.1f}, Y={config.CELL_SIZE_Y:.1f}")
        print(f"    ROBOT_DIR:    X={config.ROBOT_DIR_X}, Y={config.ROBOT_DIR_Y}")
        
        # Tính tọa độ Xe Đen (0,0)
        col = 0
        row = 0
        
        print(f"\n[4] Tính tọa độ Xe Đen (col={col}, row={row})...")
        pose_safe = robot.board_to_pose(col, row, config.SAFE_Z)
        pose_pick = robot.board_to_pose(col, row, config.PICK_Z)
        
        print(f"\n    Tọa độ sẽ di chuyển đến:")
        print(f"      X = {pose_safe[0]:.1f} mm")
        print(f"      Y = {pose_safe[1]:.1f} mm")
        print(f"      Z (safe) = {pose_safe[2]:.1f} mm")
        print(f"      Z (pick) = {pose_pick[2]:.1f} mm")
        
        # Xác nhận trước khi di chuyển
        print("\n" + "="*70)
        print("⚠️  CẢNH BÁO: Robot sẽ di chuyển đến vị trí Xe Đen (0,0)")
        print("="*70)
        print("\nĐảm bảo:")
        print("  1. Không có vật cản trên đường đi")
        print("  2. Bàn cờ đã được xếp đúng vị trí")
        print("  3. Xe Đen đang ở vị trí (0,0) - góc trái-trên")
        print("  4. Robot đang ở chế độ AUTO/Running")
        
        response = input("\n>>> Nhấn ENTER để tiếp tục, hoặc Ctrl+C để hủy: ")
        
        # Sử dụng hàm pick_at để di chuyển đến vị trí Xe Đen
        print("\n[5] Gọi hàm pick_at(0, 0) để di chuyển đến Xe Đen...")
        print("    (Robot sẽ: mở kẹp → đến vị trí → hạ xuống → đóng kẹp → nhấc lên)")
        
        robot.pick_at(col, row)
        
        # Kiểm tra vị trí
        print("\n" + "="*70)
        print("KIỂM TRA VỊ TRÍ")
        print("="*70)
        print("\nHãy quan sát robot:")
        print("  ✅ Nếu robot đang ở CHÍNH GIỮA quân Xe Đen:")
        print("     → Tuyệt vời! Hệ thống đã chính xác!")
        print("\n  ⚠️  Nếu robot LỆCH so với quân Xe Đen:")
        print("     → Cần điều chỉnh OFFSET trong config.py")
        print("     → Lệch lên trên: Tăng OFFSET_X")
        print("     → Lệch xuống dưới: Giảm OFFSET_X")
        print("     → Lệch sang trái: Giảm OFFSET_Y")
        print("     → Lệch sang phải: Tăng OFFSET_Y")
        
        input("\n>>> Nhấn ENTER để về HOME và kết thúc: ")
        
        # Về home
        print("\n[6] Về vị trí HOME...")
        robot.go_to_home_chess()
        print("    ✅ Đã về HOME!")
        
        print("\n" + "="*70)
        print("✅ TEST HOÀN TẤT!")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Người dùng hủy test!")
        
    except Exception as e:
        print(f"\n\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n[CLEANUP] Dọn dẹp...")
        # Robot sẽ tự động cleanup khi thoát

if __name__ == "__main__":
    main()
