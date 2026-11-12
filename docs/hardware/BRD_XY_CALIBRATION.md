# R1–R4: hiệu chuẩn XY và chiều cao riêng

Trạng thái: đã có code mô phỏng; chưa có kiểm chứng thực thi trong đợt sửa này.

## Hợp đồng

| Điểm | Hàng | Cột | Giao điểm |
|---|---:|---:|---|
| R1 | 0 | 0 | Xe đen bên cột 0 |
| R2 | 0 | 8 | Xe đen bên cột 8 |
| R3 | 9 | 8 | Xe đỏ bên cột 8 |
| R4 | 9 | 0 | Xe đỏ bên cột 0 |

Cả bốn điểm đều bắt buộc. Đây là giao điểm ngoài cùng của lưới chơi,
không phải bốn mép tấm bàn. Thứ tự tọa độ ô trong bảng là `(row, col)`.

`src/domain/board_xy_calibration.py` khớp một phép quay/dịch SE(2) từ XY.
Chiều cao/RPY của các điểm không tham gia phép khớp. Chiều cao mặt bàn được
cung cấp riêng theo robot_base, mm. Không tự scale hoặc warp khi kích thước sai.
Kích thước lưới phải khớp hình học dùng chung trong `shared/physical_geometry.json`;
cần đo và đối chiếu kích thước ngoài đời trước nghiệm thu PHYSICAL.

BoardPlacementState dùng cùng transform cho lưới 90 ô và mesh. Khoảng cách hàng/cột
được đọc từ hình học dùng chung. Metadata `calibration_space=XY_SE2` phân biệt
đường này với API SE(3) cũ trong board_pose_provider.py.

## Giao diện mô phỏng

1. Connect live với simulator rồi lấy bốn điểm hiện tại.
2. Chuẩn bị dời bàn ở tab Service, đưa tay ảo về SERVICE_SAFE.
3. Sửa X/Y của bốn điểm; nhập chiều cao mặt bàn ở trường riêng.
4. Áp dụng với placement_version đã nạp. Phiên bản thiếu/cũ bị từ chối.
5. Runtime giữ các kiểm tra tay đang chạy, quân đang gắn/rơi, khoảng trống Service
   và va chạm đường dời bàn trước khi công bố transform mới.

Các ô Z trong bốn dòng chỉ hiển thị. Đổi chiều cao mặt bàn riêng không thay
kết quả khớp XY. Mỗi lần áp dụng thành công tăng placement_version.

Profile phiên bản 2 ghi XY_SE2, chiều cao riêng, điểm, phiên bản hiệu chuẩn,
hash scene và hash hình học. Profile SE(3) phiên bản 1 phải nhập/kiểm định lại;
không được diễn giải âm thầm thành hiệu chuẩn XY.

## Ranh giới robot thật

Lệnh gắp thật đi qua mapping của visual correction. `physical_board_provider`
đăng ký provider XY bằng bốn điểm controller; nó không sửa tool/user của lệnh.
Cấu hình mirror XY cần dữ liệu đã đo trong `config.py`:

- `BOARD_CALIBRATION_MODEL = "XY_SE2"`.
- `BOARD_CALIBRATION_GRID_DIMENSIONS_MM`: chiều rộng/dài của lưới chơi, mm.
- `BOARD_CALIBRATION_SURFACE_Z_MM`: chiều cao mặt bàn độc lập trong robot_base.
- Hoặc `BOARD_SURFACE_Z_SOURCE = "R1_R4"` + `R1_R4_TAUGHT_AT_BOARD_SURFACE = True`
  để lấy median Z của R1–R4. Chỉ dùng khi cả bốn điểm được dạy tại mặt bàn
  (không phải SAFE_Z), cùng một tool/user, và `spread` Z không vượt
  `BOARD_CALIBRATION_Z_TOLERANCE_MM` (mặc định 1.0 mm).
- `BOARD_CALIBRATION_PROVENANCE`: nguồn số đo/biên bản.
- Khi user frame khác 0: `BOARD_CALIBRATION_USER_TO_BASE_XY` là ma trận SE(2) 3×3
  đã xác minh, cùng `BOARD_CALIBRATION_FRAME_PROVENANCE`.

Thiếu dữ liệu thì mirror bàn báo chưa hiệu chuẩn; kênh đọc cánh tay và lệnh donor
giữ contract riêng. Bốn điểm phải có cùng tool/user, khớp snapshot đã nạp cho
command mapping. Không suy diễn user 0 và 1 tương đương. HOMECHESS/R_Trash cũng
phải dùng đúng frame của lệnh; cần dạy lại nếu khác frame.

API SE(3) cũ còn tồn tại. Adapter dùng nó khi chọn `SE3_LEGACY` và có offset/contact
provenance hợp lệ, với điểm robot_base; không âm thầm dùng nó thay cho XY thiếu số đo.

Nước đang chờ lưu phiên, board revision và fingerprint của mapping, Z/rotation,
gripper và camera calibration. Guard kiểm tra trước dispatch và các stage vật lý.
Virtual kiểm tra lại trong operation lock trước motion. Snapshot cũ thiếu binding
không tự dispatch; cần đối soát/giải quyết transaction trước khi tạo lệnh mới.

Chưa có metrology, fault injection hoặc chứng minh mọi entry point/version gate.

Không có kết quả test, GUI, metrology hoặc robot thật cho thay đổi này.
