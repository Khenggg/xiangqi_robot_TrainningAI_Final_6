# Hai người chọn nước, một robot thực hiện

Chế độ riêng: `HUMAN_VS_HUMAN_ROBOT`. `HUMAN_VS_HUMAN` cũ vẫn là chơi chuột
trên máy, không điều khiển robot thật.

## Mở ván

1. Chạy `RUN.bat`. Chọn **MÔ PHỎNG 3D** để thử hoặc **ROBOT THẬT** cho phiên
   có camera/FR3. Chế độ mới không dùng preset chỉ bàn cờ 2D.
2. Bấm **2 NGƯỜI + ROBOT**. Không có bước chọn độ khó và không chạy AI.
3. Máy chủ chơi Đỏ. Mã phòng sáu ký tự luôn hiện ở đầu bàn.
4. Bấm **O / MỞ NGƯỜI ĐEN** để mở cửa sổ Đen. Hoặc từ menu chọn
   **VÀO PHÒNG / NGƯỜI ĐEN** rồi nhập mã. Phòng dùng localhost: hai cửa sổ
   trên cùng máy, không phải chơi qua LAN/Internet.
5. Với FR3 thật, khởi tạo chỉ đọc. Người vận hành kiểm tra camera/controller và
   xác nhận F9 rồi F10 như luồng hiện có. Không tự Enable/HOME khi tạo/join phòng.

## Trong ván

- Đỏ chọn quân và ô đến trên máy chủ; Đen chọn trên cửa sổ riêng, nhìn bàn xoay
  180 độ. Tọa độ truyền đi vẫn là `board_grid (col,row)`, cột 0–8, hàng 0–9.
- Robot thực hiện nước cho cả hai màu, kể cả nước ăn. FEN/lượt/ID quân chỉ đổi
  sau luồng thực thi và xác nhận tương ứng; cửa sổ Đen không cập nhật lạc quan.
- Các nút dừng, phục hồi, New Game và đầu hàng nằm trên máy chủ. SURRENDER ở
  máy chủ là Đỏ đầu hàng, kể cả đang lượt Đen.
- SURRENDER nhận yêu cầu ngay cả khi đang chạy/chờ đo tâm. Hệ thống chờ thao tác
  đang chạy hoàn tất và xác nhận dừng; nếu còn nước dang dở, V/CONTINUE chỉ đối
  soát trước khi lưu kết quả. Chúng không thử lại chuyển động khi đang kết thúc ván.
- NEW GAME giữ yêu cầu trong lúc dừng/đối soát, rồi tạo ván khai cuộc. Với robot
  thật, xếp lại bàn32 quân và V xác nhận trước khi bật lại quyền chuyển động.
- Mất kết nối khóa nhận nước mới. Nếu nước đã bắt đầu, không gửi lại nước đó;
  máy chủ giữ trách nhiệm hoàn tất hoặc phục hồi. Đen kết nối lại sẽ nhận bàn
  hiện tại, không phát lại yêu cầu cũ.
- Khi tâm quân/frame chưa đạt trước chuyển động, máy chủ dùng V/Y để đo lại
  đúng nước đang chờ. Sau chuyển động dang dở, phải dùng luồng đối soát/phục hồi
  hiện có. FEN đúng không xóa lỗi controller hoặc thay bằng chứng robot đã dừng.
- Không có SPACE xác nhận nước người, emergency đi tay, rollback hay test gắp
  trong chế độ này. Các thao tác đó không được dùng để bỏ qua robot.

## Ranh giới triển khai

Đóng cửa sổ hoặc Ctrl+C sẽ hỏi **Thoát / Ở lại** đúng một lần. Chọn Thoát đóng
ngay, kể cả khi mất kết nối hoặc đang hiện RECOVERY REQUIRED; không cần F8/F9
để cho phép thoát. Dữ liệu đã ghi trong journal được giữ nguyên. Thao tác này
đóng phần mềm, không phát lệnh đến robot/kẹp và không hoàn tất nước đang dở.

Tính năng phòng/mã/Đỏ–Đen/góc nhìn chọn lọc từ
`origin/feature/nguoivsnguoifinal@73af0f1`; không merge toàn nhánh donor.
`GameState` và journal ở máy chủ là nguồn trạng thái duy nhất. Luồng
`execute_ai_move` được tái sử dụng như bộ thực thi nước đã chọn, không hỏi AI.
Threads mạng chỉ xếp hàng; `MotionWorker` thực thi, giữ nguyên verifier, stop,
pending transaction và receipt hiện có. Client không import module controller/SDK.
Request có room session, peer generation, request ID, epoch và board revision.
Máy chủ kiểm lại token, luật cờ và gate phục hồi trước khi dispatch.

Chỉ mở **một** ứng dụng sở hữu FR3 thật; không chạy đồng thời hai host vật lý
từ hai checkout/worktree. Cửa sổ client không sở hữu phần cứng.

Kiểm thử hiện tại dùng mock motion/camera và sockets localhost. Chưa xác minh
vận hành camera/FR3 thật hoặc cả ván trên phần cứng. Xem báo cáo trong
`reports/robot-pvp-20261102/REPORT.md` trước khi xét merge.
