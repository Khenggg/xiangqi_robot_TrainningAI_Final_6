# Cài và chạy trên máy Windows mới

## Chỉ cần SETUP rồi RUN

1. Clone đúng nhánh `feat/player-vs-robot`, hoặc tải ZIP của nhánh này và giải nén toàn bộ.
2. Mở thư mục có `main.py`, `SETUP_WINDOWS.bat`, `RUN.bat` và `models`. Nếu có nhiều thư mục lồng nhau, đi vào thư mục chứa các file này.
3. Kết nối Internet, double-click **SETUP_WINDOWS.bat** và chờ đến thông báo **Setup complete**.
4. Double-click **RUN.bat** để mở client game. Những lần tiếp theo chỉ cần RUN.

Máy cần Windows 10/11 x64. SETUP tự tìm Python 3.12 x64; nếu chưa có, tải trình cài Python chính thức, kiểm tra SHA256 rồi cài cho tài khoản Windows hiện tại. Không cần tự cài Python, kích hoạt môi trường hay nhập lệnh pip. Nếu thiếu Visual C++ Runtime, SETUP tải trình cài chính thức và Windows có thể hỏi quyền quản trị (UAC): chọn Yes để tiếp tục. Nếu Windows/chính sách công ty chặn cài phần mềm hoặc tải Internet, xem lỗi trong cửa sổ SETUP.

## SETUP chuẩn bị những gì?

- Python 3.12 x64 và môi trường riêng `.venv312` trong thư mục project.
- Microsoft Visual C++ Runtime x64 khi máy chưa có, với kiểm tra chữ ký trình cài Microsoft. [PyTorch yêu cầu runtime này trên Windows](https://docs.pytorch.org/docs/main/notes/windows.html); trình cài lấy từ [Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
- Các thư viện đúng phiên bản từ `requirements-lock-win-py312.txt`, gồm PyTorch, Ultralytics/YOLO, OpenCV, ONNX Runtime và Pygame.
- Kiểm tra dependency và import thật; nạp `models/best.pt` và hai model ONNX để phát hiện lỗi trước khi khởi chạy client.
- Kiểm tra các tài nguyên cần thiết đi theo repo, gồm model PT/ONNX và engine Moonfish. Các file này đã nằm trong repo; SETUP không tải đè model hay engine có sẵn.

SETUP kiểm tra trước khi cài: giữ Python 3.12 x64 và Visual C++ Runtime hợp lệ, dùng lại trình cài trong `.setup-cache` sau khi xác thực, và bỏ qua bước cài pip khi môi trường đã có đủ đúng phiên bản trong lock. Nếu thiếu/sai phiên bản, pip bổ sung hoặc sửa dependency; các gói đúng phiên bản được giữ lại. Mỗi lần SETUP vẫn kiểm tra dependency, import và nạp model thật trước khi báo hoàn tất. Chạy lại SETUP sau gián đoạn để tiếp tục; không cần xóa môi trường.

SETUP chỉ chuẩn bị phần mềm; không tự mở camera, không ghi đè calibration, offset hay cấu hình robot, và không điều khiển cánh tay. Độ lệch quang học và sai số gắp phụ thuộc camera/bàn/TCP/teaching points thực tế, không thể tải xuống hoặc tự đoán từ máy khác.

RUN dùng đúng `.venv312` của thư mục đang chạy và kiểm tra môi trường trước khi mở client. Nếu chưa cài xong, RUN dừng và hướng dẫn chạy SETUP; không tự chuyển sang Python khác trên máy.

## Calibration và độ lệch camera

Nhánh này mặc định bật `VISUAL_PVP_PICK_ENABLED = True`: điểm gắp dùng chân bbox 85% và homography bàn như luồng PvP. Chế độ này không dùng nội tại ống kính hay chiều cao quân để tính XY. RUN vẫn yêu cầu calibrate/xác nhận lưới bàn trong client; SETUP không thay thế bước này. Các offset và thông số robot hiện có được giữ nguyên. Xem [luồng điểm gắp PvP](pvp-pick-mode.md).

Nếu chủ động chuyển sang chế độ height/ring cần nội tại ống kính, dùng profile của đúng camera vật lý, độ phân giải, focus và zoom. File `calibration/camera_intrinsics.json` trong repo là profile của camera workstation, không phải profile chung cho mọi webcam; cùng index `0` không có nghĩa là cùng camera.

Để đo camera khác: đóng RUN, in `assets/calibration/checkerboard-20mm.svg` ở Actual Size rồi đo cạnh một ô sau in. Double-click `CALIBRATE_CAMERA_INTRINSICS.bat`, nhập số đo mm khi được hỏi, thu ít nhất 12 mẫu đa dạng theo hướng dẫn cửa sổ. Có thể truyền `--camera INDEX --square-mm VALUE` nếu cần. Tool dùng cùng `.venv312` với RUN và sao lưu profile cũ trước khi lưu profile mới. `CALIBRATE_PICK_GEOMETRY.bat` dành cho chế độ top-face riêng; không phải bước bắt buộc của PvP mặc định. `MEASURE_GEOMETRY.bat` cũng dùng `.venv312` để mở công cụ đo hướng dẫn.

## Khi SETUP hoặc RUN báo lỗi

Cửa sổ giữ lại thông báo lỗi. Log nằm trong thư mục `logs`, tên bắt đầu bằng `setup-windows-` hoặc `run-windows-`. Gửi log mới nhất khi cần hỗ trợ.

Nếu client báo `Gripper LOW failed`, xem ngõ ra `DO0/DO1`, mã lỗi controller
hoặc lỗi RPC trong thông báo và traceback ở log RUN. Client giữ nước AI pending
và dừng trước thao tác tiếp theo; đã nhận nước người chơi không có nghĩa là lệnh
kẹp của robot đã thực hiện thành công. Mỗi RPC dùng kết nối HTTP mới để tránh
socket cũ hết hạn trong lúc chờ, và không tự gửi lại lệnh khi mất phản hồi.

Nếu tải thư viện bị gián đoạn, kiểm tra Internet rồi double-click SETUP lại. Có thư mục `.venv312` chưa có nghĩa là đã cài đủ; chỉ coi setup hoàn tất khi có thông báo **Setup complete**.

Nếu báo thiếu model/tài nguyên, kiểm tra đã giải nén hoặc clone đầy đủ đúng nhánh. File `best.pt` không thay thế thư viện Ultralytics: cần cả file trọng số và môi trường Python hợp lệ.

Mỗi bản clone/thư mục project cần SETUP riêng. Không chép `.venv312` từ máy khác; môi trường chứa đường dẫn và thư viện phụ thuộc máy.

## Vận hành robot thật

Sau khi client mở, kết nối camera và mạng tới controller, kiểm tra `config.py`, điểm dạy R1–R4/HOMECHESS và thực hiện luồng calibrate bàn trong client theo README. Cài phần mềm thành công không thay thế việc xác nhận kết nối, khoảng hở và tọa độ gắp trên phần cứng thực tế.

Chi tiết luồng chơi, calibrate và điều khiển trong client: [README](../README.md).
