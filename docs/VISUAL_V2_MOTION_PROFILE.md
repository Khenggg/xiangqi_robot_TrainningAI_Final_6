# Visual-correction-v2 motion profile adopted (2026-10-26)

## Nguồn

Các giá trị chuyển động dưới đây lấy từ:

- Nhánh: `origin/feature/visual-correction-v2`
- Commit đầu nhánh: `fb0598d` (2026-10-09)
- Commit đổi rotation: `a52c8e4` (2026-10-08)
- Commit đổi SAFE_Z: `12cd359` (2026-10-07)

Đây là **profile ứng viên**, chưa được đo trên robot hiện tại.
`MOTION_PROFILE_VERIFIED = False` và startup physical sẽ ghi cảnh báo
`motion.profile_unverified`.

## Giá trị đã lấy

```python
SAFE_Z  = 220.0
PICK_Z  = 178.0
PLACE_Z = 178.0
ROTATION = [180, 0, -73.2]
PICK_TOOL_ROTATION  = list(ROTATION)
PLACE_TOOL_ROTATION = list(ROTATION)
MOVE_SPEED = 50
```

So với profile cũ đang chạy trước đó:

| Thông số | Cũ | Visual v2 |
|---|---:|---:|
| SAFE_Z | 210 | 220 |
| ROTATION | [-179, -1.5, -11.3] | [180, 0, -73.2] |
| MOVE_SPEED | 70 | 50 |

`PICK_Z`/`PLACE_Z` giữ nguyên 178.

## Giá trị **không** lấy tự động

Các mục sau thuộc setup của donor, không phải motion profile thuần túy:

- `GRIPPER_OPEN_MAX_PULSE_SEC = 0.25` và `GRIPPER_CLOSE_PULSE_SEC = 0.20`.
  Pulse phụ thuộc cơ cấu kẹp thực tế; project đang giữ 0.30/0.80 cho đến khi đo.
- `DRY_RUN = False` cứng.
- `VIDEO_SOURCE = 0`, `VIDEO_BACKEND = any`, 640×480.
- `VISUAL_HEIGHT_PICK_ENABLED = True`.
- `VISUAL_BOARD_SYNC_REQUIRED = False`.
- `VISUAL_PICK_OUTSIDE_MARGIN_MM = 10.0`.
- `PICK_OUTWARD_COMPENSATION_*`.

Không copy các mục này nếu chưa đo/chưa xác nhận camera và cơ cấu kẹp.

## Rủi ro cần kiểm tra trước khi chạy thật

1. **SAFE_Z 220** có đủ cao so với quân và bàn hiện tại không.
2. **ROTATION [180, 0, -73.2]** có đúng hướng ngàm kẹp ngoài đời không.
   Rz lệch khoảng 62° so với profile cũ; sai hướng có thể chạm quân bên cạnh.
3. **MOVE_SPEED 50** chậm hơn 70; cần kiểm tra thời gian và độ ổn định.
4. **Pulse kẹp giữ nguyên 0.30/0.80**, không phải 0.25/0.20 của donor.

## Kiểm tra trước khi chạy

1. Đưa robot đến ô trống bằng pendant ở `SAFE_Z`.
2. Đọc `Rx, Ry, Rz` thực trên pendant.
3. So với `PICK_TOOL_ROTATION = [180, 0, -73.2]`.
4. Đo khoảng hở thấp nhất của ngàm so với mặt bàn/quân ở `SAFE_Z`.
5. Chạy `MEASURE_GEOMETRY.bat` → Grid → robot.
6. Test high-Z, nước thường, nước ăn quân.
7. Nếu đúng, đặt `MOTION_PROFILE_VERIFIED = True` và ghi provenance.

## Rollback

Nếu profile mới không khớp robot:

```python
SAFE_Z  = 210.0
ROTATION = [-179, -1.5, -11.3]
MOVE_SPEED = 70
```

Không tự đổi pulse kẹp hoặc calibration camera khi rollback.
