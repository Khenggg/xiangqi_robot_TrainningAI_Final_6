# Bản vá DO0 mở / DO1 đóng

Chiều kẹp chuẩn của project là **DO0 mở, DO1 đóng** — khớp lần thử từng chân trên robot sau khi đổi dây ngày 02/11/2026 (xem `CURRENT_STATE.md`, `KNOWN_ISSUES.md`). Bản vá cũ `xiangqi-do1-open-do0-close-patch.zip` đảo ngược chiều này: **không dùng nữa**.

Chạy source dùng luồng kẹp dưới đây. Bản ZIP cũ chỉ có hành vi của phiên bản đã đóng gói; bản vá chiều DO không bổ sung chức năng giữ đóng liên tục.

Nếu máy đang chạy capsule cũ (đã bị đổi sang DO1 mở) và chỉ muốn sửa chiều DO:

1. Thoát hẳn Xiangqi.
2. Chép `tools/capsule/APPLY_DO_PATCH.bat` và `tools/capsule/apply_do_patch.ps1` của nhánh này vào **thư mục đang có `start.bat` và `app/`** (nằm cạnh `start.bat`, không trong thư mục con).
3. Mở **APPLY_DO_PATCH.bat**. Chờ dòng `Applied: DO0 OPEN, DO1 CLOSE` hoặc `Already configured`.
4. Mở lại **start.bat**. Không chạy lại INSTALL hay tải lại thư viện GPU.

Bản vá chỉ sửa hai giá trị trong `app/config.py`: `GRIPPER_OPEN_DO_ID = 0`, `GRIPPER_CLOSE_DO_ID = 1`, có sao lưu `app/config.py.before-do-swap-...`; chạy lại khi đã đúng sẽ không đổi file. Bản vá **không** cập nhật luồng gắp/đặt và thời gian xung mới bên dưới — muốn có những thay đổi đó thì dùng ZIP đầy đủ mới.

## Luồng kẹp hiện tại

- Trước **mỗi** lần gắp (kể cả hai lần gắp trong nước ăn quân): mở tối đa, giữ nguyên độ mở khi tiếp cận và hạ xuống. Không khép về khe chuẩn trước khi gắp.
- Tại điểm gắp: giữ DO1 ở hướng đóng trong lúc nâng và di chuyển. Trước khi mở nhả, tắt hướng đóng, chờ deadtime rồi mới cấp DO0.
- Đặt quân: hạ xuống, mở tối đa, nhấc lên, rồi khép về khe an toàn.
- Thả quân bị ăn vào khay: mở tối đa, về vị trí phục vụ, rồi khép về khe an toàn.
- Không gắp khi phần mềm đang tin là kẹp còn đóng (có thể còn giữ quân).

Các thời gian chuẩn nằm trong `config.py`. `GRIPPER_CLOSE_PULSE_SEC` hiện là khoảng chờ đóng ban đầu; hết khoảng này **không tắt DO1**. Mở/khép khe chuẩn sau đặt vẫn dùng xung hữu hạn. Hai hướng không được bật đồng thời.

Controlled stop, lỗi chuyển động và cleanup yêu cầu dừng cánh tay trước khi ngắt tín hiệu giữ khi phiên sở hữu robot thật. Thoát nhanh cũng xử lý ngõ ra đang được phần mềm giữ trước khi kết thúc tiến trình; nếu chưa xác nhận được dừng/OFF, phiên được giữ lại cùng lỗi. Mất điện, kill tiến trình từ bên ngoài hoặc mất kết nối không có bảo đảm ngắt bằng phần mềm. Chưa có cảm biến lực/độ mở hoặc bằng chứng định mức giữ điện liên tục của motor/driver; kiểm thử mock không xác nhận lực giữ, nhiệt hoặc việc quân không rơi trên phần cứng.

Máy chạy source: cập nhật nhánh `fix/fix-capsule` bằng Git, không dùng script dành cho thư mục capsule. Nếu đã chỉnh config tại máy đó, kiểm tra hai giá trị DO sau khi cập nhật.
