# Rollback vật lý cycle gần nhất

Z chỉ mở sau một cycle Đỏ–Đen đã có proof toàn bàn, arm nghỉ và baseline mới.
Mỗi cycle chỉ dùng được một lần. Một nước Đỏ mới thu hồi quyền cycle cũ.
Emergency/test không tạo cycle rollback hợp lệ; trận kết thúc không rollback.

Arm trả quân Đỏ còn sống trước, Đen sau. Nếu Đen chặn ô cũ Đỏ thì đổi thứ tự.
Nếu Đen đã ăn quân Đỏ vừa đi, arm chỉ trả Đen; người chơi đặt lại Đỏ ở ô nguồn.
Quân bị ăn được liệt kê chính xác màu/loại/ô, người chơi tự lấy từ bãi ăn.
Không có thao tác gắp từ bãi ăn, ô đệm hay redo trong phiên bản này.

Trong khi rollback, board/FEN chính giữ S2; coordinator có checkpoint riêng.
Chỉ toàn bàn S0 đúng mới commit một lần, khôi phục history/captured inventories
và tăng epoch/revision. Audit giữ hai nước cũ với dấu đã hoàn tác. Baseline
S0 thành công mới mở chơi; lỗi baseline không chạy lại arm/commit/FEN event.

## Thao tác và recovery

- **Z:** bắt đầu khi nút được mở.
- **SPACE/V/Continue:** quét lại và tiếp tục tại checkpoint đã xác minh.
- **E:** chỉ nhấn sau khi operator đã đưa arm về pose nghỉ an toàn và kiểm tra
  kẹp thực sự rỗng. Đây là xác nhận cho lần phục hồi hiện tại. Phần mềm vẫn
  đọc lại controller, TCP/tool/user, safety, DO và camera; phím không bypass proof.
- **X:** hủy chỉ khi toàn bàn đã được phục hồi đúng S2 và arm an toàn.
- **A:** xác nhận kẹp rỗng và yêu cầu verified-abort tại S2 sau lỗi chưa rõ.
- Sau commit S0 không hủy về S2; chỉ hoàn tất baseline và đồng bộ dữ liệu.

Mất ACK hoặc lỗi 112 không cho phép tự phát lại lệnh. Chỉ operator resume với
proof an toàn/kẹp rỗng và toàn bàn mới xác định bước đã chạy hay chưa. Nếu không
khớp checkpoint nào, phục hồi bàn bằng tay theo chỉ dẫn trước khi tiếp tục.
Không tự mở kẹp hoặc gắp lại khi chưa biết đang giữ quân gì.

Journal mặc định `logs/rollback-journal.json`, đổi đường dẫn qua
`XIANGQI_ROLLBACK_JOURNAL_PATH`. Nó tách khỏi `simulation-outbox.json`, gắn account
scope và room. Giữ journal khi lỗi; file hỏng/khác account khóa recovery.
Restart tải đúng committed snapshot và kết nối robot chỉ đọc, không enable,
đổi mode, mở kẹp, homing hoặc chạy motion tự động. Khi transaction dở, đóng app
không tự kết thúc room và không phát lệnh cleanup vào gripper/controller.
Nếu thoát bình thường khi không có transaction dở, session được đánh dấu đóng
trước yêu cầu end-room; lần mở sau không phục hồi quyền Z/room đã đóng. Audit
được giữ, còn move feed của game mới bắt đầu lại.

S0 được lưu cùng commit ID và FEN chờ enqueue. Nếu chưa ghi được durable outbox,
game giữ khóa để FEN cũ không ghi đè nước mới; retry dữ liệu không chạy arm.
Outbox dùng một worker tuần tự: request S2 đang chạy hoàn tất trước S0.
Lỗi/rejection từ server hiện riêng trên status; không thay local S0 đã verified.
DRY_RUN không gửi FEN rollback tới provider.

## Proof và giới hạn nghiệm thu

Proof cần ít nhất ba frame raw mới liên tiếp qua ít nhất một giây, 90 ô có
confidence **lớn hơn 0.7** (cấu hình `ROLLBACK_LAYOUT_MIN_CONFIDENCE=0.7`) và occupancy
theo chế độ đang chọn: PvP dùng điểm chân bbox/homography; height/ring dùng
piece-height geometry. Proof toàn bàn xác nhận đúng quân/đúng ô, không bắt mọi
quân không tham gia hoàn tác phải có tâm trong giới hạn gắp. Ngay trước từng
transfer, quân nguồn vẫn phải có target đo mới đủ an toàn; không fallback về tâm
ô logic. Unknown, sai loại/màu, thêm quân, confidence thấp hoặc geometry lỗi vẫn
chặn proof. Cảnh báo `low_confidence` độc lập với độ lệch tâm, không được bỏ qua.

Idle/DO LOW không chứng minh kẹp rỗng. Recovery dùng TCP thực tại HOMECHESS hoặc
IDLE được commissioning rõ ràng; dung sai mặc định 2 mm/2 độ, không tự đoán pose.
Chưa có cảm biến jaw hoặc producer phát hiện tay được commissioning; operator
phải rút tay trước khi xác nhận. Camera chỉ phân biệt màu/loại/ô, không chứng
minh ID vật lý giữa hai quân giống hệt nhau.

Test offline/mock không chứng minh camera/controller/gripper thật hoặc server
chấp nhận FEN đi ngược. Cần nghiệm thu phần cứng và provider trước khi kết luận
toàn bộ chức năng vận hành thật. Checklist 44 case nằm trong plan; bằng chứng
offline và giới hạn từng nhóm được ghi ở `verification.md` cạnh plan.
