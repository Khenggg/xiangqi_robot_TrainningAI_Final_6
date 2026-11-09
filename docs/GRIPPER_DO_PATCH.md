# Bản vá DO1 mở / DO0 đóng

Dùng cho `xiangqi.zip` Windows GPU light ngày 09/11/2026. Bản ZIP đầy đủ cũ chưa có thay đổi này; cập nhật source bằng Git không tự sửa các bản ZIP đã tải.

1. Thoát hẳn Xiangqi.
2. Tải [xiangqi-do1-open-do0-close-patch.zip](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-gpu-light-20261109/xiangqi-do1-open-do0-close-patch.zip).
3. Giải nén **vào thư mục đang có `start.bat` và `app/`**. Hai file `APPLY_DO_PATCH.bat` và `apply_do_patch.ps1` phải nằm cạnh `start.bat`, không nằm trong một thư mục con mới.
4. Mở **APPLY_DO_PATCH.bat**. Chờ dòng `Applied: DO1 OPEN, DO0 CLOSE` hoặc `Already configured`.
5. Mở lại **start.bat**. Không chạy lại INSTALL hay tải lại thư viện GPU.

Bản vá chỉ sửa hai giá trị trong `app/config.py`: `GRIPPER_OPEN_DO_ID = 1`, `GRIPPER_CLOSE_DO_ID = 0`. Nó giữ camera/IP, profile tọa độ, thời gian xung, dữ liệu ván và runtime. Có bản sao lưu `app/config.py.before-do-swap-...`; chạy lại bản vá khi đã đúng cấu hình sẽ không thay đổi file.

Thời gian giữ nguyên: mở tối đa 0,30s; đóng gắp 0,80s; mở nhả 0,06s; khép khe di chuyển 0,06s; deadtime 0,10s; chờ ổn định 0,25s. Hai DO luôn được đưa về OFF trước/sau mỗi xung. Chiều điều khiển phải khớp dây thực tế; chưa nghiệm thu bản đổi chân trên robot thật.

Bản vá này độc lập với [bản vá R1–R4](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-gpu-light-20261109/xiangqi-r1-r4-fix.zip). Nếu chưa áp dụng R1–R4 thì vẫn cần làm riêng; hai bản vá không thay thế nhau. `--check` so cấu hình với bản đóng gói gốc nên có thể báo config đã thay đổi; khởi động bình thường cho phép sửa file này.

Máy chạy source: cập nhật nhánh `fix/fix-capsule` bằng Git, không dùng script dành cho thư mục capsule. Nếu đã chỉnh config tại máy đó, kiểm tra hai giá trị DO sau khi cập nhật.
