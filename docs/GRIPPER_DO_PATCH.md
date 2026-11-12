# Bản vá DO0 mở / DO1 đóng

Chiều kẹp chuẩn của project là **DO0 mở, DO1 đóng** — khớp lần thử từng chân trên robot sau khi đổi dây ngày 02/11/2026 (xem `CURRENT_STATE.md`, `KNOWN_ISSUES.md`). Bản vá cũ `xiangqi-do1-open-do0-close-patch.zip` đảo ngược chiều này: **không dùng nữa**.

Cách khuyến nghị: tải bản ZIP đầy đủ mới ở đầu `README.md`; bản đó đã có chiều DO và luồng kẹp mới, không cần vá.

Nếu máy đang chạy capsule cũ (đã bị đổi sang DO1 mở) và chỉ muốn sửa chiều DO:

1. Thoát hẳn Xiangqi.
2. Chép `tools/capsule/APPLY_DO_PATCH.bat` và `tools/capsule/apply_do_patch.ps1` của nhánh này vào **thư mục đang có `start.bat` và `app/`** (nằm cạnh `start.bat`, không trong thư mục con).
3. Mở **APPLY_DO_PATCH.bat**. Chờ dòng `Applied: DO0 OPEN, DO1 CLOSE` hoặc `Already configured`.
4. Mở lại **start.bat**. Không chạy lại INSTALL hay tải lại thư viện GPU.

Bản vá chỉ sửa hai giá trị trong `app/config.py`: `GRIPPER_OPEN_DO_ID = 0`, `GRIPPER_CLOSE_DO_ID = 1`, có sao lưu `app/config.py.before-do-swap-...`; chạy lại khi đã đúng sẽ không đổi file. Bản vá **không** cập nhật luồng gắp/đặt và thời gian xung mới bên dưới — muốn có những thay đổi đó thì dùng ZIP đầy đủ mới.

## Luồng kẹp hiện tại

- Trước **mỗi** lần gắp (kể cả hai lần gắp trong nước ăn quân): mở tối đa rồi khép về khe an toàn, sau đó mới tiếp cận, hạ xuống và đóng kẹp.
- Đặt quân: hạ xuống, mở tối đa, nhấc lên, rồi khép về khe an toàn.
- Thả quân bị ăn vào khay: mở tối đa, về vị trí phục vụ, rồi khép về khe an toàn.
- Không gắp khi phần mềm đang tin là kẹp còn đóng (có thể còn giữ quân).

Thời gian xung: mở tối đa 0,25s; đóng gắp 0,20s (bắt đầu từ khe an toàn); khép khe an toàn 0,06s; mở nhả ngắn 0,06s (chỉ khi được gọi riêng); deadtime 0,10s; chờ ổn định 0,25s. Hai DO luôn về OFF trước/sau mỗi xung. Xung đóng 0,20s cần được kiểm tra lực kẹp trên robot thật.

Máy chạy source: cập nhật nhánh `fix/fix-capsule` bằng Git, không dùng script dành cho thư mục capsule. Nếu đã chỉnh config tại máy đó, kiểm tra hai giá trị DO sau khi cập nhật.
