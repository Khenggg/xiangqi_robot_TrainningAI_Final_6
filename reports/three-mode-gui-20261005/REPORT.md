# Kiểm tra 3 chế độ bằng Computer Use — 2026-10-05

## Kết luận

Đã chơi trực tiếp qua cửa sổ Pygame, mở viewer và quan sát chuyển động. Mỗi chế độ **10 lượt đơn (5 lượt mỗi bên)**, sau đó bấm SURRENDER. Không dùng camera hoặc FR3 thật. **Chưa đạt tiêu chí hoàn toàn không lỗi: live viewer bị giữ ảnh cũ và không kết nối lại được ở cuối robot–robot.**

| Chế độ | Lượt hoàn tất | Hành vi quan sát | Kết thúc |
|---|---:|---|---|
| Người–robot | 10 | Tay thực hiện 5 nước AI; có 3 lần ăn quân, game và viewer cập nhật. | Đầu hàng, AI thắng |
| Người–người | 10 | Các nước và lần ăn quân cập nhật; tay giữ góc khởi tạo, không tự gắp. | Đầu hàng |
| Robot–robot | 10 | Tay thực hiện cả hai bên, có 2 lần ăn quân. Game hoàn tất đủ lượt; viewer đã có chuyển động thật nhưng bị cũ ở cuối phiên. | Đầu hàng, BLACK WINS |

Không thấy xuyên bàn trong các khung hình đã quan sát. Đây không phải bằng chứng không va chạm trên mọi mẫu quỹ đạo và không xác nhận an toàn phần cứng.

## Mã và môi trường

- Repo chính: `D:/OJT/xiangqi_robot_TrainningAI_Final_6`, nhánh `feature/unified-robot-vs-robot`, HEAD `7d8c5de`; giữ các sửa đổi chưa commit có sẵn.
- Chạy bản nguồn hiện tại trong worktree `D:/OJT/_simple_launch_sync_20261005`.
- Lệnh chạy: `python main.py --viewer-port 8099 --telemetry-port 8899`, backend VIRTUAL, tốc độ 20%, Moonfish Medium.
- Điều khiển native: Computer Use/Sky, click quân và nút trên ảnh cửa sổ; browser qua CUA. Không bơm sự kiện Pygame hoặc gọi hàm đi cờ thay thao tác GUI.
- Viewer ban đầu dùng Node server 8100 để kiểm tra sửa loader, sau đó dùng Python ViewerServer 8099.
- Các phiên thử dừng bằng Ctrl+C tại session do agent tạo. Không dừng game/server người dùng trên 8088/8765.

## Nước đi đã xác nhận

### Người–robot

1. Đỏ e6–e5; 2. Đen h2–e2; 3. Đỏ b9–c7; 4. Đen e3–e4;
5. Đỏ h9–g7; 6. Đen e4×e5; 7. Đỏ g7–e6; 8. Đen e5×e6;
9. Đỏ h7–e7; 10. Đen e6×e7.

Có một thử đi e5×e4 bị từ chối đúng luật vì tự chiếu bởi pháo; không tính vào 10 lượt. Pose về SERVICE_SAFE ban đầu bị guard từ chối đường trực tiếp rồi phục hồi bằng lift-first; không tắt collision guard.

### Người–người

1. e6–e5; 2. e3–e4; 3. e5×e4; 4. b0–c2; 5. b9–c7;
6. h0–g2; 7. h9–g7; 8. i0–h0; 9. i9–h9; 10. c0–e2.

### Robot–robot

1. b9–c7; 2. h0–g2; 3. h7–g7; 4. b2–c2; 5. g7×g3;
6. c2×c6; 7. h9–g7; 8. b0–c2; 9. i9–h9; 10. a0–b0.

## Lỗi phát hiện và thay đổi

1. **Viewer không tải được thư viện Three.js từ CDN.** Hai lỗi `viewer.browser_error` khi khởi động. Request CDN thất bại SSL; chuyển importmap sang `/vendor/three/`, dùng bản đã cài trong node_modules. Python/Node server chỉ mở file JS thuộc build hoặc examples/jsm, kiểm tra đường dẫn đã resolve. Browser đã render và autoconnect với Python server sau sửa. Không thay collision geometry.
2. **Computer Use gửi F7/F11 không có hiệu lực trong cửa sổ thử.** Chuột vẫn hoạt động. Chưa kết luận lỗi bàn phím thuộc game hay công cụ. Thêm nút NƯỚC TIẾP cho tự đấu, gọi chính `request_next_move()`; đã dùng nút này hoàn tất 10 lượt. Cho phép SURRENDER tại ranh giới lượt hoàn tất; không hủy giữa motion worker. API end-match đã được bổ sung và review mã; chưa kiểm chứng API server bên ngoài.
3. **Thông báo người–người gây nhầm.** Trước sửa hiện thoáng “AI thinking” và kết thúc “AI WINS”. Sửa thành thông báo nhận nước và RED/BLACK WINS; surrender tính bên thắng đối diện bên đang tới lượt. Chưa chơi lại nguyên 10 lượt người–người trên bản sau chỉnh thông báo. Nhãn BLACK WINS đã được quan sát ở tự đấu.
4. **Trùng cổng khi phiên thử cũ chưa dừng hết.** Phiên `20261005_215323_927c288e` báo bind 8899 thất bại. Dừng đúng process do agent tạo rồi chạy lại. Không coi phiên khởi tạo lỗi này là ván đã thử.

## Lỗi còn lại cần sửa

**Live telemetry/viewer chưa ổn định.** Phiên tự đấu có 55 sự kiện cảnh báo `twin.fault / TWIN_UNAVAILABLE`, thường phục hồi sau đó. Sau lượt 10, log backend là IDLE/COMPLETE, game đã BLACK WINS, nhưng viewer vẫn GAME_MOVE với góc khớp cũ. Reload viewer vẫn “ĐANG KẾT NỐI…”. Observer WebSocket đọc độc lập cũng timeout ở opening handshake. Không xác minh được đồng bộ snapshot cuối tự đấu; không gọi toàn bộ thử nghiệm PASS.

Hướng điều tra: telemetry publisher/event loop, bridge đọc joint, các lock khi lấy snapshot world và đăng ký client. Chưa xác định nguyên nhân gốc. Không khắc phục bằng tăng timeout hoặc tắt freshness guard trong đợt thử này.

Dòng HUD X/Y/Z là điểm trên bàn/con trỏ từ `main.mjs`, không phải TCP live; việc số đó không đổi khi góc khớp đổi không phải bằng chứng tay đứng yên.

## Bằng chứng và kiểm tra bổ sung

- `20261005_212520_ecfa2bc7.log`: 5 sự kiện nước người và 5 `move.finished`, surrender.
- `20261005_215523_5fcc29f5.log`: 10 sự kiện nước người, không có chuyển động AI, surrender.
- `20261005_222451_e9b97abf.log`: engine chọn 10 nước, chuyển động theo các stage, cảnh báo telemetry.
- `hvr-10-viewer.png`, `hvh-10-viewer.png`: ảnh viewer hai chế độ đầu.
- `rvr-motion-4.png`: tay đang di chuyển trong tự đấu; `rvr-surrender.jpg`: game kết thúc sau 10 lượt.
- `rvr-10-viewer.png`: viewer giữ trạng thái GAME_MOVE sau khi game kết thúc; `rvr-reconnect.png`: chờ kết nối sau reload.
- `telemetry.jsonl`: bản ghi đọc thụ động của phần phiên đầu; **không phải** capture đầy đủ ba chế độ. Lần đọc thêm ở tự đấu timeout, không có dữ liệu mới đáng tin từ lần đó.
- `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_simple_launch_sync.py,tests/unit/test_self_play_twin_contract.py -ParallelOnly`: **22 qua, exit 0**, có test tài nguyên Three.js nội bộ và từ chối traversal/package.json.
- `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_offline_mouse_confirmation.py -ParallelOnly`: **5 qua, exit 0**.
- Lần gọi test trước đó exit 1 vì quyền thư mục pytest Temp và đường dẫn test cũ; chạy lại dùng basetemp trong worktree, không sửa production để né lỗi test.
- Review Luna phát hiện thiếu API end-match khi surrender tự đấu; đã bổ sung. `git diff --check`: exit 0 ở worktree.

Theo dõi 06/10: đã sửa transport/ordering và kiểm tra lại tự đấu đủ 10 lượt, hai captures, surrender, reload/reconnect về IDLE. Chi tiết và giới hạn: [báo cáo sửa telemetry](../telemetry-fix-20261006/REPORT.md). Kết quả lỗi ở trên là bằng chứng lịch sử, không sửa lại thành pass.
