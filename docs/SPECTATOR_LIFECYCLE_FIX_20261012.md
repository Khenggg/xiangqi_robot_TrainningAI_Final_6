# Sửa vòng đời self-play / spectator — 12/10/2026

## Phạm vi và nguyên nhân

Kiểm tra trong worktree `D:/OJT/_reliability_fix_20261012`, từ đúng trạng thái đã bàn giao ở vòng rà soát trước. Không kết nối camera/FR3, không gửi HTTP ra dịch vụ spectator thật. Không đổi tọa độ, chiều cao gắp, calibration hoặc collision guard.

| Lỗi | Nguồn gốc / ảnh hưởng | Sửa và vị trí mã | Bằng chứng |
| --- | --- | --- | --- |
| F8 kết thúc phòng, F6 không mở lại phòng | Hồi quy từ việc bổ sung kết thúc spectator ở vòng rà soát trước: game tự chạy lại nhưng FEN không được đưa vào phòng mới | `SelfPlayController.start`, `src/core/self_play_controller.py:112`; `TuongKyDaiSuClient.ensure_match`, `src/api/simulation_client.py:91` | Chặn HTTP end đang chờ rồi restart ngay; kiểm tra FIFO end → create → FEN phòng mới |
| Phòng bị mở hai lần nếu cả startup và self-play cùng yêu cầu | Rủi ro tích hợp khi sửa restart; `room_id` chưa có trong lúc create đang chờ nên không đủ để quyết định | Theo dõi yêu cầu phiên riêng với kết quả HTTP; `ensure_match` tái sử dụng cả phòng đang mở và yêu cầu mở đang chờ | Kiểm tra startup của cả ba chế độ, chỉ một create mỗi lần |
| F6 bắt đầu trên game_over | Có sẵn trước vòng này: có thể khởi chạy lại controller trên bàn đã kết thúc | Chặn trước kiểm tra camera, thông báo chọn New Game | Test finished game không gọi verifier hoặc HTTP |
| Thông báo thất bại self-play bị thay bằng hướng dẫn F7/F8 | Có sẵn trong `main._start_selected_game` | Chỉ ghi hướng dẫn nếu `start` thành công; `main.py:127` | Verifier từ chối và thông báo lỗi vẫn còn |
| End lặp / FEN mới sau end còn lọt hàng đợi | Có sẵn: `pending` chỉ nói có việc đang chờ, không chứng minh phòng còn được phép nhận FEN | Quyết định trạng thái phiên cùng lock với enqueue; lỗi queue full không thay trạng thái | Test duplicate end, post-end FEN, full queue, close |

Mức tin cậy: **VERIFIED bằng mocks và luồng phần mềm thật** cho các ca trên. Không suy ra độ tin cậy nhận dạng/chuyển động vật lý.

## Giao kèo sau sửa

- Startup dùng `ensure_match`; F6 có thể chạy lại ván chưa kết thúc sau F8, nhưng vẫn phải vượt qua các điều kiện readiness/recovery/camera hiện hữu.
- Khi cần mở phòng mới, snapshot `current_fen` được gửi trong cùng job với create, trước các FEN tiếp theo. Nếu end cũ lỗi, create mới vẫn tách `room_id` cũ trước khi mở phòng.
- New Game dùng `create_match` để tạo phiên mới và gửi FEN ban đầu, kể cả khi phòng cũ còn đang mở. F6 sau đó tái sử dụng phiên đã được New Game yêu cầu.
- `True` từ API public chỉ có nghĩa đã xếp hàng/tái sử dụng yêu cầu; **không phải** xác nhận từ server. Create thất bại cho phép `ensure_match` ở lần sau thử lại. Thất bại cũ không xóa yêu cầu phiên mới đã xếp hàng.
- Spectator không phải WebSocket của viewer 3D. Đợt này không thay đổi transport viewer, mô hình bàn/quân hay đường đi robot.

## Kiểm chứng

Môi trường: Windows, Python 3.12.10, pytest 8.4.2, xdist 3.8.0 trong `.testvenv` của worktree. Runtime dùng các thư viện của `.venv312`; không sửa môi trường Python repo chính.

| Gate | Kết quả | Log trong `reports/reliability-fixes-20261012/` |
| --- | --- | --- |
| Trước sửa | FAIL: 6 thất bại / 2 đạt; gồm API mới chưa có và lỗi cũ tái hiện | `session-red.log` |
| Sau sửa, ca tập trung ban đầu | PASS: 38 test, exit 0 | `session-focused.log` |
| Ca cuối và hồi quy subsystem | PASS: 85 test, exit 0; có 15 ca lifecycle mới | `session-subsystem.log` |
| Vòng lặp `main.py` thật với sự kiện Pygame headless | PASS: khởi tạo → F8 → F6 → đóng; hai phòng đúng thứ tự, FEN không đổi; 0 lệnh robot | `session-gui-4.log`, `session-gui-evidence.json` |
| Hồi quy toàn dự án | PASS: 996 test song song + 8 tuần tự = 1.004 test; exit 0; 521,9 giây | `session-full.log` |
| Kiểm tra cú pháp / hash repo chính | PASS sau copy có bảo vệ baseline; 9 file khớp worktree | `session-lifecycle-delivery-verification.json`, `session-primary-compile.log` |

Lệnh chạy (cwd worktree):

```powershell
$env:PATH=(Join-Path (Get-Location) '.testvenv/Scripts')+';'+$env:PATH
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/session-subsystem --tb=short'
./tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_spectator_lifecycle.py,tests/test_simulation_client.py,tests/unit/test_reliability_audit_fixes.py,tests/unit/test_reliability_recheck.py,tests/unit/test_self_play_merge_contract.py,tests/unit/test_self_play_twin_contract.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_startup_failure_recovery.py,tests/unit/test_physical_ui_latency.py
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/session-full --tb=short'
./tools/test_fast.ps1 -Mode Balanced -Tests tests
.testvenv/Scripts/python.exe -X utf8 reports/reliability-fixes-20261012/session-gui-probe.py
```

Các lần probe `session-gui.log`, `session-gui-2.log`, `session-gui-3.log` thất bại do fixture của probe thiếu thuộc tính hoặc đợi ENDED trong khi loop đã chuyển IDLE. Giữ nguyên log thất bại; không tính là pass. Probe cuối xử lý đúng fixture và không cần thêm thay đổi production.

## Review và bàn giao

Review trực tiếp delta của vòng này: lock bao quanh cả quyết định và enqueue; job HTTP vẫn chạy ngoài lock; không chờ mạng trên GUI; thế hệ phiên ngăn failure cũ hủy phiên mới; các gate camera/readiness/motion hiện hữu vẫn được gọi. Test controller cũ bổ sung mock `ensure_match` để không gọi dịch vụ thật. Không phát hiện blocker trong phạm vi này.

`session-lifecycle-delta.patch` chỉ chứa thay đổi so với bản đã bàn giao trước vòng này, không phải toàn bộ diff bẩn với HEAD. Graph `detect_changes` trả 396 changed paths gồm thay đổi kế thừa và 0 impacted symbols; kết quả đó không chứng minh blast radius bằng 0. Consumers được xác minh trực tiếp: startup `main.py`, reset `GameState`, start/stop self-play và spectator client.

Manifest và kiểm tra hash bàn giao: `session-lifecycle-delivery-manifest.json`, `session-lifecycle-delivery-verification.json`. Các thay đổi chưa commit. Các log vòng trước vẫn mô tả snapshot tại thời điểm tương ứng.

## Chưa kiểm chứng

Camera/FR3 thật, latency khi thiết bị cùng hoạt động, độ khớp bàn/quân với ngoài đời và HTTP spectator thật đều **NOT RUN**. Test startup helper chạy production function trong isolation, không chứng minh toàn bộ GUI; probe Pygame kiểm tra riêng đường phím F8/F6 với thiết bị giả. Khả năng server thật chấp nhận FEN của ván đang dở sau khi mở lại phòng cần kiểm chứng trên dịch vụ; lỗi HTTP tiếp tục được log và không làm phát lại lệnh robot.
