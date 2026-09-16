#1: đã kết nối được tuongkydaisu.com nhưng chỉ chơi được với bot, hoạn toàn hoạt động bình thường, roomID hiển thị chưa có tác dụng rõ rệt

#2: Dựa vào cấu trúc API hiện tại (simulation_api_guide.md) thì KHÔNG THỂ HỖ TRỢ TRỰC TIẾP.

Lý do là bộ API Simulation mà Admin cấp cho bạn (/api/simulation/matches) chỉ có quyền khởi tạo phòng rỗng và "bắn" cấu hình bàn cờ lên. Nó thiếu hoàn toàn các API để tương tác 2 chiều (như: kết nối WebSocket để Lắng nghe xem đối thủ vừa đi nước gì, Chờ đối thủ vào phòng, Nhận lời thách đấu,...).

Để làm được tính năng "Người dùng nhập mã 6 số từ Robot sinh ra lên Web để đánh online với cờ thật", dự án sẽ cần:

Bên phía máy chủ tuongkydaisu.com: Cần mở một bộ WebSockets API riêng dành cho Client (Robot) để Robot đóng vai trò là một "Tài khoản người chơi" (Socket CONNECT, SUBSCRIBE /topic/match/{id}).
Bên phía Robot: Phải viết luồng WebSocket lắng nghe 24/7. Khi ông trí tuệ trên Web đi cờ bằng chuột, mạng WebSocket bắn tín hiệu về Python -> Python cập nhật GameState -> Cánh tay Robot mới gắp cục cờ thật dưới bàn di chuyển theo.

#3: có token liên quan đến robot arm trên trang web nhưng chưa rõ tác dụng 