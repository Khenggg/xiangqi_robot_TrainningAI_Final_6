# Follow-up review (2026-10-12)

Read `RELIABILITY_RECHECK_20261012.md` for seven additional corrections, final test scope and the latest delivery manifest. The report below records the earlier correction snapshot.

---

# Sửa độ tin cậy game, camera, FR3 và mô phỏng — 12/10/2026

## Phạm vi đã được người dùng chốt

- Lệnh FR3 thật dùng tọa độ và chiều cao của `origin/feature/visual-correction-v2`, đã fetch tới `fb0598d`.
- Theo yêu cầu hiện tại, **không thêm collision planner mô phỏng vào đường gửi lệnh vật lý**. Collision guard của chế độ virtual giữ nguyên.
- Mô phỏng physical hiển thị khớp đo được và animation ngàm/quân theo lệnh; animation không chứng minh gắp thật.
- Không kết nối, enable, di chuyển hoặc đóng/mở gripper thật trong đợt sửa. Mọi RPC trong test là mock hoặc HTTP server localhost giả.
- Làm tuần tự trong worktree `D:/OJT/_reliability_fix_20261012`, dựa trên HEAD `7d8c5de` cùng snapshot chính xác patch đang có ở repo chính. Không reset/clean/cherry-pick đè patch người dùng.

Báo cáo `docs/reviews/PHYSICAL_GAME_RELIABILITY_AUDIT.md` là ảnh chụp review tĩnh trước sửa, được giữ nguyên. Các đề xuất F01/F02 trong báo cáo đó được thay phạm vi bởi quyết định người dùng ở trên; không được dùng như mô tả hành vi runtime sau sửa.

## Thay đổi thực thi

| Nhóm | Thay đổi và nơi kiểm tra | Giới hạn bằng chứng |
| --- | --- | --- |
| Tọa độ/Z physical | `config.py`, `robot_VIP.FR5Robot.board_to_pose`: SAFE_Z=220 mm; PICK_Z/PLACE_Z=178 mm; tool rotation `[180,0,-73.2]`; margin ngoài bàn=10 mm. R2/R3/R4 dùng XY đã dạy; R1 và các ô khác đi bilinear, cộng OFFSET_X=5 mm/OFFSET_Y=0 như donor. Target float camera đi bilinear. | Giữ đúng quy tắc donor, không xác nhận các giá trị phù hợp bàn thật hôm nay. Không đổi tốc độ/pulse gripper hoặc artifact calibration. |
| Frame waypoint | Loader giữ tool/user của R1–R4 và trash; nhận frame từ R1; HOMECHESS/trash khác hoặc thiếu metadata bị từ chối trước motion. `robot_VIP._verify_waypoint_frame`, `_move_piece_sequence`. | Không tự chuyển đổi user frame. Bàn mirror metric vẫn yêu cầu calibration base hợp lệ. |
| Physical readiness | `HardwareManager.physical_telemetry_ready` và `FR5Robot._require_actuation` kiểm tra connected/valid/measurement age/status trước dispatch/stage. Operator F9/F10 vẫn tách khỏi Connect live. | Không thay controller safety. Tắt Python worker không phải lệnh dừng FR3. |
| RPC | `rpc_transport.SingleAttemptTransport/BoundedRPCProxy`; SDK dùng transport này; chờ reconnect có giới hạn, timeout socket riêng, serialize calls, mất reply trả `RpcOutcomeUnknown` thay vì resend. Receiver thread owned được join có giới hạn. | Timeout socket không chứng minh thời điểm robot đã dừng. Kết quả motion unknown yêu cầu đối soát/kiểm tra pendant, không replay. |
| AI | Moonfish đọc stdout qua queue, drain stderr, deadline handshake/bestmove có hiệu lực; lỗi dừng engine, lần retry explicit có thể restart. `GameState.retire_ai_job` giữ worker cũ khi reset/rescan/rollback/emergency, reaps trước request mới. | Python thread không bị cưỡng bức kill; token cũ không được commit. |
| Giao diện | Startup, difficulty, physical enable, SPACE/scan/recovery, mouse override và virtual AI motion được submit/poll qua worker; API spectator chạy FIFO riêng. `main.py`, `session_startup.py`, `InputHandler._queue_or_run`. | Chưa benchmark ánh sáng/driver/inference thật cùng FR3. Khi motion worker còn chạy, input thay đổi bàn được khóa. |
| Recovery | Self-play FAULTED/ENDED mở V/F4/confirm turn/New Game/Continue sau khi worker dừng; chỉ thoát fault khi đồng bộ/pending được giải quyết. `SelfPlayController.recovery_input_allowed/finish_recovery`, routing ở main. | Scan thất bại không tự cấp quyền motion hoặc đoán bàn mới. |
| Commit | Physical commit đã được camera xác nhận giữ FEN/lượt/history/move ID dù observer lỗi, trả committed=True và latch scene fault. Không chuyển động lại để sửa viewer. `GameState.commit_pending_physical_move`. | Boolean cho biết đã commit; scene fault vẫn phải đọc riêng. Chưa thay toàn bộ API commit bằng kiểu kết quả mới. |
| Camera | AUTO truyền confidence như SPACE; HvH dùng màu lượt hiện tại; baseline đầu ván physical đối chiếu expected board; baseline lỗi sau robot/manual override tạm dừng scan và chỉ dẫn V. | Không huấn luyện lại model; test fixture không chứng minh chất lượng camera thật. |
| Spectator API | create/FEN/end xếp FIFO, không block GUI; self-play gửi FEN sau commit và end khi terminal. Tạo room mới không tiếp tục dùng room cũ nếu đóng thất bại. | Giá trị public trả về là accepted-to-queue, không phải server ACK; queue hữu hạn và có log failure/full. Shutdown cho worker daemon hoàn tất best-effort. |
| Đồng bộ cánh tay | Backend đọc đo được tách khỏi provider bàn; chưa có contact calibration thì `PhysicalStateRelay` vẫn đưa khớp tới WS, viewer là read-only. | Không tạo calibration giả; preview bàn lúc thiếu calibration không khẳng định khớp bàn thật. |
| Animation | `LiveTwinBridge.begin/animate/finish_command_animation` nối với facade; expected piece/captured piece gắn/thả theo command edge. Lỗi hiển thị log riêng, không đổi kết quả motion. Đối soát camera sau nước đi ghi đè estimate. | `physical_grasp_verified=False`; attachment này không đo tiếp xúc ngàm. |
| Viewer | Reject disconnected/invalid/stale physical packet; badge chờ telemetry, watchdog dữ liệu và deadline connect; callback socket cũ không ghi đè socket mới; packet bị reject không cập nhật ngàm. | HTTP probe/Node không thay thế nghiệm thu browser+camera+FR3 thật. |
| Lifecycle | Startup transaction cleanup partial resource và giữ home retry; fatal exit nonzero; cleanup độc lập collect lỗi và đóng RPC owned sau reader/worker; read-only cleanup không enable/gripper. | Nếu worker/reader chưa dừng, resource đang dùng được giữ mở và báo lỗi; không giả định shutdown Python làm robot ngừng. |

## Review và phạm vi kiểm chứng

Review thực hiện tuần tự theo skill code-review: đối chiếu incremental diff với snapshot repo chính, đọc callers/contracts, kiểm tra failure path và chạy regression. Không tạo subagent. Graph MCP đã index/get_architecture/search_graph/trace_path/detect_changes; một số truy vết không trả symbol và detect_changes không trả impacted_symbols. Vì vậy không dùng kết quả graph trống để khẳng định blast radius bằng 0. Các thay đổi SDK diện rộng là thay vòng chờ reconnect không giới hạn bằng cùng helper; test HTTP lost-reply chạy qua chính vendor MoveCart, không chỉ mock facade.

Các test cũ được giữ. Fixture thiếu frame metadata, mock thread bằng `object()`, giả định API synchronous hoặc startup luôn xong sau đúng ba frame được cập nhật theo contract mới. Negative tests code112, stale, frame sai, mất reply, low-confidence và không replay vẫn tồn tại.

### Kết quả thực thi

Kết quả acceptance cuối và hash giao về repo chính được ghi ở `reports/reliability-fixes-20261012/REPORT.md` và `delivery-manifest.json`.

- Lần full đầu: 953 đạt, 12 lỗi; lần full tiếp: 965 đạt, 2 lỗi fixture. Log giữ cả các lần thất bại.
- Gate sau sửa fixture: 87 đạt (`final-repaired.log`). Gate tích hợp mirror/entrypoint: 16 đạt (`integration.log`).
- Silent engine là child process thật; lost reply là HTTP endpoint localhost thật gọi qua vendor SDK, chỉ constructor controller được bỏ qua.
- Test animation đi qua HardwareManager + facade + PyBullet thật, RPC giả: quân theo arm pose trong giai đoạn attach, release và camera-confirmed reconciliation về ô đích.
- Smoke cả 3 mode qua `main.py` thật, Moonfish/PyBullet/HTTP/WS thật, SDL dummy: HTTP200 với JS MIME đúng; nhận robot_state/board_placement/world_state; 32 quân và scene synced; shutdown không lỗi. Không di chuyển quân trong smoke này, không gọi là nghiệm thu 10 nước mỗi mode. Ảnh GUI/JSON/log lưu theo tên mode.
- Node kiểm tra freshness, gripper/telemetry contracts; `node --check main.mjs`; Python compileall. Chi tiết exit trong REPORT.

### Điều chưa xác minh ngoài đời

Chưa xác minh R1–R4/TCP/Z/bãi thải/HOMECHESS của setup thật, chất lượng nhận dạng, latency camera/robot/browser đồng thời, firmware completion, clearance, grasp/drop/capture vật lý. Không có cam/FR3 kết nối trong tác vụ này. Mức độ tin cậy cao cho failure boundaries đã chạy; hành vi phần cứng và đúng calibration còn chưa xác minh.

Thiếu contact calibration chỉ cho phép phản chiếu cánh tay bằng raw telemetry và preview bàn có cảnh báo. Muốn khẳng định quân trên viewer khớp quân thật cần provider bàn được hiệu chuẩn. Các ngưỡng gắp/Z hiện theo donor, không được coi là phép đo mới của bàn đang setup.

## Khởi động sau khi nhận patch

```powershell
cd D:\OJT\xiangqi_robot_TrainningAI_Final_6
.\RUN.bat
.\RUN.bat --virtual
.\RUN.bat --physical
```

Mặc định: game + virtual runtime + HTTP/WS sau khi chọn mode. `--virtual`: game-only, tắt mô phỏng/viewer đúng yêu cầu trước đây. `--physical`: camera + kết nối FR3 read-only; Connect live đọc WS, F9/F10 mới là xác nhận quyền motion. `--no-viewer` chỉ tắt HTTP/browser; dùng `--viewer-port`/`--telemetry-port` khi cổng đang bị dùng. Dừng phiên cũ rồi mở phiên mới để nạp code; reload trang web để nhận module mới.
