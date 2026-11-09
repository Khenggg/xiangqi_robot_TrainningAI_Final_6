# Xiangqi — xiangqi.zip

Bản đầy đủ `xiangqi-gpu-light-20261109-fixed` đã tích hợp sửa lỗi truyền profile R1–R4 và chiều kẹp DO1 mở / DO0 đóng. Không cần bản vá riêng; thời gian xung giữ nguyên.

1. Giải nén **toàn bộ** xiangqi.zip vào thư mục local có quyền ghi, ví dụ D:\Xiangqi. Không mở trực tiếp trong ZIP.
2. Lần đầu mở **INSTALL.bat**, hoặc chạy **start.bat -Setup**. File này thực thi start.run để giải nén runtime nền rồi tải/cài thư viện ML vào runtime của ứng dụng. Lần đầu cần Internet và vài GB trống; NVIDIA dùng PyTorch CUDA, máy không có NVIDIA dùng CPU. Không cài vào Python hệ thống, không cần admin.
3. Từ đó mở **start.bat** để chạy project. Nếu chưa setup, start.bat tự chuẩn bị runtime trước rồi mở game.

start.run là script PowerShell cho bước cài đặt, không phải định dạng double-click chuẩn của Windows. Dùng INSTALL.bat hoặc start.bat -Setup để Windows thực thi đúng script; không cần đổi registry hay file association.

## Giữ nguyên luồng source

Launcher chạy Python đi kèm, chuyển thư mục làm việc sang app và chạy đúng app/main.py. Không ghi đè config.py, engine, chế độ chơi, camera/IP hoặc lựa chọn vision. Không tự thêm tham số chọn chế độ. Tham số CLI truyền vào start.bat được chuyển nguyên sang project. Không dùng settings.json của capsule r2. Chỉnh cấu hình như source tại app/config.py; biến môi trường giữ nguyên tác dụng như chạy source.

Source giữ camera ưu tiên index cấu hình rồi thử các index còn lại trong 0–2; phiên physical tự thử enable một lần khi kiểm tra hiện có đạt. Không tự HOME/chỉnh kẹp; sau lỗi/stop/recovery vẫn dùng đối soát và F9/F10 thủ công. Web 3D và telemetry giữ nguyên. Robot vs Robot dùng F6 để bắt đầu self-play.

Runtime dành cho Windows 10/11 x64, đóng gói PyTorch CUDA 12.4 và ONNX Runtime GPU 1.20.1. Project ưu tiên GPU khi driver NVIDIA tương thích sẵn có, tự dùng CPU nếu GPU không khả dụng theo luồng source. CUDA/cuDNN DLL cần thiết đi kèm runtime; không cài CUDA Toolkit toàn hệ thống. Gói không tự cài hoặc cập nhật driver NVIDIA. Model/engine/viewer/font đi kèm; thư viện ML được tải trong lần setup đầu. Camera và controller vẫn cần driver, mạng và calibration đúng thiết bị. Khi đổi camera hoặc bàn, chấm lại bốn góc; đóng gói không thay thế calibration vật lý.

## Kiểm tra và lỗi

- start.bat --check: kiểm tra SHA256/model offline, không mở camera/robot.
- start.bat --smoke: thêm kiểm tra renderer headless, không mở camera/robot.
- Log launcher nằm trong state/launcher-error-*.log; log project tại app/logs/.
- Không xóa app/data/runtime/ để bỏ recovery. Giữ journal và xử lý theo trạng thái thực tế.
- Nếu runtime.zip hỏng, giải nén lại toàn bộ xiangqi.zip. Không copy riêng start.bat.

Đóng ứng dụng chính hỏi Thoát/Ở lại như source. Thoát phần mềm không chứng minh robot đã dừng. Cửa sổ người Đen đóng trực tiếp. Phòng Đỏ/Đen chỉ localhost trên cùng máy.

Bản này có Player vs Robot dùng logic vsc-v3 riêng, giữ cấu hình phần cứng hiện tại và cầu web 3D hiển thị. Xem docs/HVR_VSC_V3.md trong source.
