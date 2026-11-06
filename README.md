# [⬇ TẢI CAPSULE.ZIP — WINDOWS X64](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/capsule-windows-x64-20261105-r2/Xiangqi-Capsule-Windows-x64-20261105-r2.zip)

Giải nén toàn bộ → mở **START.bat** → chọn chế độ chơi. Những lần sau chỉ cần mở lại **START.bat**.

## Video demo

[![Video demo Xiangqi Robot — bấm để xem trên YouTube](https://img.youtube.com/vi/PShKIGPRk10/hqdefault.jpg)](https://youtu.be/PShKIGPRk10)

# Xiangqi Robot

Ứng dụng cờ tướng kết hợp engine Moonfish, nhận diện camera, mô phỏng 3D và robot FAIRINO FR3. Bản portable dành cho Windows 10/11 x64 đã bao gồm runtime, thư viện CPU, model và tài nguyên 3D; không cần cài Python, Node.js hay CUDA. Chơi local không cần Internet.

## Sử dụng

1. Tải capsule bằng liên kết ở đầu trang.
2. Giải nén toàn bộ vào thư mục local có quyền ghi, ví dụ `D:\Xiangqi`.
3. Mở **START.bat**, chọn môi trường và chế độ chơi.

Giữ nguyên các thư mục đi kèm; không chạy trực tiếp trong ZIP hoặc copy riêng START.bat. ZIP mã nguồn của GitHub không chứa runtime/model như capsule.

| Chế độ trong capsule | Cách chơi |
|---|---|
| VS Robot | Người Đỏ, AI Đen |
| Human vs Human | Hai người trên cùng bàn ảo |
| Robot vs Robot | Hai AI dùng chung một executor/robot |
| 2 người + robot | Hai người chọn nước, một executor/robot thực hiện cả hai màu |

Với **2 người + robot**, máy chủ chơi Đỏ; nhấn **O** để mở cửa sổ người Đen. Hai cửa sổ kết nối localhost trên cùng PC, không qua LAN/Internet.

## Thiết bị thực tế

Robot/camera cần driver, kết nối và calibration phù hợp với bộ thiết bị. Kiểm tra bàn và trạng thái robot trước khi xác nhận quyền chuyển động **F9 → F10**. Đóng phần mềm không thay thế việc xác nhận robot đã dừng.

Bản đóng gói đã được kiểm tra local; PC Windows sạch thứ hai, cả ván UI/browser và robot thật vẫn cần nghiệm thu riêng.

## Phát triển

Source của bản bàn giao nằm trên nhánh `final`:

```powershell
git clone --branch final https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6.git
```

Khi phát triển từ source, cài môi trường bằng SETUP_WINDOWS.bat trước RUN.bat. Sau thay đổi code, build và kiểm chứng capsule mới trước khi bàn giao.
