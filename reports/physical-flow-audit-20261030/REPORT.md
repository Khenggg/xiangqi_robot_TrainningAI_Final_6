# Audit luồng vật lý — 2026-10-30

## Phạm vi và kết luận

Kiểm tra working tree hiện tại tại HEAD `18e67fc9006a91a2a32c4c861974760089a687de`.
Working tree có nhiều thay đổi sẵn có; báo cáo áp dụng cho trạng thái source được
ghi hash trong `source-state.json`, không đại diện cho HEAD sạch.

**3 finding P1, còn OPEN.** Đã tái hiện bằng các method production với SDK/camera
giả và dữ liệu tất định. Không kết nối robot/camera thật, không phát lệnh ra phần
cứng. Không sửa production code hoặc test trong lượt audit này.

Đã xem đường đi startup/session → xác nhận bàn → bật quyền vật lý → lấy tâm quân
→ semantic guard/dispatch → commit/recovery/controlled stop và biên SDK.
Đây là audit có phạm vi, không phải chứng nhận toàn bộ hệ thống không còn lỗi.

## P1-01 — Yêu cầu dừng trong lúc bật robot vẫn để lọt RobotEnable(1)

- **Vị trí:** `src/hardware/robot_VIP.py:166-190`, đặc biệt `181-189`;
  `src/hardware/hardware_manager.py:535-548`.
- **Nguyên nhân:** low-level chỉ kiểm tra stop latch trước handshake. Sau khi
  `Mode(0)` trả về, code gửi `RobotEnable(1)`, đặt quyền chuyển động và xóa latch
  mà không kiểm tra yêu cầu dừng mới. Manager kiểm tra generation sau khi low-level
  trả về nên phát hiện được hủy, nhưng lúc đó enable đã được gửi.
- **Tái hiện VERIFIED:** dùng `MotionWorker` và `ControlledStopCoordinator` thật,
  chặn fake `Mode` bằng Event, gọi coordinator `begin`, rồi cho `Mode` trả về.
  Thứ tự thu được: `Mode(0)` → `operator_stop_requested=true` → `RobotEnable(1)`.
  Manager trả lỗi `Enable cancelled by a newer stop request`, cuối cùng latch lại
  được đặt nhưng `physical_motion_authorized=true`. Probe low-level độc lập còn
  cho thấy activation tự xóa stop latch và trả `True`.
- **Tác động:** có thể bật controller sau khi người vận hành đã yêu cầu dừng.
  Probe không chứng minh robot thật đã chuyển động.
- **Khuyến nghị:** mang generation/token hủy xuyên suốt handshake; kiểm tra trước
  từng lệnh controller và sau từng phản hồi. Không xóa stop mới đến trong activation;
  không giải quyết bằng cách chỉ thêm kiểm tra sau `RobotEnable`.
- **Kiểm chứng cần có khi sửa:** dừng trong lúc `Mode` chờ, trước enable và trong
  lúc enable chờ; trường hợp phục hồi stop cũ hợp lệ; phản hồi enable mất/không rõ.

## P1-02 — Kiểm tra IDLE hết hiệu lực trong lúc chờ camera vẫn cho bật robot

- **Vị trí:** `src/hardware/hardware_manager.py:517-540`;
  `src/hardware/robot_VIP.py:166-190`.
- **Nguyên nhân:** freshness/IDLE chỉ được kiểm tra trước `verify_physical_board`.
  Camera verification và đồng bộ bàn có thể mất thời gian. Trước khi gọi activation
  không đọc lại telemetry; low-level activation cũng không xác nhận lại.
- **Tái hiện VERIFIED:** fake telemetry ban đầu fresh/IDLE; trong lúc xác nhận bàn,
  lần lượt đổi sang MOVING hoặc làm measurement cũ 3 giây. Cả hai trường hợp vẫn
  trả `enabled=true`, gửi fake `Mode(0)` và `RobotEnable(1)`. Mỗi trường hợp chỉ đọc
  telemetry một lần. Trường hợp đối chứng fresh/IDLE không đổi cũng bật bình thường.
- **Tác động:** điều kiện cho phép bật quyền vật lý có thể không còn đúng tại thời
  điểm gửi lệnh controller.
- **Khuyến nghị:** đọc lại telemetry fresh/IDLE sau xác nhận camera và ngay trước
  handshake; ràng buộc với token hủy và thời hạn quan sát. Đây là lỗi độc lập với
  P1-01: không cần có thao tác dừng để tái hiện.
- **Kiểm chứng cần có khi sửa:** telemetry đổi MOVING, hết hạn hoặc mất kết nối
  trong lúc camera chờ đều phải chặn enable; fresh/IDLE ổn định vẫn được phép.

## P1-03 — Mất camera ở mẫu cuối vẫn dùng hai tâm quân cũ để dispatch

- **Vị trí:** `src/hardware/hardware_manager.py:983-1056`;
  `src/vision/visual_pick_estimator.py:232-250`;
  `src/vision/visual_pick_modes.py:17-23`.
- **Nguyên nhân:** nhánh center ghi lỗi lấy ảnh rồi tiếp tục; mẫu lỗi không làm mất
  hiệu lực các tâm đã thu được. Aggregate chỉ yêu cầu đủ số mẫu hợp lệ và jitter,
  không yêu cầu mẫu mới nhất còn xác nhận tâm. Kết quả vẫn ghi `failure=""` và
  `Strict center consensus` khi lần lấy ảnh cuối báo mất camera.
- **Tái hiện VERIFIED:** hai frame đầu cho tâm hợp lệ giống nhau; frame thứ ba
  ném `camera disconnected on latest sample`. Sampler production trả target.
  Đưa target qua `GameState`/move context hợp lệ và `execute_piece_move` thật:
  fake `robot.move_piece` được gọi một lần, báo success; camera health không được
  kiểm tra thêm. Không dùng robot thật và không commit kết quả thành nước cờ thật.
- **Tác động:** đường pick có thể bắt đầu với tọa độ lấy trước sự cố mất camera.
  Finding áp dụng nhánh center được tái hiện; không suy rộng sang mọi pick mode.
- **Khuyến nghị:** lưu cả mẫu thất bại, buộc mẫu cuối hợp lệ và còn mới trước
  dispatch; camera mất kết nối phải hủy/đo lại trong giới hạn. Chỉ giữ quorum từ
  các mẫu cũ là chưa đủ để xác nhận camera hiện còn hoạt động.
- **Kiểm chứng cần có khi sửa:** lỗi/missing frame cuối sau hai mẫu tốt phải chặn
  dispatch; mất rồi phục hồi phải đo lại; nhóm mẫu mới ổn định vẫn dispatch được.

## Nguồn gốc thay đổi

**PRE-EXISTING so với hai thay đổi startup phiên mới và log FEN vừa thực hiện.**
Các hàm activation/center sampler nêu trên không được sửa trong hai tác vụ đó.
Hai hàm manager được so sánh source trực tiếp với snapshot trước tác vụ log FEN:
đều giống nhau (`parent-evidence.json`). Không khẳng định chúng giống HEAD:
`source-state.json` ghi rõ cả ba hàm khác HEAD trong working tree đang có thay đổi.
Không xác định tác giả hoặc thời điểm đưa lỗi vào trước snapshot này.

## Bằng chứng và lệnh kiểm chứng

Môi trường: Windows, Python 3.12.10 trong `.venv312`. Các probe chỉ dùng mock.

```powershell
.\.venv312\Scripts\python.exe -X utf8 reports/physical-flow-audit-20261030/probe_parent.py
.\.venv312\Scripts\python.exe -X utf8 reports/physical-flow-audit-20261030/motion-review/probe_activation_cancellation.py
```

**PASS, exit 0:** assertions của probe tái hiện các lỗi trên. Đây là PASS của phép
tái hiện lỗi, không có nghĩa production đã được sửa. Parent probe có tùy chọn
`--baseline-hardware` để so với snapshot cục bộ nếu còn giữ; không có tham số này
thì các trường so baseline là `null`. Lần lưu bằng chứng có truyền snapshot,
hai trường baseline đều `true`.

Kết quả chi tiết: `parent-evidence.json`. Source tái hiện low-level độc lập nằm tại
`motion-review/probe_activation_cancellation.py`.

Nhóm test tập trung đã chạy:

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv312\Scripts') + ';' + $env:PATH
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_legacy_physical_robot_gates.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_physical_fr3_backend.py,tests/unit/test_ai_home_approach_recovery.py,tests/unit/test_pick_target_retry.py,tests/unit/test_physical_camera_commit_gate.py,tests/unit/test_brd_actor_credentials.py,tests/unit/test_session_user_flows.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_retry_logging.py,tests/unit/test_board_verify_retry.py,tests/unit/test_camera_startup_and_health.py
```

**FAIL, exit 1: 104 passed, 3 failed.** Runner dừng trước serial gate sau lỗi.
Ba ca thất bại được chạy lại riêng bằng cùng runner, exit 1, vẫn 3 failed:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_camera_startup_and_health.py::test_old_board_confirmation_does_not_automatically_retry_physical_robot,tests/unit/test_ai_home_approach_recovery.py::test_first_ai_cannon_move_routes_safely_or_leaves_board_uncommitted
```

Output lần chạy lại được lưu ở `failing-tests.txt`:

- Test old-board confirmation: fixture dùng `SimpleNamespace`, thiếu recovery
  method và `pending_ai_move.expected_board`; cuối cùng `KeyError: expected_board`
  tại `src/ui/input_handler.py:918`. Chưa coi đây là một lỗi production vật lý
  được xác nhận vì `GameState` thật có contract đầy đủ hơn fixture này.
- Hai tham số của test AI cannon/home: assertion tại
  `tests/unit/test_ai_home_approach_recovery.py:64` đòi `red_rook_0` xuất hiện trong
  `rejected_paths`, nhưng không xuất hiện. Đây là đường virtual/PyBullet trong
  test, chưa phải bằng chứng robot thật thất bại. Chưa sửa hoặc xác định đầy đủ
  nguyên nhân assertion lệch.

Full regression: **NOT RUN**. Camera/FR3 thật, grasp, calibration, quỹ đạo và
controlled stop vật lý: **NOT RUN**. Không thể kết luận độ chính xác chuyển động
hoặc độ an toàn phần cứng chỉ từ các probe này.

Ưu tiên xử lý: P1-01 → P1-02 → P1-03; mỗi bản sửa cần regression tập trung trước
khi cân nhắc kiểm chứng phần cứng có ủy quyền.
