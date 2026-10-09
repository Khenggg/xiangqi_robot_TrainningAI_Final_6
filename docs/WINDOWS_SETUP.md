# Cài và chạy trên máy Windows mới

## Chỉ cần SETUP rồi RUN

1. Clone đúng nhánh `feature/visual-correction-v2`, hoặc tải ZIP của nhánh này và giải nén toàn bộ.
2. Mở thư mục có `main.py`, `SETUP_WINDOWS.bat`, `RUN.bat` và `models`. Nếu có nhiều thư mục lồng nhau, đi vào thư mục chứa các file này.
3. Kết nối Internet, double-click **SETUP_WINDOWS.bat** và chờ đến thông báo **Setup complete**.
4. Double-click **RUN.bat** để mở client game. Những lần tiếp theo chỉ cần RUN.

Máy cần Windows 10/11 x64. SETUP tự tìm Python 3.12 x64; nếu chưa có, tải trình cài Python chính thức, kiểm tra SHA256 rồi cài cho tài khoản Windows hiện tại. Không cần tự cài Python, kích hoạt môi trường hay nhập lệnh pip. Nếu thiếu Visual C++ Runtime, SETUP tải trình cài chính thức và Windows có thể hỏi quyền quản trị (UAC): chọn Yes để tiếp tục. Nếu Windows/chính sách công ty chặn cài phần mềm hoặc tải Internet, xem lỗi trong cửa sổ SETUP.

## SETUP chuẩn bị những gì?

- Python 3.12 x64 và môi trường riêng `.venv312` trong thư mục project.
- Microsoft Visual C++ Runtime x64 khi máy chưa có, với kiểm tra chữ ký trình cài Microsoft. [PyTorch yêu cầu runtime này trên Windows](https://docs.pytorch.org/docs/main/notes/windows.html); trình cài lấy từ [Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
- Các thư viện đúng phiên bản từ `requirements-lock-win-py312.txt`, gồm PyTorch, Ultralytics/YOLO, OpenCV, ONNX Runtime và Pygame.
- Kiểm tra dependency và import thật; nạp `models/best.pt` và hai model ONNX để phát hiện lỗi trước khi khởi chạy client.
- Kiểm tra các tài nguyên cần thiết đi theo repo, gồm engine Moonfish và profile camera `calibration/camera_intrinsics.json`.

SETUP không yêu cầu đo lại nội tại camera, không ghi đè cấu hình robot và không điều khiển cánh tay. Profile camera có sẵn dùng cho setup ban đầu; giữ camera và chế độ ảnh tương ứng với profile đó.

RUN dùng đúng `.venv312` của thư mục đang chạy và kiểm tra môi trường trước khi mở client. Nếu chưa cài xong, RUN dừng và hướng dẫn chạy SETUP; không tự chuyển sang Python khác trên máy.

## Khi SETUP hoặc RUN báo lỗi

Cửa sổ giữ lại thông báo lỗi. Log nằm trong thư mục `logs`, tên bắt đầu bằng `setup-windows-` hoặc `run-windows-`. Gửi log mới nhất khi cần hỗ trợ.

Nếu tải thư viện bị gián đoạn, kiểm tra Internet rồi double-click SETUP lại. Có thư mục `.venv312` chưa có nghĩa là đã cài đủ; chỉ coi setup hoàn tất khi có thông báo **Setup complete**.

Nếu báo thiếu model/tài nguyên, kiểm tra đã giải nén hoặc clone đầy đủ đúng nhánh. File `best.pt` không thay thế thư viện Ultralytics: cần cả file trọng số và môi trường Python hợp lệ.

Mỗi bản clone/thư mục project cần SETUP riêng. Không chép `.venv312` từ máy khác; môi trường chứa đường dẫn và thư viện phụ thuộc máy.

## Vận hành robot thật

Sau khi client mở, kết nối camera và mạng tới controller, kiểm tra `config.py`, điểm dạy R1–R4/HOMECHESS và thực hiện luồng calibrate bàn trong client theo README. Cài phần mềm thành công không thay thế việc xác nhận kết nối, khoảng hở và tọa độ gắp trên phần cứng thực tế.

Chi tiết luồng chơi, calibrate và điều khiển trong client: [README](../README.md).
