# Đo riêng camera → grid và grid → robot

Chạy `MEASURE_GEOMETRY.bat` riêng; đóng `RUN.bat` để tránh tranh camera/robot.
BAT mở **client hướng dẫn bằng tiếng Việt**. Chọn phép đo, làm theo hướng dẫn
trên màn hình, đánh dấu checklist rồi bấm nút tiếp tục. Không cần nhập lệnh console.
Không có AI, FEN, best.pt hay lệnh đóng/mở gripper trong hai phép đo này.
Không thay đổi calibration, teaching points, TCP hay offset hiện tại.

## Camera → grid (chọn 1)

Giữ nguyên camera/bàn, độ phân giải và crop như lúc tạo `perspective.npy`.
Dọn quân tại 9 giao điểm cần đo. Công cụ chụp một frame cố định, hiện lưới vàng
và cửa sổ phóng to tại con trỏ. Click giao điểm IN THẬT theo thứ tự hướng dẫn:
`(0,0), (4,0), (8,0), (0,4), (4,4), (8,4), (0,9), (4,9), (8,9)`.
Không click theo lưới vàng, viền trang trí hoặc tâm quân.
Gốc `(0,0)` là P0; `(8,0)` là P1; `(8,9)` là P2; `(0,9)` là P3 trong calibration.
Di chuột để xem vùng phóng to. Nút **Bỏ điểm cuối** sửa click nhầm;
**Kết thúc và về menu** giữ cả số đo chưa đủ 9 điểm.

CSV ghi pixel, grid đo được, `delta_col/row = measured - expected`, độ lệch
theo đơn vị ô. Điểm đỏ trên ảnh là giao điểm do người đo chọn. Sai số bằng 0
ở bốn góc tự nó không chứng minh calibration đúng; xem các điểm bên trong.
Lặp lại trên nhiều frame với bàn đứng yên để đánh giá độ lặp lại.

Đo ảnh có sẵn cùng hệ camera/calibration:
`python scripts/measure_geometry.py camera --image path/to/frame.png`

## Grid → robot (chọn 2)

Công cụ đọc R1–R4 và nội suy bilinear đúng như visual pick, gồm cả offset config.
Không dùng `FR5Robot.connect()` vì hàm đó kích hoạt ngàm khi khởi động.
Mỗi điểm chỉ chạy khi bấm **Chạy arm tới điểm chuẩn ở trên cao** và xác nhận checklist;
nhập XYZ hiện tại từ pendant sau khi đã nâng
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

Mở kết nối từ màn hình chuẩn bị chỉ đọc R1–R4, chưa chạy arm.
Nút **Lưu sai số → điểm kế tiếp** ghi XYZ đã căn, sau đó yêu cầu nâng lại Z.
Nút **Dừng đo** không tự HOME hoặc dừng khẩn cấp; khi cần dừng chuyển động,
dùng nút dừng trên pendant. Client không tự xác minh số XYZ bạn nhập: phải đọc
đúng tọa độ thật, không lấy số ví dụ. Đảm bảo cả đường đi trên cao thông thoáng.

## Trình tự thao tác trên client

| Bước | Thực hiện | Client làm gì |
| --- | --- | --- |
| 1 | Đóng RUN.bat, giữ camera/bàn cố định | Hiện menu hai phép đo |
| 2 | Chọn Camera, đánh dấu checklist, bấm chụp | Giữ ảnh đứng yên, hiện điểm cần click |
| 3 | Click lần lượt 9 giao điểm in thật | Lưu từng click và chuyển sang điểm kế tiếp |
| 4 | Về menu, chọn Robot, hoàn tất checklist | Đọc R1–R4 và lưu kế hoạch, chưa chuyển động |
| 5 | Nâng Z bằng pendant, nhập XYZ hiện tại và xác nhận | Chỉ khi bấm Chạy mới đưa arm tới XY chuẩn trên cao |
| 6 | Jog/hạ/căn tâm ngàm tại Z hướng dẫn; nhập XYZ đã căn | Lưu sai số, yêu cầu nâng Z trước điểm tiếp theo |
| 7 | Lặp lại đủ 9 điểm, nâng về nơi an toàn bằng pendant | Hiện bảng kết quả; không tự HOME |
| 8 | Bấm Mở thư mục kết quả, gửi các thư mục mới tạo | Cung cấp ảnh, CSV, ma trận và metadata để phân tích |

## Console tùy chọn

Giao diện là mặc định khi chạy BAT. Các lệnh cũ vẫn dùng được:

```text
python scripts/measure_geometry.py camera
python scripts/measure_geometry.py robot
python scripts/measure_geometry.py robot --move
```

Lệnh `robot` không có `--move` chỉ lưu kế hoạch. Trong console camera dùng
`R` để bỏ điểm cuối, `Q`/ESC để kết thúc; robot chuyển động cần gõ `MOVE` cho từng điểm.

## Kết quả

Mỗi lần chạy tạo thư mục riêng `measurement_reports/<timestamp>`:
ảnh camera gốc, overlay, CSV, bản sao ma trận và metadata độ phân giải;
hoặc kế hoạch robot, CSV sai số XY, R1–R4, tool/user, góc và offset.
Đây là dữ liệu đo, chưa tự sửa lens hay áp dụng bù robot.
