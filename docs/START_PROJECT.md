# Khởi động dự án

## Bản capsule

Giải nén bộ phát hành, mở **START.bat**, rồi chọn môi trường và chế độ chơi. Không chạy SETUP trên máy sử dụng capsule. Chi tiết: [Vận hành capsule](CAPSULE_OPERATOR.md).

## Chạy từ source

Cần Windows x64, Python 3.12 có Launcher `py`, Node.js/npm và Internet cho bước cài dependency. Chạy tại thư mục repo:

```powershell
.\SETUP_WINDOWS.bat
if ($LASTEXITCODE -ne 0) { throw 'SETUP thất bại. Xử lý lỗi trước khi chạy game.' }
.\RUN.bat
```

SETUP tạo `.venv312`, cài thư viện Python/ONNX và asset Three.js. SETUP không tải trọng số nhận diện hay thực hiện calibration. Đường camera cần `models/best.pt`, `models/cchess/pose_4_v6.onnx` và `models/cchess/layout_nano_v3.onnx`.

| Lệnh | Chức năng |
|---|---|
| `.\RUN.bat` hoặc `--sim` | Game + mô phỏng FR3 + viewer |
| `.\RUN.bat --board-only` | Bàn 2D, không camera/robot/viewer |
| `.\RUN.bat --robot` | Camera + controller + mirror, ban đầu chỉ đọc |
| `.\RUN.bat --no-3d` | Giữ môi trường đã chọn, không mở viewer |
| `.\RUN.bat --physical --recalibrate-camera` | Chọn sẵn calibration camera tương tác |
| `.\RUN.bat --simulation-profile fast` | Profile playback nhanh của simulation |
| `.\RUN.bat --help` | Xem CLI, không mở thiết bị |

Các alias `--virtual`, `--physical`, `--no-viewer` lần lượt tương ứng `--board-only`, `--robot`, `--no-3d`. `--simulation-profile` chỉ áp dụng cho simulation. Tham số CLI chọn sẵn môi trường; người dùng vẫn chọn trên màn hình chính.

`RUN.bat` ưu tiên Python trong `.venv312`, rồi `.venv`, sau đó Python/py trong PATH. Script kiểm tra dependency cơ bản và trả mã lỗi của ứng dụng. `XIANGQI_NO_PAUSE=1` bỏ bước chờ cuối script khi chạy từ automation.

## Chọn chế độ

- **VS Robot:** người Đỏ, AI Đen.
- **Human vs Human:** bàn ảo cho hai người, không robot thật.
- **Robot vs Robot:** hai AI dùng cùng executor/robot.
- **2 người + robot:** máy chủ Đỏ và cửa sổ người Đen; một executor/robot thực hiện cả hai màu. Cần simulation hoặc physical. Nhấn O để mở người Đen; phòng chỉ localhost cùng PC. Xem [hướng dẫn mode](TWO_HUMAN_ROBOT_MODE.md).

## Phiên mới và phục hồi

Mỗi lần mở/chọn ván tạo bàn khai cuộc mới, Đỏ đi trước. Hiện không có lựa chọn tiếp tục nguyên ván cũ; dữ liệu phiên cũ được archive.

Khi phiên physical trước còn thao tác chưa giải quyết, khởi động lại vẫn giữ yêu cầu phục hồi. Kiểm tra arm/kẹp, xử lý stop theo UI, xếp bàn khai cuộc và V xác nhận trước khi F9/F10. Ứng dụng không tự phát lại lệnh cũ. Giữ journal để xử lý giao dịch có kết quả chưa xác định.

Đóng cửa sổ máy chủ hoặc Ctrl+C hiện **Thoát / Ở lại**. Xác nhận Thoát đóng phần mềm ngay; thao tác này không gửi lệnh dừng robot và không xác nhận thiết bị đã dừng. Cửa sổ người Đen đóng trực tiếp khi bấm X.

## Camera và profile robot

Camera dùng calibration đã lưu khi setup không thay đổi. Để chấm lại bốn góc, chọn **Robot thật**, tick **Chấm lại 4 góc bàn từ camera** rồi bắt đầu phiên:

1. Chọn bốn giao điểm ngoài cùng theo thứ tự Xe Đen trái, Xe Đen phải, Xe Đỏ phải, Xe Đỏ trái.
2. Kiểm tra lưới hiển thị.
3. S để lưu, R để làm lại, Q/Esc để hủy.

Profile physical mặc định: `calibration/physical_teaching_points_user0.json`, robot base/user 0. Luồng này đọc bộ tọa độ cố định của setup, không tự lấy lại teaching/WObj từ controller. Profile chỉ dùng cho bộ thiết bị đã hiệu chuẩn. Xem [frame robot](ROBOT_FRAME_BASE_ONLY.md) và [board calibration](BRD_XY_CALIBRATION.md).

Camera Monitor hiển thị nhận diện theo frame; xác nhận FEN và giao dịch nước đi là bước riêng. Khi robot không sẵn sàng, kiểm tra kết nối/controller bên cạnh ảnh camera: [Kết nối robot](../ROBOT_CONNECTION.md).

## Viewer và log

Viewer dùng Three.js local và CAD loader đã vendor. Nếu source thiếu asset, chạy lại SETUP; với capsule, giải nén lại trọn bộ. Sau cập nhật, khởi động lại ứng dụng và tải lại viewer nếu trình duyệt giữ trang cũ.

Log source: `logs/<id-phien>/`. Log capsule: `app/logs/<id-phien>/`, lỗi launcher: `state/launcher-error-*.log`. Đọc `errors.log`, sau đó `run.log`. Xem [LOGGING.md](LOGGING.md).
