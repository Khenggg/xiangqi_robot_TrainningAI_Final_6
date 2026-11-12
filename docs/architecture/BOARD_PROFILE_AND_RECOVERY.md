# Profile R1–R4 và khôi phục game

Phạm vi: vị trí bàn **mô phỏng**, game và thông báo recovery. Profile không thay calibration camera/robot thật và không cấp quyền chuyển động.

## Lưu vị trí

1. Trong viewer: Connect live với backend mô phỏng, mở **Vị Trí**.
2. **Lấy 4 điểm từ bàn mô phỏng**, sửa XYZ theo `robot_base`, đơn vị mm.
3. Tab **Service → Chuẩn Bị Dời Bàn**. Chờ SERVICE_SAFE.
4. Trở lại **Vị Trí → Áp dụng R1–R4**. Chỉ tiếp tục khi backend chấp nhận.
5. **Lưu vị trí đã áp dụng**. Lưu hình học đang có hiệu lực, không lưu các ô chưa áp dụng.

Một profile hiện hành được lưu tại `data/simulation_board_profile.json`, ngoài Git. Lần lưu thành công tiếp theo thay thế profile trước bằng ghi file tạm và atomic replace. Lỗi ghi không xóa profile cũ.

Record gồm schema version, calibration/placement version lúc lưu, thời điểm, nguồn giả lập, frame, đơn vị, bốn điểm, checksum cấu hình scene và chiều cao di chuyển. Không dùng như bằng chứng đo vật lý.

## Nạp sau khi khởi động lại

Không tự dời bàn hoặc đưa tay về service khi khởi động. Connect live → **Lấy 4 điểm từ bàn mô phỏng** để lấy phiên bản hiện tại → **Service / Chuẩn Bị Dời Bàn** → **Khôi phục profile đã lưu**.

Nạp lại qua chính pipeline áp dụng R1–R4: fit hình học, kiểm tra phiên bản, robot đứng yên, không giữ quân, quân đã đứng yên, SERVICE_SAFE và va chạm trên toàn đường dời bàn. Thành công cập nhật cùng placement cho world, provider, backend và twin; placement version tăng mới, không dùng lại số phiên bản cũ trong file.

Thiếu file, JSON hỏng, sai nguồn/frame/đơn vị/schema, cấu hình scene hay H đã đổi: từ chối và giữ nguyên bàn. Khi file bị hỏng, nhập lại bốn điểm và lưu lại. Sau khi nạp vẫn cần kiểm tra đường đi; profile không lưu trạng thái “đã kiểm định”.

## Khi game bị khóa

Panel trái thay lịch sử nước đi bằng:

- Bước cần làm.
- Lý do dừng, nước đang chờ và trạng thái thực thi.
- Lỗi dài được giới hạn trong panel; xem log phiên chơi để lấy chi tiết.

Với camera/robot thật: **V** đối soát; **F4** quét toàn bàn nếu thế cờ khác; **1 / 2** xác nhận lượt khi được yêu cầu. Các nút này sử dụng gate hiện có, không tự xóa lỗi hoặc phát lại lệnh gắp. Với mô phỏng: sửa nguyên nhân backend rồi **NEW GAME** để đồng bộ lại. Sau test gắp/thả, nếu đã dời quân thì khôi phục thế khởi đầu trước NEW GAME. Kích hoạt robot thật vẫn là thao tác riêng.

## Phần cần xác minh ở công ty

Luồng đã được kiểm tra bằng executor/camera mock với GameState, PyBullet và telemetry thật: nước thường, ăn quân, camera hậu kiểm không xác nhận, và chặn thực thi lại khi fault còn giữ. Đây chưa phải kiểm chứng phần cứng.

Khi có setup thật và yêu cầu chạy phần cứng riêng:

1. Kiểm tra camera/calibration và telemetry chỉ đọc, xác minh bàn đang đứng yên và đủ trạng thái trước lượt.
2. Commission có giám sát với một nước thường: thu ảnh trước/sau, kết quả backend, FEN, identity quân và telemetry viewer.
3. Kiểm tra một nước ăn quân: quân bị ăn biến mất trong simulation và quân đi giữ đúng identity/ô đích. Dừng nếu camera không xác nhận toàn bàn, lệnh backend bị từ chối hoặc trạng thái twin không nhất quán.

Không suy ra độ an toàn robot thật từ test mô phỏng; ngưỡng và quyền kích hoạt phần cứng giữ theo calibration/commissioning hiện có.

## Bằng chứng kiểm chứng 2026-10-05

- Worktree thực thi: `D:/OJT/_simple_launch_sync_20261005`.
- `tools/test_fast.ps1 -Workers 4`: 701 ca parallel + 8 ca serial qua, exit 0, 713 giây. Không chạy hardware tests hay ca mang marker slow.
- Gate subsystem: 70 qua. Sau chỉnh hướng dẫn UI và chặn profile trong PHYSICAL: 35 ca liên quan qua; `node --check robot-3d-viewer/main.mjs` exit 0. Node placement integrity và single motion authority qua.
- Browser thật qua CUA, HTTP 8098 / WS 8898 trong worktree: dịch X +10 mm → áp dụng version 2 → lưu → reset version 3 → nạp bản stale bị từ chối → làm mới version nhưng chưa SERVICE_SAFE vẫn bị từ chối → chuẩn bị lại → nạp thành công version 4; UI XYZ đúng profile.
- GUI recovery render được kiểm tra bằng ảnh: hướng dẫn, nguyên nhân và nước chờ nằm trong panel. Không tự gỡ khóa. Luna rà soát độc lập; đã sửa câu mô tả test có thể gây hiểu nhầm.
- `reports/profile-recovery-20261005/` có log/exit codes, ảnh viewer và recovery, profile lưu qua browser, SHA256 tám file đối chiếu main/worktree. Server thử đã đóng, không đụng phiên đang mở của người dùng.
- Graph `detect_changes` trả danh sách gồm lịch sử cũ và không có impacted symbols; không dùng nó để khẳng định phạm vi ảnh hưởng. Đối chiếu diff, trace và gate thực thi nêu trên.
- Chưa kiểm chứng camera/FR3 thật, chưa tuyên bố toàn bộ quỹ đạo hoặc độ an toàn vật lý. Thay đổi hiện ở repo chính, chưa commit/push.
