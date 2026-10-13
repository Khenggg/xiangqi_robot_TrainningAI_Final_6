# Tích hợp visual v2 — 09/10/2026

## Nguồn và lựa chọn

- Nguồn visual: `fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09`.
- Target: `feature/unified-robot-vs-robot`, HEAD `7d8c5de`, cộng source chưa commit được giữ trong snapshot `da703237561c5264d96886514852bd958e613409`.
- Chủ dự án đã chọn **C01–C10 = A**. Ghép chọn lọc trong `D:/OJT/_visual_integrate_20261009`; không merge nguyên file legacy hoặc chép calibration camera 0 sang runtime.
- Hướng dẫn hiện hành: [VISUAL_V2_INTEGRATION.md](../../docs/VISUAL_V2_INTEGRATION.md).

## Thay đổi

1. Module geometry, consensus, height, ring, debug và wizard camera mới; camera index và resolution giữ theo target. Không nhập intrinsics/sample của donor; kích thước chưa đo để `None`, modes mới mặc định tắt.
2. Adapter đo tâm ghép vào manager hiện tại, giữ strict center, không fallback foot/logical. Khởi tạo occupancy cả khi chỉ bật ring/height/top-face. Vùng ngoài lưới mặc định 0 mm; khả năng mở tới 10 mm đòi hỏi kích thước đã đo.
3. Adapter motion dùng typed result, cùng identity/epoch/expected board cho cả hai màu. Verify toàn bàn trước và sau; capture checkpoint chỉ ghi sau khi ô đích và toàn bàn chỉ thiếu quân bị ăn được xác nhận. Retry từ checkpoint không bỏ quân bị ăn lần hai.
4. Physical manager từ chối target thiếu/nonfinite và thiếu callback capture trước khi gọi robot. SDK 112 giữ failure, không đi tiếp/kẹp. Consensus là precondition failure riêng, không phải lỗi SDK có thể retry.
5. Worker physical một job; chặn input gây tranh quyền; cleanup không giải phóng camera/controller dưới worker còn chạy. Retry và checkpoint được xóa khi New Game, clear-pending, đối soát, rollback, undo hoặc commit.
6. T/H/Y và nút hover/đo lại. Test gắp giữ identity riêng và không đổi FEN; hover virtual dùng R1–R4 hiện tại/resolver/backend guard, không kẹp. Giữ resize/fullscreen và mapping chuột.
7. Setup Windows dùng dependency chung có PyBullet/WebSocket, RUN và calibration launchers cùng ưu tiên `.venv312`. Tham số donor chỉ lưu thành profile ứng viên không được runtime tự đọc.

Không đổi các file collision geometry, simulator runtime, R1–R4 provider, viewer hoặc telemetry trong patch mới này. Đã kiểm tra các luồng đó qua manager/UI mới. Các đổi source có trước vẫn được giữ.

## Bằng chứng thực thi

Python kiểm tra: `C:/Users/Ken/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`, **3.11.15**; không dùng FR3/camera thật hoặc API website. Các bài physical dùng SDK/camera mocks.

| Lần chạy | Kết quả | Phạm vi |
|---|---|---|
| Build `python -m compileall -q src main.py config.py` | exit 0 | Cú pháp/import tĩnh, không hardware |
| Full unit lần đầu, `test_fast.ps1 -Workers 2 -Tests tests/unit -ParallelOnly` | 705 passed, 3 failed; exit 1 | Phát hiện thiếu None kwargs virtual, fixture không có config, epoch đổi bị phân loại ENDED thay FAULTED; đã sửa |
| Full runner lần hai, `test_fast.ps1 -Workers 4` | **727 parallel + 8 serial passed, exit 0**, 732,81 s | Slow/hardware excluded. Worker đã import source trước các điều chỉnh guard/clear-request cuối; không mô tả đây là full run toàn bộ source cuối |
| Closing gate, `test_fast.ps1 -Workers 2 -Tests <21 file được giữ trong closure.log> -ParallelOnly` | **236 passed, exit 0**, 25,84 s | Source cuối: manager/typed SDK result, center/ring hai màu, retry capture, recovery, camera acquisition, PyBullet hover, launcher/profile/telemetry và các tests optics đã chuyển hợp đồng |
| Donor test migration trên 5 file optics/adapter | 72 passed, exit 0 | Cũng nằm trong closing gate; không cộng hai số làm số test độc lập |
| Calibration scripts `--help` | exit 0 | Không mở camera; không kiểm chứng quang học/cài mới Windows |
| `git diff --check` | exit 0 | Patch không có lỗi whitespace |

Lệnh và output đầy đủ: `full-unit-initial.log`, `full-unit-final.log`, `closure.log`, `system-raw.log`; các lần thất bại trung gian vẫn giữ trong log. Runner dùng `PYTEST_ADDOPTS` với basetemp riêng và confcutdir tại worktree. `closure.log` ghi danh sách 21 file, marker, số worker và các cảnh báo deprecation.

### Ba chế độ, mỗi chế độ 10 lượt đơn rồi đầu hàng

Chạy lại opening fixtures qua **InputHandler và SelfPlayController cùng PyBullet thật**, engine là fixture các nước đã ghi; không phải Computer Use click Pygame và không đánh giá chất lượng engine.

| Chế độ | Lượt | Ăn quân | Motion robot | Kết thúc |
|---|---:|---:|---:|---|
| Người–robot | 10 | 3 | 5 | Đầu hàng |
| Người–người | 10 | 1 | 0; joints giữ nguyên | Đầu hàng |
| Robot–robot | 10 | 2 | 10 | Đầu hàng |

`system.json` có từng FEN, joint pose, identity và số đo. Với 15 motion robot, vị trí body được đọc **ngay sau executor, trước commit FEN/reconcile**: sai lệch XY lớn nhất 0,163052 mm ở người–robot và 0,172885 mm ở robot–robot. Quân bị ăn đã ra khỏi lưới; không còn payload gắn trên kẹp sau đặt. Sau commit, toàn bộ active identities/cells khớp. Sai lệch 0 trong lần probe cũ chỉ là sau reconcile; lưu riêng `system-after-reconcile.json`, không dùng để chứng minh landing.

Lần system đầu hoàn tất các ván nhưng harness cleanup exit 1 vì engine fixture thiếu `local_engine`; đã sửa fixture và chạy lại toàn bộ với số đo trước commit. Không sửa production để né lỗi này.

Hover PyBullet sau xoay 3° và dịch 10 mm qua R1–R4: approach XY theo placement mới, quân/FEN không đổi; collision guard tắt thì từ chối và giữ joints. Test manual GUI gắp/thả hiện có cũng đọc settle trước reconcile trên bàn đã đổi pose.

### Viewer và GUI

- Computer Use mở browser của server riêng **8097/8897**; badge SIMULATION, IDLE, board/pieces/robot render. Reload tự kết nối về 8897, không lỗi browser được ghi nhận; không điều khiển server người dùng 8088/8765.
- Trạng thái OFFLINE ban đầu được quan sát lúc asset loader chưa xong và khi nút Connect live đóng socket đang mở; sau reconnect/reload xác nhận SIMULATION/IDLE. Không coi các ảnh intermediate này là lỗi telemetry.
- `gui-controls.png` là **render headless Pygame**, để kiểm tra bố cục nút T/H/Y; không phải ảnh native desktop. Browser screenshot đã quan sát trong phiên công cụ, không được lưu thành file report.
- Không quan sát bằng mắt mọi mẫu quỹ đạo; đây không phải chứng nhận không va chạm trên mọi pose/scene.

## Chuyển hợp đồng test

Giữ toàn bộ test optics/geometry/consensus. Các harness legacy dùng direct SDK, `require_visual_target` hoặc mong exception thay typed result đã được chuyển:

- `GuardedMotionTests` donor: 5 methods thay bằng 2 typed-boundary tests. Điều kiện source thiếu/nonfinite, capture callbacks và SDK stop được kiểm tra tại manager/executor trong `test_visual_v2_adapter.py`.
- Hai direct-coordinator tests của ring được thay bằng cases center/ring riêng cho cả đỏ/đen và capture retry/no-commit trong adapter suite. Ring-specific routing/fail-closed/init và optical tests vẫn giữ.
- Camera mocks có lock/stop state đầy đủ; diagnostic test qua `update_display`. Khác biệt public fail-closed exception được phản ánh trong fixture, không đổi production thành fallback để test xanh.

Luna review độc lập nhiều lượt: tìm lỗi reset còn request cũ, đã sửa; review cuối guard/coordinator/state-clear/shutdown không thấy blocker. Review là static; kết quả chạy ở trên do root kiểm chứng.

## Đưa về repo chính

`export-manifest.json` ghi SHA256 từng file. Trước copy phải đối chiếu main với snapshot cho mọi file cũ, từ chối nếu đã có chỉnh sửa mới; file mới có nội dung khác cũng từ chối. Sau copy đối chiếu hash main/worktree và giữ nguyên HEAD/index. Báo cáo copy cuối nằm trong `export-result.json`. Không tự commit, push hoặc tạo merge commit.

## Giới hạn còn lại

- Camera thật, intrinsics thực, ngưỡng nhận dạng, chiều cao quân, sai số R1–R4 và hướng TCP/gripper thực chưa được kiểm chứng tại máy này. Chế độ mới vẫn opt-in; profile donor không phải phép đo của hệ thống này.
- Không có chứng nhận hardware collision planner; giữ các quyền commissioning/actuation hiện tại. Không suy độ chính xác robot từ số sai lệch PyBullet.
- Fresh install Python 3.12/Windows, long soak và CI remote chưa chạy. Script setup/CLI/import được kiểm tra trên môi trường đang có; không tự cài hoặc điều khiển phần cứng.
