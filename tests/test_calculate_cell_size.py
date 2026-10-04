# =============================================================================
# === FILE: test_calculate_cell_size.py ===
# === Tính toán CELL_SIZE tự động từ 4 teaching points R1-R4 ===
# =============================================================================
#
# Cách chạy:
#   cd D:\Project\xiangqi_robot_TrainningAI_Final_6
#   python tests/test_calculate_cell_size.py
#
# Mục đích:
#   - Đọc 4 teaching points R1-R4 từ robot
#   - Tính toán CELL_SIZE_X và CELL_SIZE_Y chính xác
#   - Cập nhật vào config.py
# =============================================================================

import sys
import os

# Add project root to path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_DIR)

import config
from src.hardware.robot_VIP import FR5Robot

def main():
    print("="*70)
    print("TÍNH TOÁN CELL_SIZE TỰ ĐỘNG TỪ 4 TEACHING POINTS")
    print("="*70)
    
    print("\n📋 Yêu cầu:")
    print("   Bạn cần dạy 4 điểm R1, R2, R3, R4 trên bộ điều khiển robot:")
    print("   - R1 = (0,0) - Xe Đen Trái (góc trái-trên)")
    print("   - R2 = (8,0) - Xe Đen Phải (góc phải-trên)")
    print("   - R3 = (8,9) - Xe Đỏ Phải (góc phải-dưới)")
    print("   - R4 = (0,9) - Xe Đỏ Trái (góc trái-dưới)")
    
    input("\n>>> Nhấn ENTER nếu đã dạy 4 điểm, hoặc Ctrl+C để hủy: ")
    
    # Khởi tạo robot
    print("\n[1] Khởi tạo và kết nối robot...")
    robot = FR5Robot()
    
    try:
        robot.connect()
        print("    ✅ Đã kết nối!")
        
        # Đọc 4 teaching points
        print("\n[2] Đọc 4 teaching points từ robot...")
        points = {}
        for i in range(1, 5):
            point_name = f"R{i}"
            err, data = robot.robot.GetRobotTeachingPoint(point_name)
            if err != 0:
                print(f"    ❌ Lỗi đọc {point_name} (err={err})")
                print(f"    Hãy dạy điểm {point_name} trên bộ điều khiển robot!")
                return
            
            x = float(data[0])
            y = float(data[1])
            z = float(data[2])
            points[point_name] = (x, y, z)
            print(f"    ✅ {point_name}: X={x:.3f}, Y={y:.3f}, Z={z:.3f}")
        
        # Tính toán CELL_SIZE
        print("\n[3] Tính toán CELL_SIZE...")
        
        # R1 (0,0) → R2 (8,0): 8 cột
        r1_x, r1_y, r1_z = points["R1"]
        r2_x, r2_y, r2_z = points["R2"]
        r3_x, r3_y, r3_z = points["R3"]
        r4_x, r4_y, r4_z = points["R4"]
        
        # Tính khoảng cách ngang (R1 → R2)
        delta_x_horizontal = abs(r2_x - r1_x)
        delta_y_horizontal = abs(r2_y - r1_y)
        distance_horizontal = (delta_x_horizontal**2 + delta_y_horizontal**2)**0.5
        
        # Tính khoảng cách dọc (R1 → R4)
        delta_x_vertical = abs(r4_x - r1_x)
        delta_y_vertical = abs(r4_y - r1_y)
        distance_vertical = (delta_x_vertical**2 + delta_y_vertical**2)**0.5
        
        # CELL_SIZE
        cell_size_horizontal = distance_horizontal / 8  # 8 khoảng cột
        cell_size_vertical = distance_vertical / 9      # 9 khoảng hàng
        
        print(f"\n    Khoảng cách R1 → R2 (8 cột): {distance_horizontal:.2f} mm")
        print(f"    Khoảng cách R1 → R4 (9 hàng): {distance_vertical:.2f} mm")
        print(f"\n    → CELL_SIZE (ngang): {cell_size_horizontal:.2f} mm")
        print(f"    → CELL_SIZE (dọc):   {cell_size_vertical:.2f} mm")
        
        # Xác định trục nào là X, trục nào là Y
        print("\n[4] Xác định mapping trục...")
        if delta_y_horizontal > delta_x_horizontal:
            # Y thay đổi nhiều hơn khi di chuyển ngang → Y là trục ngang
            print("    ✅ Trục Y đi NGANG (col → Y)")
            print("    ✅ Trục X đi DỌC (row → X)")
            cell_size_x = cell_size_vertical   # X = dọc
            cell_size_y = cell_size_horizontal # Y = ngang
        else:
            # X thay đổi nhiều hơn khi di chuyển ngang → X là trục ngang
            print("    ✅ Trục X đi NGANG (col → X)")
            print("    ✅ Trục Y đi DỌC (row → Y)")
            cell_size_x = cell_size_horizontal # X = ngang
            cell_size_y = cell_size_vertical   # Y = dọc
        
        # So sánh với giá trị hiện tại
        print("\n" + "="*70)
        print("SO SÁNH VỚI GIÁ TRỊ HIỆN TẠI")
        print("="*70)
        print(f"\n  Giá trị HIỆN TẠI trong config.py:")
        print(f"    CELL_SIZE_X = {config.CELL_SIZE_X:.2f} mm")
        print(f"    CELL_SIZE_Y = {config.CELL_SIZE_Y:.2f} mm")
        
        print(f"\n  Giá trị TÍNH TOÁN từ teaching points:")
        print(f"    CELL_SIZE_X = {cell_size_x:.2f} mm")
        print(f"    CELL_SIZE_Y = {cell_size_y:.2f} mm")
        
        diff_x = abs(cell_size_x - config.CELL_SIZE_X)
        diff_y = abs(cell_size_y - config.CELL_SIZE_Y)
        
        print(f"\n  Chênh lệch:")
        print(f"    ΔX = {diff_x:.2f} mm")
        print(f"    ΔY = {diff_y:.2f} mm")
        
        if diff_x > 1.0 or diff_y > 1.0:
            print(f"\n  ⚠️  CẢNH BÁO: Chênh lệch > 1mm!")
            print(f"  → Nên cập nhật CELL_SIZE trong config.py")
        else:
            print(f"\n  ✅ Chênh lệch nhỏ, giá trị hiện tại đã tốt!")
        
        # Đề xuất cập nhật
        print("\n" + "="*70)
        print("ĐỀ XUẤT CẬP NHẬT")
        print("="*70)
        print(f"\nMở file config.py và sửa:")
        print(f"\n  CELL_SIZE_X = {cell_size_x:.2f}  # Tính từ teaching points")
        print(f"  CELL_SIZE_Y = {cell_size_y:.2f}  # Tính từ teaching points")
        
        print("\n" + "="*70)
        print("✅ HOÀN TẤT!")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Người dùng hủy!")
        
    except Exception as e:
        print(f"\n\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
