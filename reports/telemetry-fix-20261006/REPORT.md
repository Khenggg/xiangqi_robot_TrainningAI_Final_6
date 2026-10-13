# Sửa telemetry/viewer — 06/10/2026

## Phạm vi

Sửa trên repo chính, chạy bản sao thay đổi trong worktree `D:/OJT/_simple_launch_sync_20261005`, baseline HEAD `7d8c5de`. Chỉ VIRTUAL; không kết nối/điều khiển phần cứng.

## Nguyên nhân và bằng chứng

1. `TelemetryPublisher._run_server`: gọi callback đồng bộ ngay trong asyncio event loop. Test dùng callback chờ Event tái hiện viewer thứ hai timeout opening handshake trước sửa (exit 1), kết nối và nhận snapshot được sau sửa. Đây là lỗi tái hiện chắc chắn; chưa có stack của phiên GUI cũ chứng minh chính callback đó gây lần treo cũ.
2. Broadcast tạo `run_coroutine_threadsafe(client.send(...))` cho mỗi cập nhật và mỗi client, không giới hạn số tác vụ đang chờ. Runtime, bridge và heartbeat cùng phát world_state lớn. Phiên sửa bước đầu `20261006_012216_caf7c5a2` vẫn treo sau 3 lượt; observer báo keepalive ping timeout. Stack phiên chẩn đoán ghi nhận server trong `permessage_deflate.encode`, producer liên tục lập lịch send. Không kết luận một mẫu stack chứng minh deadlock; kết hợp bằng chứng mạng và kiến trúc hàng đợi để sửa cơ chế tích tụ.
3. `LiveTwinBridge.sync_robot_state` nhận snapshot trước khi chờ physics lock nhưng kiểm tra tuổi sau khi chờ. Planning có thể giữ shared world lâu, gây cảnh báo stale giả cho borrowed virtual world. Bỏ snapshot bị trễ thay vì phát lỗi/ghi đè execution mới. Backend publisher từ chối snapshot timestamp cũ hơn trạng thái đã nhận.

## Thay đổi

- Xử lý callback bằng `asyncio.to_thread`, có shared asyncio Lock giữ thứ tự dispatch giữa các client. Không sửa operation ownership/collision guard.
- Gộp robot/world snapshot mới nhất trước khi gửi; một writer cho mỗi client, giới hạn 25 Hz và timeout send 2 giây. Tắt nén WebSocket tại localhost để tránh nén lặp snapshot lớn trong luồng mạng.
- Giới hạn custom events 64; nếu tràn hoặc viewer gửi quá chậm, đóng 1013 để người dùng reconnect, không âm thầm duy trì lịch sử thiếu.
- Cache operation_state và replay cùng robot, placement, world khi reconnect.
- Không nới freshness threshold của robot thật. Test riêng chứng minh nhánh physical vẫn báo lỗi khi snapshot quá hạn.

## Kiểm chứng mã

- Bộ telemetry/FR3/twin/self-play: 21 passed, exit 0 tại bước transport; sau đó bổ sung test slow-viewer/overflow.
- Bộ `test_telemetry_liveness.py` cuối: 6 passed, exit 0. Bao gồm blocked callback + serialized dispatch, snapshot không quay ngược, physics lock delay virtual/physical, slow client nhận latest snapshot, event overflow disconnect.
- Review Luna phát hiện hai điểm: callback giữa client cần serialize; overflow cần đóng client. Đã sửa cả hai.

## Kiểm tra GUI

Phiên cuối: `20261006_013940_4599664e`, lệnh `python main.py --viewer-port 8099 --telemetry-port 8899` trong worktree. Dùng chuột Computer Use chọn ROBOT VS ROBOT / Medium / NƯỚC TIẾP. Browser IAB và một observer WebSocket độc lập cùng theo dõi.

Đã hoàn tất **10 lượt tổng cộng (5 mỗi bên)** và dùng chuột surrender: GUI hiện BLACK WINS / Self-play match ended.

| Lượt | Nước đi trên GUI | Kết quả |
|---|---|---|
| 1 | Mã đỏ b9 → c7 | Hoàn tất |
| 2 | Mã đen h0 → g2 | Hoàn tất |
| 3 | Pháo đỏ h7 → g7 | Hoàn tất |
| 4 | Pháo đen b2 → c2 | Hoàn tất |
| 5 | Pháo đỏ g7 × g3 | Ăn tốt đen |
| 6 | Pháo đen c2 × c6 | Ăn tốt đỏ |
| 7 | Mã đỏ h9 → g7 | Hoàn tất |
| 8 | Mã đen b0 → c2 | Hoàn tất |
| 9 | Xe đỏ i9 → h9 | Hoàn tất |
| 10 | Xe đen a0 → b0 | Hoàn tất |

- Log phiên cuối: **0 twin.fault, 0 ERROR/CRITICAL**, errors.log rỗng. Observer độc lập ghi nhận hàng trăm mẫu MOVING; viewer được quan sát ở các giai đoạn gắp, mang, đặt và retreat. Không thấy treo kênh như lần trước.
- Đối chiếu identity + ô của **toàn bộ 30 quân còn lại** từ telemetry cuối với 10 nước GUI: khớp, tất cả RESTING. Hai quân bị ăn: black_pawn_3 và red_pawn_1. Đây là trạng thái sau commit/reconciliation, không dùng sai số cuối bằng 0 để chứng minh độ chính xác gắp vật lý.
- Sau surrender, backend và viewer đều IDLE, stage COMPLETE, joint `[0,-70,60,-80,-90,0]`, không lỗi. Reload browser tự kết nối lại thành công, không giữ GAME_MOVE/pose cũ.
- Các probe kết nối mới đọc robot/world/operation_state trong khoảng 0,41–0,64 giây; probe sau surrender 0,532 giây, nhận IDLE và 30 quân. Probe giữa lượt 6 nhận operation_state GAME_MOVE dù motion_state của một stage là IDLE: hai trường này có ý nghĩa khác nhau.
- SHA256 ba file production/test ở main và worktree trùng nhau. Lần GUI này kiểm tra lại chế độ gây treo ROBOT VS ROBOT; hai chế độ còn lại có bằng chứng ở báo cáo ngày 05/10, chưa chạy lại sau sửa transport.

Bằng chứng: `final-run.log`, `final-events.jsonl`, `final-errors.log`, `evidence-summary.json`, `reconnects.jsonl`, `game-surrender.jpg`, `viewer-moving.png`, `viewer-final-reconnected.png`. `telemetry-after.jsonl` có phần đầu từ một phiên chẩn đoán; script `summarize_evidence.py` lọc robot/world theo timestamp của phiên cuối. Số packet custom events trong summary có thể gồm replay đầu phiên cũ; không dùng làm số lần thực thi nước đi.

Lệnh kiểm tra cuối: `python reports/telemetry-fix-20261006/reconnect_probe.py` và `python reports/telemetry-fix-20261006/summarize_evidence.py` (main repo), exit 0. Observer chỉ đọc, không gửi lệnh điều khiển. Các test chạy qua `tools/test_fast.ps1 -Workers 2 -Tests ... -ParallelOnly` với basetemp riêng trong worktree.

Sau khi thu bằng chứng, đã chủ động dừng game/observer kiểm thử bằng Ctrl+C (process exit 1 do thao tác dừng, không tính là test failure) và đóng tab IAB 8099 do agent tạo. Các log `final-*` được chụp trước thao tác dừng. Phiên người dùng trên 8088 không được restart trong lượt sửa này.

Hai phiên `diagnose_live.py` có periodic faulthandler kết thúc bất thường; không tính là pass và chưa xác định nguyên nhân kết thúc. Phiên cuối chạy entrypoint bình thường, không thêm diagnostic wrapper.

## Giới hạn

Không chứng minh an toàn phần cứng hoặc toàn bộ quỹ đạo từ ảnh chụp. Không dùng kết quả bộ unit nhỏ này để tuyên bố toàn repo đã hết lỗi. Canceled to_thread không hủy callback đang chạy: các runtime operation vẫn phải hoàn tất/được dừng qua cơ chế runtime hiện có.
