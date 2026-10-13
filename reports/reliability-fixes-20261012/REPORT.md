# Kết quả kiểm chứng và bàn giao — 12/10/2026

## Nguồn và scope

- Repo chính: `D:/OJT/xiangqi_robot_TrainningAI_Final_6`, branch `feature/unified-robot-vs-robot`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e`.
- Snapshot giữ patch tracked/untracked đang có; baseline 467 file. Worktree: `D:/OJT/_reliability_fix_20261012`.
- Fetch donor `origin/feature/visual-correction-v2` tới `fb0598d`; chỉ lấy quy tắc tọa độ/Z/margin/rotation physical được yêu cầu. Không merge cả branch, không commit/push/reset/clean.
- Chi tiết sửa và giới hạn: `docs/RELIABILITY_FIXES_20261012.md`.

## Gate cuối

| Gate | Lệnh / evidence | Kết quả |
| --- | --- | --- |
| Full regression Python 3.12.10 | `tools/test_fast.ps1 -Mode Balanced -Tests tests -Durations 5`, worktree .testvenv, basetemp `.pytest_tmp/acceptance`; `acceptance.log` | Exit 0: 968 parallel + 8 serial đạt; 567.58 s; hardware/slow không chạy |
| Gate sửa fixture/lifecycle/recovery | Runner 2 workers, các file ghi trong `final-repaired.log` | Exit 0: 87 đạt |
| GUI routing / facade-PyBullet integration | `integration.log` | Exit 0: 16 đạt |
| Node freshness | `node tests/unit/test_viewer_freshness.mjs` | Exit 0: valid/stale/disconnected/missing/invalid physical, virtual compatibility |
| Viewer gripper/telemetry | `node tests/unit/test_viewer_gripper_and_telemetry.mjs` | Exit 0: canonical asset + 13 negative profile và 8 negative world packet cases |
| Syntax/import readiness | `node --check robot-3d-viewer/main.mjs`; `.testvenv/Scripts/python -m compileall -q src main.py`; `.venv312/Scripts/python main.py --help` | Exit 0; help không mở thiết bị |
| Main virtual HvR / HvH / RvR | `smoke_startup.py <mode>`, log + JSON + GUI PNG theo mode | Cả ba exit 0; Moonfish/PyBullet thật; HTTP200 đúng JS MIME; WS nhận robot_state/board_placement/world_state; 32 quân; scene synced; cleanup |

Full regression giữ 8 warning deprecated WebSocket ở parallel và 2 ở serial; không có failing test. Lần đầu `full-regression.log` 953 đạt/12 lỗi, lần tiếp `full-final.log` 965 đạt/2 lỗi fixture; các log này giữ để truy nguyên, **acceptance.log mới là gate cuối**. Không bỏ negative test hoặc đổi logic production để fake thành công.

Smoke main dùng SDL dummy và sự kiện kiểm thử, không computer-use qua chuột vật lý; không chơi 10 nước từng mode trong smoke. HTTP/WS probe không phải test WebGL browser. GUI PNG RvR đã được xem lại. Full suite và test mirror đi qua PyBullet; toàn bộ RPC physical là mock/localhost server.

Test HTTP lost reply đi qua chính SDK `RPC.MoveCart` với HTTP endpoint localhost nhận request rồi đóng kết nối: chỉ nhận một request, exception `RpcOutcomeUnknown`, không replay. Silent Moonfish test dùng child process thật còn sống nhưng không trả handshake/bestmove, deadline giải phóng engine/lock. Animation test đi HardwareManager → physical facade → mock RPC → real PyBullet, quan sát quân theo khớp mới, release và reconcile đúng ô; không chứng minh tiếp xúc ngàm thật.

## Review

Inline review tuần tự: source diff so snapshot main (bỏ khác biệt CRLF/LF), callers/contracts, lost-reply/stale/frame-error/commit/recovery/cleanup. Theo user, không spawn subagent. MCP graph indexed/architecture/search/trace/detect_changes; graph không trả impacted_symbols nên không dùng nó làm chứng cứ không ảnh hưởng. Gate cuối chạy sau các sửa source cuối cùng; sau gate chỉ cập nhật tài liệu và copy verified files.

## Bàn giao

`delivery-manifest.json` ghi pre/post SHA256 của từng source/test/doc được đưa về main. Copy có preflight đối chiếu hash main với snapshot; không ghi file thay đổi đồng thời. `delivery-verification.json` ghi số file và parity sau copy. Không đưa .testvenv/node_modules junction/cache vào repo chính. Pytest 8.4.2/xdist 3.8.0 chỉ cài trong môi trường test riêng; runtime .venv312 của main không bị thay dependency.

## Phần cứng và điều còn cần xác minh

Không kết nối/enable/move/gripper FR3 thật hay đọc camera thật. Physical coordinates/Z theo donor nhưng không có phép đo mới cho setup hiện tại. Không thêm simulator collision gate cho physical, theo yêu cầu; virtual giữ guard hiện có. Missing board contact calibration cho phép raw arm telemetry, không cho phép tuyên bố preview bàn/quân khớp ngoài đời. Live camera latency, recognize accuracy, frame/height measurements, firmware completion và commissioning vẫn chưa xác minh.
