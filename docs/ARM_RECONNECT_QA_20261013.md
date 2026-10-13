# Đồng bộ cánh tay độc lập với calibration bàn — 2026-10-13

## Lỗi đã xác minh

Phiên `20261013_123719_185b4c4f` khởi động với `Robot SDK not connected`.
`HardwareManager._init_robot` không tạo backend khi SDK thất bại; `build_session`
chỉ mở WebSocket khi có bridge. Vì vậy cổng8765 không tồn tại dù SDK có receiver
tự reconnect về sau. Khi kiểm tra, ping2/2 và GetControllerIP đều thành công;
web8088 còn hoạt động nhưng không có8765.

## Sửa đổi

- Giữ `BorrowedPhysicalStateSource` nếu startup để lại SDK handle đang reconnect.
  Không tạo SDK thứ hai, không gọi connect lại, enable, home hay IO từ viewer.
- Raw reader theo trạng thái SDK hiện tại; dữ liệu cần packet thực, mới và hợp lệ.
  Socket connected đơn thuần, packet thiếu hoặc lặp quá lâu không thành LIVE.
- WebSocket được mở để nhận lại dữ liệu khi receiver phục hồi.
- Viewer tự kết nối khi nguồn telemetry tồn tại, dù board provider thiếu.
- Cảnh báo phân biệt cánh tay LIVE và vị trí bàn/quân chưa hiệu chuẩn.
- Startup thất bại không tự phục hồi quyền game/actuation hay teaching points.
  `robot.connected`/quyền motion vẫn giữ chặn; scope này chỉ phục hồi quan sát.

## Kiểm chứng

Trong worktree `D:/OJT/_reliability_fix_20261012`:

1. Trước sửa:5 test song song thất bại; nhánh serial chưa chạy vì runner dừng.
2. Sau sửa:98 passes (96 parallel+2 serial), exit0, qua `tools/test_fast.ps1`.
   Bao gồm WebSocket thực tại localhost, mock SDK startup thất bại rồi hồi phục;
   kiểm tra packet thiếu/stale/disconnected và không cấp quyền chuyển động.
3. Node: freshness, coordinate contract, single motion authority; syntax main.mjs,
   tất cả exit0.
4. FR3 thật192.168.58.2, game đã được người dùng đóng: observer dùng manager thật,
   SDK thật, raw relay, publisher và ViewerServer; chưa khởi tạo camera/AI/game.
   Các phương thức actuation của SDK bị chặn tại observer trước khi kết nối.
   Browser tự kết nối, nhận PHYSICAL/joints_valid=true và hiện LIVE THẬT.
   Góc tại một sample:
   `[-89.46548,-128.62292,106.87717,-68.51096,-89.49550,42.53711] deg`.
   Mảng viewer bằng nguyên mảng góc của packet WebSocket nhận cùng thời điểm.
   Bàn chưa calibrated, motion_authorized=false trong evidence.

Evidence: `reports/arm-reconnect-20261013/` gồm baseline-hashes.json,
source-delta.patch, red.log, regression.log, physical.json, browser.json,
observer-closed.json và delivery-manifest.json.

## Giới hạn

Không thử rút Ethernet thật: hồi phục mất mạng được kiểm chứng bằng mock SDK
qua WebSocket thực. Hardware stream/browser đã kiểm chứng tại kết nối có thật.
Không thử chuyển động, gắp, camera/game/capture trong đợt này. Đây là đồng bộ
góc khớp, không xác nhận vị trí bàn, TCP/gripper hay toàn bộ parity hình học.
Graph impact hiện chưa đủ mới: detect_changes401 inherited paths/0symbols
không phải bằng chứng không có ảnh hưởng; scope dựa vào diff chính xác và gates.
