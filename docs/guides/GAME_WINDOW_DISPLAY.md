# Cửa sổ game: resize và fullscreen

## Cách sử dụng

- Khi mở, cửa sổ tự co để nằm trong 80% màn hình, chừa chỗ cho thanh tiêu đề/taskbar.
- Kéo cạnh cửa sổ hoặc dùng nút maximize để thay đổi kích thước.
- **F11** bật/tắt fullscreen; **Esc** thoát fullscreen và khôi phục kích thước cửa sổ trước đó.
- Hướng dẫn phím nằm ở cuối giao diện. Bàn cờ giữ đúng tỷ lệ; phần viền trống không nhận bấm.

## Nguyên nhân và sửa đổi

`main.py` trước đây mở display cố định 1440 × 1080, không bật RESIZABLE. Trên màn hình thấp hơn canvas, hoặc khi Windows phóng lớn theo DPI, một phần giao diện nằm ngoài vùng nhìn thấy.

`src/ui/game_window.py` giữ canvas logic 1440 × 1080, co toàn bộ khung hình theo display thực tế, và chuyển vị trí chuột trở lại pixel canvas trước khi đưa vào các handler menu/game. Không đổi ô cờ, trạng thái game, tọa độ robot hoặc calibration. `main.py` đặt SDL DPI awareness trước khi khởi tạo display.

Tham khảo API: [Pygame display](https://www.pygame.org/docs/ref/display.html), [SDL Windows DPI awareness](https://wiki.libsdl.org/SDL2/SDL_HINT_WINDOWS_DPI_AWARENESS).

## Kiểm chứng và giới hạn

- Gate cuối: `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_game_window.py,tests/unit/test_offline_mouse_confirmation.py,tests/test_difficulty_menu.py`: **22 passed**, exit 0.

- Test mapping tất cả 90 ô và nút menu ở cửa sổ 960×720, 1280×720, 700×900, 1920×1080; bấm viền không tạo nước đi.
- Test nước tốt e6→e5 qua chuỗi display pixel → canvas → InputHandler, commit một lần và cập nhật observer ở hai tỷ lệ.
- Driver SDL Windows thật: desktop 1920×1080 → cửa sổ 1152×864 → fullscreen 1920×1080 → khôi phục 1152×864; kiểm tra trực tiếp trả exit 0.
- Đã quan sát cửa sổ bản sửa bằng Computer Use: thanh tiêu đề, menu và phần hướng dẫn cuối trang đều nằm trong ảnh chụp.
- Computer Use vẫn chưa xác nhận gửi được chuột/phím tới game. Test fullscreen trên driver thật gọi đường chuyển chế độ trực tiếp; chưa xác nhận F11 bằng thao tác GUI tự động, chưa chơi hết ván.
