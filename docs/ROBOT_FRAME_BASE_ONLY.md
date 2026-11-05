# Robot frame policy — robot base (user 0)

## Nguồn tọa độ cố định cho game (2026-10-30)

Theo yêu cầu setup cố định, game hiện dùng
`calibration/physical_teaching_points_user0.json`, được chọn bởi
`PHYSICAL_TEACHING_POINTS_FILE` trong `config.py`. Bộ điểm gồm R1–R4, HOMECHESS
và R_Trash, tool 0/user 0, giữ nguyên pose/joints từ bản chụp controller ngày
2026-10-28 và chuẩn hóa metadata theo bằng chứng WObj 1 identity đã lưu.

Khởi động, về HOME, ăn quân và nguồn dữ liệu cho mirror không đọc lại teaching
points/WObj từ controller. Không cần chọn WObj 1 trên pendant để qua bước này.
Robot vẫn phải kết nối, có telemetry hợp lệ, camera xác nhận bàn và được bật
bằng F9/F10. File thiếu/sai frame/đơn vị hoặc tọa độ không hợp lệ sẽ chặn enable,
không tự quay về đọc controller. Calibration camera và cấu hình Z/tốc độ/kẹp
không đổi. Mirror vẫn cần cấu hình hình học/Z độc lập như trước.

Các mục dưới về kiểm tra WObj tại runtime áp dụng khi chủ động chọn chế độ đọc
controller (`PHYSICAL_TEACHING_POINTS_FILE = None`) để chẩn đoán. Không có thay
đổi nào được ghi lên controller bởi việc chọn nguồn tọa độ cố định.

## 1. Quy tắc hiện tại

Toàn bộ teaching point dùng cho chuyển động thật phải nằm trong **robot base (user 0)**:

- `R1`, `R2`, `R3`, `R4`
- `HOMECHESS`
- `R_Trash`

Cả sáu điểm phải dùng **cùng một tool frame**. Project không tự đổi frame và
không tự suy diễn `user 0` tương đương `user 1` trừ trường hợp đặc biệt đã kiểm
chứng: WObj hiện tại có offset **identity tuyệt đối**. Khi đó tọa độ số học của
user 1 trùng robot base; app có thể chuẩn hóa metadata thành user 0 và ghi cảnh
báo. WObj có offset khác 0 vẫn bị từ chối.

## 2. Cấu hình

Trong `config.py`:

```python
ROBOT_USER_FRAME = 0          # bắt buộc robot base
ROBOT_TOOL_FRAME = None       # None: chấp nhận tool duy nhất controller trả về
                              # hoặc đặt số cụ thể (ví dụ 0) để bắt buộc
ROBOT_FRAME_POLICY = "BASE_ONLY"
BOARD_CALIBRATION_REQUIRE_BASE_FRAME = True
```

`ROBOT_USER_FRAME` khác `0` sẽ bị từ chối ngay khi tạo `FR5Robot`.

## 3. Code kiểm tra gì

- `src/hardware/robot_VIP.py`
  - `_load_teaching_points`: R1–R4 phải cùng một cặp `(tool, user)`; user phải là 0;
    nếu `ROBOT_TOOL_FRAME` được đặt, tool phải khớp.
  - `_validated_corners`: kiểm lại frame đã cache trước mỗi lần tính pose/enable.
  - `_verify_waypoint_frame` và kiểm tra `R_Trash`: HOMECHESS/R_Trash phải cùng frame.
- `src/hardware/simulation_adapter.py`
  - `physical_board_provider`: từ chối mirror nếu R1–R4 không ở user 0
    (khi `BOARD_CALIBRATION_REQUIRE_BASE_FRAME=True`).
- `src/domain/board_pose_provider.py`
  - Calibration SE(3) chỉ chấp nhận `wobj` 0.

Khi sai frame:

- App vẫn kết nối **chỉ đọc**, vẫn xem được tay robot.
- `physical_motion_authorized = False`.
- F10 bị từ chối.
- Không có lệnh `MoveCart`, `MoveJ` hay gripper nào được gửi.

## 4. Vì sao phải dạy lại, không sửa số

Tọa độ X/Y trong teaching point chỉ có nghĩa khi biết nó được đo từ frame nào.
Nếu chỉ đổi nhãn `user 1` thành `user 0` mà giữ nguyên số:

- Cổng kiểm tra sẽ pass.
- Nhưng controller sẽ hiểu các số đó trong robot base.
- Robot đi sai vị trí, không có exception.
- Camera verify sau nước đi vẫn có thể pass vì nó chỉ so layout quân, không so XY tuyệt đối.

Vì vậy **không sửa metadata bằng tay**. Phải dạy lại, hoặc transform bằng
ma trận SE(3) đã kiểm chứng. Ngoại lệ duy nhất là WObj identity đã đọc trực tiếp
từ controller: `GetActualWObjNum()` và `GetCurWObjCoord()` phải trả offset
`[0,0,0,0,0,0]`; khi đó app chuẩn hóa R1–R4 sang user 0 và log
`robot.frame_normalized_identity_wobj`. Nếu offset khác identity, app từ chối.

## 5. Quy trình chuyển sang user 0

Chuẩn bị:

- Dừng app, kết thúc ván sạch, không còn nước/test đang chờ.
- Có người vận hành trực tiếp, nút dừng khẩn cấp hoạt động, khu vực trống.
- Ghi lại R1–R4/HOMECHESS/R_Trash hiện tại (XYZ, tool, user) để đối chiếu.

Trên pendant:

1. Chọn **tool** đang dùng (ví dụ 0) và **user 0**.
2. Dạy lại theo đúng thứ tự:
   - R1 = (row 0, col 0)
   - R2 = (row 0, col 8)
   - R3 = (row 9, col 8)
   - R4 = (row 9, col 0)
   - HOMECHESS
   - R_Trash
3. Dùng cùng một điểm tiếp xúc trên kẹp, cùng góc ngàm, cùng độ cao dạy.
4. Đọc lại sáu điểm, xác nhận:
   - bộ điều khiển trả đủ 20 trường,
   - `tool` giống nhau,
   - `user = 0`.

Kiểm tra bằng công cụ chỉ đọc:

```powershell
.\.venv312\Scripts\python.exe tools\diagnostics\read_teaching_points.py
.\.venv312\Scripts\python.exe tools\diagnostics\read_teaching_points.py --connect
```

Sau đó:

1. Chạy `MEASURE_GEOMETRY.bat` → **Grid → robot** để đo sai số.
2. Khởi động lại app.
3. F9 → F10.
4. Test theo thứ tự: di chuyển ở độ cao an toàn → một nước đi thường → một nước ăn quân.

## 6. Những gì thay đổi sau khi dạy lại

- `teaching_points_version` tăng.
- Binding/nước đang chờ cũ hết hiệu lực.
- `perspective.npy` (camera) không đổi.
- `OFFSET_X/Y`, `SAFE_Z`, `PICK_Z`, `PLACE_Z`, rotation không tự đổi; nên đo lại.
- Nếu dùng mirror bàn, cập nhật `BOARD_CALIBRATION_GRID_DIMENSIONS_MM`,
  `BOARD_CALIBRATION_SURFACE_Z_MM`, `BOARD_CALIBRATION_PROVENANCE`.

## 7. Checklist trước khi chơi thật

- [ ] R1–R4 cùng `tool`, cùng `user = 0`.
- [ ] HOMECHESS cùng `tool`, cùng `user = 0`.
- [ ] R_Trash cùng `tool`, cùng `user = 0` (nếu chơi nước ăn quân).
- [ ] `read_teaching_points.py --connect` báo `OK`.
- [ ] `MEASURE_GEOMETRY` đã chạy và sai số trong ngưỡng chấp nhận.
- [ ] Camera calibration còn đúng (bàn/camera không xê dịch).
- [ ] F9/F10 bật được.
- [ ] Test high-Z không chạm quân.
- [ ] Một nước đi thường chạy đúng.
- [ ] Một nước ăn quân chạy đúng.

Không có bước nào trong tài liệu này cho phép bỏ qua kiểm tra frame hoặc tự
động ghi đè teaching point.
