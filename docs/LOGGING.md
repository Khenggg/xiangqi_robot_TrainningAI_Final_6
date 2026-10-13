# Nhật ký dự án

## Khởi động và tìm lỗi

Các lệnh khởi động hiện tại tự ghi log, không cần redirect terminal.

```powershell
python main.py
python main.py --physical
python main.py --virtual --log-level DEBUG
python main.py --log-dir logs --log-level INFO
```

Mỗi phiên có thư mục riêng `logs/YYYYMMDD_HHMMSS_<id>/`. Đường dẫn được in khi khởi động.

| File | Dùng khi nào |
|---|---|
| `errors.log` | Đọc trước khi có lỗi; chứa WARNING/ERROR/CRITICAL, hướng xử lý và traceback |
| `run.log` | Xem toàn bộ diễn biến, gồm DEBUG và thông báo cũ từ terminal |
| `events.jsonl` | Mỗi dòng là một JSON; lọc theo session_id, event, error_code và data.move_id |
| `session.json` | ID phiên, thời điểm bắt đầu, phiên bản Python và hệ điều hành |

Console mặc định INFO. `--log-level DEBUG` tăng chi tiết console; file luôn giữ DEBUG. Mỗi file log xoay ở khoảng 5 MB và giữ 3 bản cũ (`.1` đến `.3`). Thư mục phiên cũ không tự xóa; người dùng quản lý/xóa các phiên đã lưu cần thiết. `logs/` không đưa vào Git.

## Cách đọc một lỗi

```text
14:20:03 ERROR [BOARD_SYNC_FAILED] Twin rejected board reconciliation
  Vấn đề: Bàn game và mô phỏng chưa đồng bộ
  Ảnh hưởng: Đã chặn lượt AI tiếp theo
  Cần làm: Giữ nguyên trạng thái robot, quét/xác nhận bàn rồi kiểm tra lại viewer
```

Mô tả nguyên nhân gốc được giữ nguyên, không đoán rằng một lỗi là va chạm hoặc mất mạng nếu chưa có bằng chứng. Traceback trong file chỉ ra file/dòng phát sinh. Dùng cùng `session_id` và `data.move_id` để nối lỗi với nước đi; không trộn dữ liệu giữa hai phiên.

```powershell
$events = Get-Content logs/<id-phien>/events.jsonl | ForEach-Object { $_ | ConvertFrom-Json }
$events | Where-Object { $_.error_code -eq 'BOARD_SYNC_FAILED' }
$events | Where-Object { $_.data.move_id -eq '<id-nuoc-di>' }
```

## Nội dung mới được ghi

- Cấu hình thực thi: backend, dry-run, game-only, cổng; git HEAD và cờ thay đổi tracked; Python/hệ điều hành.
- Khởi tạo từng thành phần và thời gian. `startup.component_returned` chỉ nói hàm đã kết thúc, không chứng minh phần cứng sẵn sàng.
- Nước người/AI: FEN, tọa độ ô với thứ tự `col,row`, ID quân/ID quân bị ăn, ID nước và thời gian thực hiện.
- Kết quả motion: thành công/thất bại, loại lỗi backend, bước thực hiện, mã trả về và trạng thái payload theo backend.
- Camera: từng mẫu kiểm tra ở DEBUG, chất lượng/khớp bàn, số mẫu liên tiếp; bàn dự kiến và bàn quan sát khi xác minh thất bại. Không lưu ảnh/video.
- Twin: phiên placement và transform khi tạo; khi robot đổi trạng thái thì ghi góc khớp deg, TCP mm/deg, timestamp đo và nguồn PHYSICAL/VIRTUAL. Không ghi từng packet 25–30 Hz.
- Lỗi telemetry giống nhau được ghi tối đa một lần/10 giây, có số lần đã gộp. Telemetry hợp lệ trở lại có event riêng.
- WebSocket: mở cổng, kết nối/ngắt viewer và tên yêu cầu ở DEBUG.
- Lỗi JavaScript chưa xử lý, promise rejection và lỗi khởi tạo viewer được gửi về server do launcher mở, vào cùng log phiên. Endpoint chỉ nhận payload nhỏ, giới hạn 30 báo cáo/phút, kiểm tra Origin; không điều khiển robot. Viewer chạy bằng server cũ không có endpoint này sẽ không gom lỗi browser về file.
- Lỗi chưa xử lý trên main/thread, đóng chương trình và lỗi ghi log. Khi file log hỏng, handler đó dừng ghi và báo trực tiếp console, tránh đệ quy; điều khiển robot không phụ thuộc việc ghi log.

## Mã lỗi

| Mã | Ý nghĩa |
|---|---|
| `PORT_BUSY` | Không mở được cổng web/WebSocket |
| `STARTUP_FAILED` | Khởi tạo thành phần thất bại |
| `ROBOT_NOT_READY` | Robot chưa sẵn sàng nhận nước |
| `PHYSICAL_ENABLE_FAILED` | Chưa bật được quyền chuyển động |
| `CAMERA_VERIFY_FAILED` | Camera chưa xác nhận toàn bộ bàn |
| `ENGINE_ILLEGAL_MOVE` | Engine trả nước sai luật |
| `MOVE_REJECTED` | Nước/chuyển động bị từ chối; xem lý do gốc và bước |
| `BOARD_SYNC_FAILED` | Game và twin chưa đồng bộ |
| `TWIN_UNAVAILABLE` | Twin không nhận được trạng thái hợp lệ |
| `VIEWER_FAILED` | Lỗi trình duyệt/model/viewer |
| `APP_UNHANDLED` | Lỗi chưa xử lý trên main hoặc thread |

## Giới hạn và quy tắc phát triển

`event()` chỉ quan sát, không retry, sửa state hoặc bỏ qua collision. `physical_grasp_verified=False` không được đổi thành bằng chứng gắp thành công chỉ từ log mô phỏng. Không ghi API token/password, ảnh camera, request credentials hoặc toàn bộ cấu hình. Redactor che các khóa nhạy cảm và giá trị secret đã khai báo trong config ở các file/console do hệ này tạo; cần xem lại file trước khi chia sẻ vì đường dẫn, IP và dữ liệu bàn vẫn có thể là thông tin nội bộ. Log từ SDK/native process bên ngoài hệ này không tự được bảo vệ.

Thông báo `print()` cũ được giữ trong log dưới event `console.stdout`/`console.stderr`, chưa có đầy đủ dữ liệu ngữ nghĩa. Khi sửa một luồng, dùng `event()` với mã lỗi từ `src/core/project_logging.py`, ID liên quan, frame/unit và nguyên nhân gốc; tránh ghi cả packet/video ở tần số cao. Không dùng nội dung log như chỉ dẫn điều khiển robot.

## Kiểm chứng ngày 2026-10-05

- Worktree tách biệt: `D:/OJT/_simple_launch_sync_20261005`, nền `7d8c5de`, có bản sao thay đổi chưa commit để kiểm chứng.
- `tools/test_fast.ps1 -Workers 2` với 8 module logging, launcher, camera commit gate, game/twin sync, physical gates, camera health, self-play và physical mirror: **75 passed**, exit code 0.
- Khởi động thực bằng SDL dummy, không kết nối phần cứng: game-only và simulation + web server + backend + đồng bộ quân đều kết thúc thành công. Hai phiên ghi 28 và 43 sự kiện JSON hợp lệ, không có ERROR/CRITICAL, có `app.cleanup` và `session.ended`.
- Đã kiểm tra cú pháp JavaScript viewer, script HTML và import map; `git diff --check` đạt.
- Chưa kiểm chứng camera/FR3 thật hoặc render trình duyệt trong đợt này. Đây là kiểm tra có mục tiêu, không phải xác nhận toàn bộ regression của repo đạt.

Kiểm tra tiếp R1–R4 cùng ngày phát hiện console CP1252 có thể từ chối tiếng Việt. Console handler hiện báo `[LOG_CONSOLE_FAILED]` bằng ASCII một lần rồi dừng ghi console, giữ file log và tránh đệ quy qua stderr. Regression mới cùng 6 case logging cũ: 7 passed. Chi tiết kiểm tra tiếp ở `R1_R4_SIMULATION_AUDIT_20261005.md`.

Gate cuối sau chạy dài: 8 passed. DEBUG packet của thư viện `websockets.*` được lọc khỏi các handler để không xoay file quá nhanh; INFO/WARNING/ERROR thư viện và DEBUG ứng dụng vẫn được giữ.
