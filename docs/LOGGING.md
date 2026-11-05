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

## Debug quét FEN (2026-10-30)

Sau khi khởi động lại app, lỗi xác thực có mã nguyên nhân ngay trong thông báo
ở console và `errors.log`; không chỉ ghi chung chung là thiếu mẫu. Ví dụ:

```text
WARNING [CAMERA_VERIFY_FAILED] FEN [BOARD_MISMATCH]: Bàn không khớp FEN dự kiến. 2 ô lệch; hàng/cột tính từ 0.
  hàng=5, cột=6: dự kiến Tốt Đỏ (r_P); nhận ô trống (.).
  hàng=6, cột=6: dự kiến ô trống (.); nhận Tốt Đỏ (r_P).
  Mẫu liên tiếp=0/2.
```

Ví dụ này vẫn có thể đủ 16 Đỏ + 16 Đen. `row`/`col` và hàng/cột trong thông báo
đều **tính từ 0**, thứ tự `row,col`; hàng 0 là phía Đen, hàng 9 phía Đỏ theo bàn
game. Thông báo hiển thị tối đa 20 ô; `data.diff_cells` trong JSON giữ đủ mọi ô
lệch, tối đa 90 ô.

| `data.reason` | Chi tiết cần xem |
|---|---|
| `BOARD_MISMATCH` | `diff_cells`: từng `row`, `col`, `expected`, `observed`; `board_diff_count` và tổng quân mỗi bên |
| `LOW_PIECE_CONFIDENCE` | `low_confidence_cells`: ô, quân, confidence thực tế; `confidence_threshold`, `min_piece_confidence` |
| `CONFIDENCE_INVALID` | `confidence_error`: sai kích thước, thiếu dữ liệu, NaN/Infinity hoặc ngoài [0,1] |
| `BOARD_SANITY_FAILED` | `sanity_error`: thiếu/thừa Tướng, Tướng ngoài Cung, quân không hợp lệ hoặc quá số lượng |
| `QUALITY_REJECTED` / `RECOGNITION_FAILED` | `recognition_error` và kết quả model; không suy đoán confidence là nguyên nhân nếu model không cung cấp lý do |
| `NO_FRESH_OBSERVATION` / `FRAME_UNAVAILABLE` | Camera chưa cung cấp ảnh mới đủ dữ liệu; đây không phải bằng chứng bàn khớp |
| `STALE_FRAME` / `FUTURE_FRAME` / `INVALID_TIMESTAMP` | `observed_at`, `frame_age_s`, `max_frame_age_s` nếu có |
| `DUPLICATE_FRAME` / `OUT_OF_ORDER_FRAME` / `INVALID_OBSERVATION_ID` | Mã/thời gian hiện tại và trước đó; ảnh bị loại không được tính thành mẫu mới |
| `INSUFFICIENT_STABLE_SAMPLES` | `consecutive`/`required`, số lần thử và cửa sổ chờ; ví dụ mới đạt 1/2 mẫu |
| `LAYOUT_UNSTABLE` | Hai ảnh quét toàn bàn khác nhau; `comparison=FIRST_SCAN_VS_SECOND_SCAN` và các ô lệch giữa hai ảnh |
| `CALIBRATION_UNAVAILABLE` / `CAMERA_UNAVAILABLE` | Calibration, camera hoặc recognizer chưa sẵn sàng |
| `EXCEPTION` | `exception_type`, `error`; traceback của mẫu lỗi ở `run.log`/`events.jsonl` |

Timestamp/mã quan sát không hợp lệ có giá trị NaN/Infinity được ghi thành `null`
và giữ dạng chữ ở `observed_at_repr`/`observation_id_repr`. Ngưỡng confidence
không hữu hạn cũng được giải thích bằng chữ; JSON không ghi token NaN/Infinity
không chuẩn.

Các event `camera.verification_sample`, `camera.verification_retry`,
`camera.verification_failed` và `camera.verified` dùng cùng một
`data.verification_id` cho một lần xác thực. `failure_counts` cho biết các nguyên
nhân đã gặp trong cửa sổ retry; kết quả mẫu cuối không được lấy lại từ ảnh cũ.
Khi thất bại, `game_fen`, `board_revision`, `move_id`, `expected_board_fen` và
`observed_board_fen` hỗ trợ nối lỗi với trạng thái game. Hai trường `*_board_fen`
chỉ chứa **vị trí quân**, không tự suy luận lượt chơi từ ảnh.

Quét toàn bàn qua F4 dùng `camera.scan_sample`, `camera.scan_failed`,
`camera.scan_verified` với `operation=SCAN_FULL_BOARD`. Nó so sánh hai ảnh mới
với nhau trước khi nhận lại bàn; khác với `VERIFY_EXPECTED_BOARD` so sánh ảnh với
bàn dự kiến ở startup/V/xác nhận nước robot. Không thay đổi ngưỡng hoặc quy tắc
cho phép robot chạy. Log không tự lưu ảnh/video, không sửa các phiên log cũ.

```powershell
$events = Get-Content logs/<id-phien>/events.jsonl | ForEach-Object { $_ | ConvertFrom-Json }
$failure = $events | Where-Object { $_.event -in @('camera.verification_failed', 'camera.verification_unavailable', 'camera.scan_failed') } | Select-Object -Last 1
$failure.data | Format-List
$events | Where-Object { $_.data.verification_id -eq $failure.data.verification_id }
```

## Đo tâm quân và phím Y (cập nhật 2026-10-26)

Các event có cấu trúc dùng để kiểm tra vì sao robot dừng khi đo tâm:

| Event | Nội dung |
|---|---|
| `vision.pick_attempt` | Mỗi lần thử: ô, tâm đo được `col/row`, `offset_cells`, `offset_mm`, `confidence`, lý do chấp nhận/từ chối (DEBUG) |
| `vision.pick_resolved` | Đo thành công: `mode`, `cells`, `targets` (col/row/offset/confidence), `resolution` |
| `vision.pick_failed` | Đo thất bại: `mode`, `cells`, `resolution` gồm số lần thử, số mẫu hợp lệ, độ dao động, giới hạn 6 mm/0,12 ô |
| `vision.retry_paused` | Đã tạm dừng chờ Y: `stage`, `reason`, `move_id`, `resolution` |
| `vision.retry_started` | Bắt đầu đo lại sau Y/Continue: `source`, `move_id`, `stage`, `reason` |
| `ui.retry_pick_requested` | Người dùng bấm Y/Continue: `source` (`Y`/`CONTINUE`), `mode`, `kind` (`game_move`/`self_play`/`manual_test`), `move_id`, `stage`, `resolution` |
| `ui.retry_rejected` | Y/Continue bị từ chối: `reason` (`NO_PENDING_MOVE`, `STALE_PENDING_MOVE`, `NOT_PICK_PAUSED`, `UI_WORKER_BUSY`, `STALE_SELF_PLAY_EPOCH`), `mode`, `source` |

Ví dụ lọc:

```powershell
$e = Get-Content logs\<id>\events.jsonl | ForEach-Object { $_ | ConvertFrom-Json }
$e | Where-Object { $_.event -match '^(vision|ui)\.' -and $_.event -match 'pick|retry' } |
     Select-Object timestamp,event,message,@{n='data';e={$_.data | ConvertTo-Json -Compress -Depth 6}}
```

`vision.pick_attempt` chỉ ghi khi thực sự đo tâm (trước khi gắp, sau khi lấy quân bị ăn, khi bấm Y). Camera nhận diện nền không tạo event này liên tục.

Thông điệp hiển thị ở terminal của các event trên đã kèm số liệu chính (tâm đo được, offset, số mẫu, độ dao động, lý do), nên không cần mở file vẫn biết vì sao dừng. `vision.pick_attempt` vẫn là DEBUG: chỉ hiện ở terminal khi chạy `--log-level DEBUG`, nhưng luôn có trong `run.log` và `events.jsonl`.

### Đọc kết quả

- `spread_cells` lớn hơn `jitter_limit_cells` → các lần đo dao động quá mức.
- `offset_cells`/`offset_mm` lớn hơn giới hạn → quân nằm quá xa tâm ô.
- `valid_samples` nhỏ hơn 2 → không đủ mẫu ổn định.
- `attempts_detail[].reason` cho biết lần thử đó bị loại vì gì (không thấy quân, nhầm quân bên cạnh, offset quá lớn…).

Các event này chỉ quan sát; không làm thay đổi quyết định gắp hoặc nới giới hạn an toàn.

## Calibration camera và đóng khẩn cấp (cập nhật 2026-10-28)

- `physical.camera_calibration_requested` (INFO): người vận hành tick **Chấm lại 4 góc bàn từ camera** trước khi mở physical.
- `camera.calibration_created` (INFO): cửa sổ `CALIBRATE` đã lưu `perspective.npy` mới; có `path`, `sha256`, `camera_index`.
- `app.force_close_armed` (WARNING): đã nhận Ctrl+C lần đầu trong màn hình recovery; phải nhấn lần nữa trong 5 giây.
- `app.force_close_refused` (ERROR): không buộc đóng vì robot còn quyền chuyển động hoặc còn giao dịch chờ.
- `app.force_close` (ERROR): người vận hành xác nhận Ctrl+C lần hai và tiến trình thoát cưỡng bức.

## Calibration camera lúc khởi động (cập nhật 2026-10-26)

- `camera.calibration_loaded` (INFO): dùng `perspective.npy` đã lưu; có `path`, `sha256`, `camera_index`.
- `camera.calibration_created` (INFO): vừa tạo calibration mới; có `path`, `sha256`, `camera_index`, `recalibrate`.

Mặc định `--physical` dùng file đã lưu. Chỉ mở cửa sổ calibration khi chưa có file hoặc khi chạy `--recalibrate-camera`. File hỏng làm startup dừng với hướng dẫn rõ.

## Camera recognition và verify bàn (cập nhật 2026-10-26)

| Event | Nội dung |
|---|---|
| `camera.recognition_unavailable` | ERROR/`STARTUP_FAILED`: thiếu CChess ONNX, YOLO `best.pt`, detector hoặc CameraMonitor; physical không chạy |
| `camera.recognition_ready` | INFO: đủ model + CameraMonitor cho physical |
| `camera.verification_retry` | DEBUG: chưa đủ mẫu liên tiếp; đang chờ bàn ổn định trong cửa sổ retry |
| `camera.verification_failed` | WARNING: có `attempts`, `diff_cells`, `expected_board`, `observed_board` |

`verify_physical_board` vẫn yêu cầu khớp **chính xác toàn bộ 90 ô**. Cấu hình retry:

```python
VERIFY_BOARD_RETRY_TIMEOUT_SEC = 2.0
VERIFY_BOARD_RETRY_POLL_SEC = 0.15
```

Đặt timeout = 0 để tắt retry (giữ hành vi cũ).

## Đồng bộ quân khi kẹp (cập nhật 2026-10-26)

- `twin.animation_attached` (INFO): viewer ước lượng quân đã được kẹp; data gồm
  `piece_id`, `physical_grasp_verified=false`.
- `twin.animation_released` (INFO): viewer ước lượng quân đã được thả.
- `twin.animation_failed` (WARNING): không thể cập nhật world/viewer; không phải
  bằng chứng robot không gắp được.
- Command animation bám theo **cạnh lệnh kẹp** (close/open), không phụ thuộc
  một lần poll telemetry mới. Poll telemetry định kỳ vẫn cập nhật vị trí tay.
- Đây là hiển thị ước lượng: không thay thế camera xác nhận bàn sau nước đi và
  không chứng minh kẹp đã giữ quân thật.

### `world_state.captured_pieces` (2026-10-26)

Captured pieces are removed from the physics body list but retained as
immutable snapshots in `world_state.captured_pieces`:

```json
{
  "type": "world_state",
  "pieces": [ ... active bodies ... ],
  "captured_pieces": [
    {
      "id": "red_cannon_1",
      "pose_world": [ ... ],
      "orientation_quat_world": [ ... ],
      "physical_state": "OUT_OF_BOUNDS",
      "captured": true
    }
  ]
}
```

The viewer draws these snapshots in the tray. They are visual history, not
physical grasp or tray-calibration evidence. `pieces` contains only live bodies;
`captured_pieces` is cleared when the game resets and the bodies respawn.

### Packet `gripper_command` (2026-10-26)

Chỉ physical bridge phát packet này khi lệnh kẹp đóng/mở:

```json
{
  "type": "gripper_command",
  "source": "PHYSICAL",
  "phase": "CLOSE",
  "action": "close",
  "piece_id": "black_cannon_0",
  "captured_piece_id": null,
  "move_id": "...",
  "physical_grasp_verified": false
}
```

- `action` là `close`, `open_max` hoặc `close_to_safe_gap`.
- `close_to_safe_gap` không attach/release và không phát packet.
- Viewer chỉ áp dụng khi `source === "PHYSICAL"` và `state.liveSource === "PHYSICAL"`.
- Virtual/game-only không phát packet; nếu có packet lạc, viewer bỏ qua.
- Packet chỉ điều khiển animation kẹp; `world_state` vẫn là nguồn vị trí quân.
- Packet physical cuối cùng được replay trong snapshot đầu tiên khi viewer reconnect.

## Z mặt bàn cho mirror (cập nhật 2026-10-26)

- `board.surface_z_resolved` (INFO): mirror đã chọn nguồn Z mặt bàn.
  Data gồm `source` (`MEASURED`/`R1_R4`), `value_mm`, và với `R1_R4` là
  `z_mm`, `spread_mm`, `tolerance_mm`.
- `R1_R4` chỉ được dùng khi `R1_R4_TAUGHT_AT_BOARD_SURFACE=True`; nếu không,
  mirror báo lỗi và dùng relay bàn mặc định.
- Đây là Z cho **mirror hiển thị**, không thay đổi `PICK_Z`/`PLACE_Z`/`SAFE_Z`
  của lệnh robot.

## Retry đo tâm gắp (cập nhật 2026-10-26)

- `vision.pick_retry` (INFO): một lần đo tâm chưa đạt và sẽ thử lại;
  data gồm `attempt`, `attempts`, `stage`, `reason`, `resolution`.
- Cấu hình:
  ```python
  VISUAL_PICK_RETRY_ATTEMPTS = 3
  VISUAL_PICK_RETRY_INTERVAL_SEC = 0.4
  ```
- Hết lượt thử, hệ thống vẫn chuyển sang `PICK_PAUSED` / `ui.retry_rejected` như cũ;
  không nới giới hạn 6 mm hoặc 0.12 ô.

## Motion profile chưa kiểm chứng

- `motion.profile_unverified` (WARNING): physical startup đang dùng profile từ
  `origin/feature/visual-correction-v2@fb0598d` nhưng `MOTION_PROFILE_VERIFIED=False`.
  Data gồm `source`, `safe_z`, `rotation`, `move_speed`.
- Đây chỉ là cảnh báo, không tự hạ/tăng SAFE_Z hoặc đổi ROTATION.
- Sau khi đo và xác nhận trên pendant, đặt `MOTION_PROFILE_VERIFIED=True` và ghi
  provenance trong `docs/VISUAL_V2_MOTION_PROFILE.md`.

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
