# Xiangqi — bộ mang đi sự kiện

1. Giải nén **toàn bộ** ZIP vào một thư mục local có quyền ghi, ví dụ `D:\Xiangqi`. Không mở ứng dụng trực tiếp trong ZIP.
2. Mở **START.bat**.
3. Chọn môi trường và kiểu chơi trên màn hình, rồi bắt đầu.

Không cần cài Python, Node.js, Git, CUDA; không chạy SETUP hoặc pip/npm. Chơi local không cần Internet. Bộ này dành cho **Windows 10/11 x64**, có trình duyệt và đủ RAM/dung lượng cho ứng dụng; không phải bản ARM/32-bit/Windows Server không giao diện. CPU vision được đóng gói sẵn, tốc độ tùy máy.

## Khi dùng robot thật

Kết nối bộ camera và robot của team; xếp bàn khai cuộc. Chọn **Robot thật**. Kiểm tra camera nhìn đúng bàn, robot/kẹp đã dừng và vùng chuyển động phù hợp; xác nhận trên giao diện trước khi F9 → F10 cho phép chuyển động. Mở START không tự bật hoặc chạy robot.

Camera và controller vẫn cần driver/kết nối phần cứng hoạt động. Nếu đổi cổng/camera/máy, team chỉnh `camera_index` và `robot_ip` trong `settings.json` khi bàn giao. Nếu dịch chuyển camera/bàn hoặc đổi bộ robot, phải xác nhận/hiệu chuẩn lại theo setup thực tế; đóng gói phần mềm không thay thế bước này. Không dùng tọa độ robot đi kèm cho một robot/setup khác khi chưa commissioning.

## Nếu không mở được

- Giải nén lại đầy đủ, không copy riêng START.bat. Thư mục cần quyền ghi; không chạy trong Program Files/thư mục chỉ đọc.
- Chụp thông báo và gửi team file `state/launcher-error-*.log`; log game nằm trong `app/logs/`.
- Để team kiểm tra trọn bộ, chạy `START.bat --check` từ terminal. Lệnh này kiểm tra file/model offline, không mở camera/robot. `--smoke` thêm kiểm tra renderer không màn hình.
- Không xóa `app/data/runtime/` để bỏ recovery sau lỗi robot. Giữ nguyên journal và xử lý theo thông báo trong game.

`settings.json` chọn sẵn môi trường (`SIMULATION`, `BOARD_ONLY`, `PHYSICAL`), số camera và IP controller. Người vận hành vẫn đổi môi trường trên màn hình chính được. Team chuẩn bị file này trước sự kiện; người dùng thường chỉ cần START.
