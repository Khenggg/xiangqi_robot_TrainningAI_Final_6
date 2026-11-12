# Kiểm tra luồng người dùng — 2026-10-19

## Kết luận

Các luồng chính dưới đây đã chạy thành công trong môi trường virtual cô lập,
và các bản sửa đã được áp dụng về working tree chính. **Chưa đủ bằng chứng
để kết luận toàn dự án sạch lỗi hoặc đạt nghiệm thu với phần cứng thật.**

Yêu cầu kiểm tra theo luồng thực tế lần này thay thế giới hạn chỉ đọc code trước đó.
Không mở camera hoặc gửi lệnh tới FR3 thật. Không thay đổi dữ liệu phiên của repo chính.

## Cách kiểm tra

- Snapshot của HEAD `18e67fc9006a91a2a32c4c861974760089a687de` cùng các thay đổi
  chưa commit được chạy tại `D:/OJT/_qa_userflow_20261019`.
- Chạy nguyên `main.py`, AI Moonfish thật và executor PyBullet thật. Driver gửi
  sự kiện chuột/phím qua vòng lặp Pygame; không gọi trực tiếp hàm commit để đi quân.
- Pygame dùng màn hình ảo SDL; viewer chạy trên Chrome headless có profile riêng.
  Không điều khiển chuột/bàn phím desktop. Đây không phải máy ảo Windows đầy đủ.
- Driver kiểm tra FEN, ID quân, revision và các ô quân từ telemetry sau mỗi nước
  ổn định; đồng thời lưu ảnh GUI và ảnh viewer WebGL.
- Spectator token được để trống; chưa kiểm chứng API ngoài bằng tài khoản thật.

## Kết quả luồng thực thi cuối

Mỗi lượt bên dưới là một lần một bên di chuyển quân (ply).

| Chế độ | Số lượt | Game và world khớp | Đầu hàng | New Game và về menu |
|---|---:|---|---|---|
| Người vs Người | 10 | Đạt, có 2 quân bị ăn | Đạt | Đạt, phục hồi 32 quân |
| Người vs Robot | 10 | Đạt, có quân bị ăn | Đạt | Đạt, phục hồi 32 quân |
| Robot vs Robot | 10 | Đạt | Đạt ngay tại lượt 10 | Đạt, phục hồi 32 quân |

Chrome nhận 146 / 1290 / 1964 gói robot và 139 / 1197 / 1854 gói world tương ứng.
Hai chế độ có executor ghi nhận ít nhất 100 tư thế khớp khác nhau, cả đóng/mở kẹp
và trạng thái quân attached. Người vs Người giữ cánh tay đứng yên. Không có
exception JavaScript chưa xử lý trong lượt cuối; đã lưu 9 ảnh viewer.

Robot vs Robot chưa có nước ăn quân trong 10 lượt thực thi cuối này. Kiểm tra
10 lượt/2 captures của cả ba chế độ cũng đạt trong suite tích hợp riêng, nhưng
suite đó mock chuyển động cánh tay; không dùng nó làm bằng chứng quỹ đạo gắp thật.

Một luồng gắp thử qua GUI cũng đã chạy: chọn T → chọn quân → chọn ô trống →
gắp/thả → New Game. FEN của ván giữ nguyên, ID trên bàn test thay đổi đúng và
reset trở về 32 quân. Khoảng cách lớn nhất giữa hai lần xử lý sự kiện trong
giai đoạn chờ gắp của lần cuối là 141 ms. Đây là mẫu đo một lần, không phải
cam kết FPS/p95 cho toàn ứng dụng hay phần cứng thật.

## Những lỗi đã sửa trong lượt QA này

1. Phiên đã đóng an toàn/kết thúc vẫn bị nạp thành recovery khi chọn chế độ khác.
   Chỉ tạo phiên mới nếu phiên cũ đã kết thúc sạch, không còn transaction hoặc
   cờ recovery; giữ outbox cũ. Phiên bị ngắt vẫn được giữ để đối soát.
2. Serializer từ chối số NumPy trong binding/calibration, khiến AI dừng trước
   dispatch. Chuẩn hóa các scalar số về int/float; vẫn từ chối NaN/Infinity.
3. Surrender trong Robot vs Robot bị bỏ qua ngoài khoảng READY ngắn.
   Nhận yêu cầu khi đang nghĩ/di chuyển; hoàn tất nước đang chuyển rồi kết thúc,
   không phát thêm nước và không ghi kết quả sớm khi quân còn đang di chuyển.
4. Gắp thử virtual chạy ngay trên GUI. Chuyển các UI job sang MotionWorker,
   đồng thời kiểm tra cờ busy trước khi đọc backend để tránh chờ khóa physics.
5. Lỗi metadata quyền điều khiển làm đóng WebSocket dù joint telemetry còn hợp lệ.
   Tiếp tục phát trạng thái chỉ đọc với command_context=null; lệnh vẫn bị khóa.

## Kiểm tra và giới hạn còn lại

| Kiểm tra | Kết quả |
|---|---|
| Bộ tập trung trên source cuối | 125 passed |
| Bộ serial cuối, gồm socket thật và SDK/camera giả | 10 passed |
| Node viewer contracts | 11/11 file kiểm tra đạt |
| AST, diff và đối chiếu source đã đưa về repo | Đạt; 11 file khớp snapshot đã kiểm tra |
| Lượt hồi quy rộng trước các sửa cuối | 862 passed, **35 failed** |

35 thất bại của lượt rộng được lưu nguyên danh sách, chưa được tuyên bố đã giải
quyết hoặc chạy lại toàn bộ trên bản cuối. Trong đó có kỳ vọng cũ xóa body quân
bị ăn, fixture camera/mode không phù hợp, fixture bỏ qua constructor/binding,
và các ca cần điều tra thêm (route recovery, camera reconciliation, undo,
startup latency). Không sửa code sản phẩm để đáp ứng kỳ vọng xóa quân ở khay
hoặc buộc lỗi optional viewer chặn nước đã commit.

Hai thất bại serial do lỗi metadata làm rớt WebSocket đã được sửa và kiểm tra lại;
10/10 serial hiện đạt. Điều này không xóa kết quả thất bại của lượt hồi quy rộng.

Chưa kiểm chứng: FR3/camera/GPU thật; đo hình học, cao độ và R1–R4 trên setup
ngoài đời; lỗi mất gói/phanh thực tế; API spectator thật; toàn bộ T-01–T-22.
Goal BRD tổng thể chưa được đánh dấu hoàn tất.

## Bằng chứng

`reports/user-flow-qa-20261019/` chứa:

- `ui-flow.jsonl`, `browser-evidence.json`: các bước và telemetry của lượt cuối.
- `browser-*.png`, `0/1/2-*.png`: ảnh viewer và canvas Pygame.
- `manual-flow.jsonl`: kết quả gắp thử cuối.
- `final-focused.log`, `serial-regression-final.log`, `viewer-tests.log`.
- `full-regression.log`, `failing-regressions.json`: kết quả rộng chưa đạt.
- `promoted-source-manifest.json`: hash các file đã đưa về repo.

Các driver trong thư mục bằng chứng dành cho snapshot QA, dùng cổng riêng
8098/8775 và static viewer 8099. Không dùng chúng với dữ liệu phiên đang làm việc.
