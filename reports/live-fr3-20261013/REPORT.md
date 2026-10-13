# Kiểm tra kết nối FR3 thật — 13/10/2026

## Đã kiểm chứng bằng lệnh đọc

- Controller phản hồi GetControllerIP: 192.168.58.2.
- GetSoftwareVersion: FR3-V1-001(V6.0), v3.8.5.1, V3.8.25-QX.
- Backend read-only kết nối thành công. Ba mẫu đều joints_valid=True, tcp_valid=True, IDLE, không có telemetry_error/last_error.
- Pose cuối TCP/flange controller x≈-104.282, y≈149.626, z≈348.136 mm; góc ≈[179.848,0.545,-42.002] độ. Đây là tọa độ controller, không phải số đo so với sàn thực tế.
- Chỉ gọi connect/state/getter/disconnect và RPC đọc/maths. Không enable, MoveJ/MoveL, HOME, reset, gripper hoặc ghi tool/user frame.

## Chênh lệch quan sát

Từ cùng khớp đo được, FR3Kinematics/URDF cho flange [-103.398,149.195,448.135] mm. Controller GetForwardKin trả [-104.282,149.626,348.136] mm, khớp telemetry. Delta URDF − controller ≈[0.884,-0.432,99.999] mm, norm≈100.004 mm. Góc gần khớp. GetTCPOffset và GetWObjOffset đang trả sáu số 0.

Đây là chênh lệch tại một cấu hình khớp, chưa chứng minh nguyên nhân là geometry hay gốc base frame. Không áp dụng offset -100 mm hoặc sửa model theo một mẫu. Cần xác minh frame và thêm các cấu hình đo trước khi tuyên bố parity vị trí. Các getter GetToolCoordWithID/GetWObjCoordWithID không được firmware này cung cấp (RPC fault -506); không ghi cấu hình để thử khắc phục.

## GUI và phần chưa chạy

Đã mở main.py --physical ở repo chính, PID lưu trong game.pid. Giao diện Home hiện bình thường. Hai lần Computer Use press Return bị chặn với `user input was detected in this window; call get_window_state before continuing`, nên chưa kích hoạt VS ROBOT/startup camera. Đã hỏi người dùng để yên input hoặc tự bấm VS ROBOT.

perspective.npy vẫn giữ SHA256 6B6B021D688092EB2062ED9684F9437249FDDEB4481C86BE3308653F9DE899B8. Chưa duyệt hoặc ghi calibration mới. Camera, viewer/WebSocket, FEN và ba chế độ chơi/gắp vật lý đều chưa được kiểm chứng trong lượt này. Không bật F9/F10 hoặc nhận quyền chuyển động từ việc chỉ kết nối.

Bản sửa recovery còn ở worktree _reliability_fix_20261012; 249 tests liên quan đạt nhưng chưa copy về repo chính. Phiên GUI đang dùng snapshot repo chính trước bản sửa đó.

## Evidence

read-only-state.json, flange-comparison.json, controller-fk.json, frame-offsets.json, startup.stdout.log/startup.stderr.log và logs/20261013_095626_3e2c3631/.

Lưu ý: Get-NetAdapter vẫn báo Ethernet Disconnected dù TCP/RPC trả lời hợp lệ. Chưa xác định đường truyền thực tế; dùng phản hồi controller và packet hợp lệ làm bằng chứng kết nối, không thay đổi cấu hình mạng.
