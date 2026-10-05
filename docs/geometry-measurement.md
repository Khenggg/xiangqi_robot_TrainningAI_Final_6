# Đo riêng camera → grid và grid → robot

Chạy `MEASURE_GEOMETRY.bat` riêng; đóng `RUN.bat` để tránh tranh camera/robot.
Không có AI, FEN, best.pt hay lệnh đóng/mở gripper trong hai phép đo này.
Không thay đổi calibration, teaching points, TCP hay offset hiện tại.

## Camera → grid (chọn 1)

Giữ nguyên camera/bàn, độ phân giải và crop như lúc tạo `perspective.npy`.
Dọn quân tại 9 giao điểm cần đo. Công cụ chụp một frame cố định, hiện lưới vàng
và cửa sổ phóng to tại con trỏ. Click giao điểm IN THẬT theo thứ tự hướng dẫn:
`(0,0), (4,0), (8,0), (0,4), (4,4), (8,4), (0,9), (4,9), (8,9)`.
Không click theo lưới vàng, viền trang trí hoặc tâm quân.
`R` bỏ điểm cuối; `Q`/ESC kết thúc và lưu, kể cả khi chưa đo đủ 9 điểm.

CSV ghi pixel, grid đo được, `delta_col/row = measured - expected`, độ lệch
theo đơn vị ô. Điểm đỏ trên ảnh là giao điểm do người đo chọn. Sai số bằng 0
ở bốn góc tự nó không chứng minh calibration đúng; xem các điểm bên trong.
Lặp lại trên nhiều frame với bàn đứng yên để đánh giá độ lặp lại.

Đo ảnh có sẵn cùng hệ camera/calibration:
`python scripts/measure_geometry.py camera --image path/to/frame.png`

## Grid → robot (chọn 2)

Công cụ đọc R1–R4 và nội suy bilinear đúng như visual pick, gồm cả offset config.
Không dùng `FR5Robot.connect()` vì hàm đó kích hoạt ngàm khi khởi động.
Mỗi điểm chỉ chạy khi gõ `MOVE`; nhập XYZ hiện tại từ pendant sau khi đã nâng
đến ít nhất `SAFE_Z`. Công cụ chuyển AUTO/enable, đi ở tốc độ 10 tới XY chuẩn
trên cao, sau đó về `SAFE_Z`; không tự hạ xuống `PICK_Z` và không gắp.

Dùng pendant chuyển chế độ jog, hạ chậm đến chiều cao đo (`PICK_Z` mặc định),
căn **tâm ngàm thật** vào giao điểm, rồi nhập XYZ đã căn. Phải dùng đúng
Tool=0/User=1 như lệnh robot, không trộn tọa độ base với user frame.
Trước điểm tiếp theo nâng lại bằng pendant, nhập XYZ hiện tại; không tự HOME.
CSV ghi `delta_x/y = aligned - commanded`: dấu biểu thị hướng bù cần thiết.
Số đo phải cùng chiều cao và góc ngàm; công cụ từ chối Z lệch quá 1mm.
Nếu không xác nhận được tâm ngàm từ góc nhìn hiện tại, dùng đầu chỉ thị có
vị trí đã biết so với tâm ngàm thay vì đánh giá theo ảnh camera nghiêng.

Chọn 3 chỉ đọc và lưu kế hoạch, không gửi lệnh chuyển động.

## Kết quả

Mỗi lần chạy tạo thư mục riêng `measurement_reports/<timestamp>`:
ảnh camera gốc, overlay, CSV, bản sao ma trận và metadata độ phân giải;
hoặc kế hoạch robot, CSV sai số XY, R1–R4, tool/user, góc và offset.
Đây là dữ liệu đo, chưa tự sửa lens hay áp dụng bù robot.
