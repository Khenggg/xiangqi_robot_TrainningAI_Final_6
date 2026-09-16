# HƯỚNG DẪN DẠY TEACHING POINTS ĐỂ TRÁNH SINGULARITY

## Vấn đề

Khi robot di chuyển đến các góc xa của bàn cờ (đặc biệt là R2 và R3), nếu chỉ dùng tính toán tự động từ R1, robot có thể rơi vào trạng thái **Singularity** - các khớp thẳng hàng làm mất khả năng điều khiển.

## Giải pháp

Hệ thống đã được cập nhật để hỗ trợ **Hybrid Mode**:
1. **Ưu tiên**: Dùng teaching points R2, R3, R4 (nếu có) với MoveJ
2. **Fallback**: Tính toán tự động từ R1 với MoveCart (nếu không có teaching points)

## Cách dạy Teaching Points

### Bước 1: Dạy điểm R1 (BẮT BUỘC)

R1 là điểm gốc, đã có hướng dẫn trong README.md chính.

**Vị trí:** Góc Đen-Trái (col=0, row=0) - Xe Đen Trái

### Bước 2: Dạy điểm R2 (KHUYẾN NGHỊ - Tránh Singularity)

**Vị trí:** Góc Đen-Phải (col=8, row=0) - Xe Đen Phải

1. Mở phần mềm điều khiển robot FR5
2. Chuyển sang chế độ Teaching (dạy tay)
3. Di chuyển robot đến:
   - Chính giữa ô góc Đen-Phải (col=8, row=0)
   - Đầu kẹp hướng xuống
   - Độ cao SAFE_Z (khoảng 270mm)
   - **QUAN TRỌNG:** Tránh tư thế Singularity (các khớp không thẳng hàng)
4. Lưu điểm này với tên: **`R2`** (chữ hoa, không dấu cách)

### Bước 3: Dạy điểm R3 (KHUYẾN NGHỊ - Tránh Singularity)

**Vị trí:** Góc Đỏ-Phải (col=8, row=9) - Xe Đỏ Phải

1. Di chuyển robot đến:
   - Chính giữa ô góc Đỏ-Phải (col=8, row=9)
   - Đầu kẹp hướng xuống
   - Độ cao SAFE_Z (khoảng 270mm)
   - **QUAN TRỌNG:** Tránh tư thế Singularity
2. Lưu điểm này với tên: **`R3`** (chữ hoa, không dấu cách)

### Bước 4: Dạy điểm R4 (TÙY CHỌN)

**Vị trí:** Góc Đỏ-Trái (col=0, row=9) - Xe Đỏ Trái

1. Di chuyển robot đến:
   - Chính giữa ô góc Đỏ-Trái (col=0, row=9)
   - Đầu kẹp hướng xuống
   - Độ cao SAFE_Z (khoảng 270mm)
2. Lưu điểm này với tên: **`R4`** (chữ hoa, không dấu cách)

## Cách hệ thống hoạt động

### Khi có Teaching Points (R2, R3):

```
Robot di chuyển đến (8, 0):
1. Hệ thống phát hiện có teaching point R2
2. Đọc joint angles từ R2: [j1, j2, j3, j4, j5, j6]
3. Dùng MoveJ với joint angles → TRÁNH SINGULARITY ✅
4. Log: "🎯 Dùng MoveJ với teaching point R2 để tránh Singularity"
```

### Khi KHÔNG có Teaching Points:

```
Robot di chuyển đến (8, 0):
1. Hệ thống không tìm thấy R2
2. Tính toán tự động: X = R1_X + (0 * CELL_SIZE_Y), Y = R1_Y + (8 * CELL_SIZE_X)
3. Dùng MoveCart với tọa độ tính toán → CÓ THỂ GẶP SINGULARITY ⚠️
4. Log: "⚠️ Không có teaching points - sẽ dùng tính toán tự động"
```

## Kiểm tra Teaching Points

Sau khi dạy xong, khởi động lại chương trình và xem log:

```
[ROBOT] ✅ Đã kết nối tới 192.168.58.2
[ROBOT] 📍 Đang load teaching points để tránh Singularity...
[ROBOT]   ✅ Loaded R2: X=526.0, Y=226.0, Z=270.0
[ROBOT]   ✅ Loaded R3: X=895.0, Y=226.0, Z=270.0
[ROBOT]   ✅ Loaded R4: X=895.0, Y=-100.0, Z=270.0
[ROBOT] ✅ Đã load 3 teaching points
```

Nếu không có teaching points:
```
[ROBOT]   ⚠️ R2 không tồn tại (err=...) - sẽ dùng tính toán tự động
[ROBOT]   ⚠️ R3 không tồn tại (err=...) - sẽ dùng tính toán tự động
[ROBOT] ⚠️ Không có teaching points - sẽ dùng tính toán tự động (có thể gặp Singularity)
```

## Lưu ý quan trọng

1. **R1 là BẮT BUỘC** - Không có R1 thì robot không hoạt động
2. **R2, R3 là KHUYẾN NGHỊ** - Giúp tránh Singularity ở 2 góc xa nhất
3. **R4 là TÙY CHỌN** - Ít gặp Singularity hơn R2, R3
4. **Độ cao Z:** Khi dạy teaching points, nên dùng độ cao SAFE_Z (270mm)
5. **Tư thế:** Tránh các tư thế có khớp thẳng hàng (elbow, wrist)

## Troubleshooting

### Vẫn gặp Singularity sau khi dạy R2, R3?

1. Kiểm tra log xem teaching points có được load không
2. Thử dạy lại R2, R3 với tư thế khác (tránh khớp thẳng hàng)
3. Tăng độ cao SAFE_Z lên 300mm khi dạy
4. Kiểm tra tên teaching point phải đúng: "R2", "R3" (chữ hoa, không dấu)

### Teaching point bị lỗi khi đọc?

```python
# Kiểm tra bằng Python console:
from src.hardware.robot_VIP import FR5Robot
robot = FR5Robot()
robot.connect()

# Kiểm tra R2
err, data = robot.robot.GetRobotTeachingPoint("R2")
print(f"R2: err={err}, data={data}")
```

Nếu `err != 0`, teaching point không tồn tại hoặc tên sai.

## Tóm tắt

- ✅ Dạy R1 (BẮT BUỘC)
- ✅ Dạy R2, R3 (KHUYẾN NGHỊ - Tránh Singularity)
- ✅ Dạy R4 (TÙY CHỌN)
- ✅ Khởi động lại và kiểm tra log
- ✅ Test di chuyển đến các góc xa

Với teaching points, robot sẽ di chuyển mượt mà và tránh được Singularity!
