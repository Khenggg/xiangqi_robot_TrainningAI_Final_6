# [⬇ TẢI CAPSULE.ZIP — WINDOWS X64](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/capsule-windows-x64-20261105-r2/Xiangqi-Capsule-Windows-x64-20261105-r2.zip)

Giải nén toàn bộ → mở **START.bat** → chọn chế độ chơi. Những lần sau chỉ cần mở lại **START.bat**.

## Video demo

[![Video demo Xiangqi Robot — bấm để xem trên YouTube](https://img.youtube.com/vi/PShKIGPRk10/hqdefault.jpg)](https://youtu.be/PShKIGPRk10)

# Xiangqi Robot

Hệ thống chơi cờ tướng kết hợp giao diện Pygame, engine Moonfish, nhận diện camera và điều khiển robot FAIRINO FR3. Ứng dụng hỗ trợ chơi trên máy, mô phỏng 3D và vận hành với bộ camera/robot thực tế.

Capsule Windows đã bao gồm runtime Python, thư viện CPU, model nhận diện, engine và tài nguyên 3D. Người sử dụng không cần cài Python, Node.js, Git hay CUDA. Chơi local không cần Internet.

## Mục lục

- [Phần 0 — Khởi động](#phan-0)
- [Phần 1 — Cấu trúc dự án](#phan-1)
- [Phần 2 — Kiến trúc và luồng xử lý](#phan-2)
- [Phần 3 — Các module](#phan-3)
- [Phần 4 — Vận hành](#phan-4)
- [Phần 5 — Chế độ chơi và AI](#phan-5)
- [Phần 6 — Camera và calibration](#phan-6)
- [Phần 7 — Cấu hình và dữ liệu](#phan-7)
- [Phần 8 — Kiểm thử và xử lý lỗi](#phan-8)
- [Phần 9 — Tài liệu tham khảo](#phan-9)

<a id="phan-0"></a>
## PHẦN 0: KHỞI ĐỘNG

### Sử dụng capsule

1. Tải capsule bằng liên kết ở đầu trang.
2. Giải nén toàn bộ vào một thư mục local có quyền ghi, ví dụ `D:\Xiangqi`.
3. Mở **START.bat** và chọn môi trường, chế độ chơi.

Yêu cầu: **Windows 10/11 x64**, có trình duyệt và đủ tài nguyên để chạy ứng dụng. Giữ nguyên các thư mục `runtime/`, `app/` và dữ liệu đi kèm; không chạy trực tiếp trong ZIP hoặc copy riêng START.bat. Bản ZIP mã nguồn của GitHub không chứa môi trường/model như capsule.

Với robot thật, camera/controller cần driver, kết nối và bộ calibration phù hợp. Khi đổi camera, di chuyển bàn hoặc thay robot, kiểm tra lại cấu hình trước khi vận hành. Hướng dẫn chi tiết: [Vận hành capsule](docs/CAPSULE_OPERATOR.md).

<details>
<summary><strong>Chạy từ source — dành cho phát triển</strong></summary>

Cài Python 3.12 x64 có Python Launcher và Node.js/npm, sau đó chạy tại thư mục repo:

```powershell
git clone --branch final https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6.git
cd xiangqi_robot_TrainningAI_Final_6
.\SETUP_WINDOWS.bat
if ($LASTEXITCODE -ne 0) { throw 'SETUP thất bại. Xử lý lỗi trước khi chạy game.' }
.\RUN.bat
```

SETUP tạo môi trường `.venv312`, cài dependency Python/ONNX và asset Three.js. Chỉ chạy RUN sau khi SETUP thành công. Các lần sau dùng RUN; chạy lại SETUP khi dependency thay đổi hoặc môi trường bị thiếu.

Đường camera cần bổ sung model vào `models/best.pt`, `models/cchess/pose_4_v6.onnx` và `models/cchess/layout_nano_v3.onnx`. Trọng số được quản lý riêng, không nằm trong Git. Moonfish đã có source trong repo.

Lệnh chạy theo môi trường: [Khởi động từ source](docs/START_PROJECT.md).

</details>

### Tạo bản bàn giao mới

Team build capsule trên máy phát triển với thư mục model đã chuẩn bị:

```powershell
.\BUILD_CAPSULE.bat --models "D:\path\to\models"
```

Kết quả gồm thư mục portable, ZIP và checksum tại `dist/`. Sau khi thay code, cần build và kiểm chứng capsule mới trước khi phát hành; push source không tự cập nhật ZIP. Xem [Hướng dẫn build](docs/WINDOWS_CAPSULE_BUILD.md).

<a id="phan-1"></a>
## PHẦN 1: CẤU TRÚC DỰ ÁN

```text
main.py                 # Menu, lifecycle và game loop
config.py               # Cấu hình runtime
RUN.bat                 # Chạy source
SETUP_WINDOWS.bat       # Cài môi trường phát triển
BUILD_CAPSULE.bat       # Đóng gói bản portable
src/                    # Game, AI, vision, hardware, mô phỏng và UI
moonfish/               # Engine cờ local
models/                 # Model nhận diện, được cung cấp riêng khi build
assets/                 # Tài nguyên giao diện
robot-3d-viewer/         # Viewer Three.js và CAD
shared/                 # Geometry, scene và physics
calibration/            # Profile theo bộ thiết bị
scripts/                # Công cụ đo và calibration
tools/                  # Build, kiểm thử và chẩn đoán
tests/unit/             # Tests Python và JavaScript
docs/                   # Hướng dẫn kỹ thuật
```

<a id="phan-2"></a>
## PHẦN 2: KIẾN TRÚC VÀ LUỒNG XỬ LÝ

```text
Chuột / Camera / Engine
         ↓
Kiểm tra luật, lượt và phiên
         ↓
Context nước đi → Worker → Executor
                          ├─ Mô phỏng FR3 / PyBullet
                          └─ Controller robot / camera xác minh
         ↓
Commit bàn cờ, FEN và lượt
         ↓
Giao diện / Viewer / Nhật ký
```

Máy chủ sở hữu trạng thái ván cờ và giao dịch thực thi. Client người Đen gửi yêu cầu nước đi, nhận bàn đã được máy chủ xác nhận. Viewer hiển thị trạng thái; trong phiên robot thật, viewer là mirror và không cấp quyền chuyển động.

Mỗi phiên mới bắt đầu từ bàn khai cuộc, Đỏ đi trước. Lịch sử phiên được archive; các biên nhận và yêu cầu phục hồi của thao tác đang dở vẫn được giữ. Khởi động lại không tự phát lại lệnh robot.

<a id="phan-3"></a>
## PHẦN 3: CÁC MODULE

| Module | Trách nhiệm |
|---|---|
| `src/core/` | Luật/FEN, game state, session, journal, worker và điều phối PvP |
| `src/ai/` | Engine Moonfish và quản lý yêu cầu AI |
| `src/vision/` | Camera, nhận diện, calibration ảnh và xác định điểm gắp |
| `src/hardware/` | Controller/SDK, quyền motion, stop và telemetry |
| `src/simulation/` | FR3 virtual, kinematics, physics và collision checks |
| `src/digital_twin/` | Đồng bộ trạng thái hiển thị |
| `src/domain/` | Move identity, geometry và board pose |
| `src/ui/` | Menu, bàn cờ, điều khiển, recovery và client người Đen |
| `src/api/` | Kết nối spectator tùy chọn |
| `tools/capsule/` | Builder, launcher và kiểm tra bản đóng gói |

<a id="phan-4"></a>
## PHẦN 4: VẬN HÀNH

### Môi trường chạy

| Môi trường | Chức năng |
|---|---|
| **Chơi trên máy** | Bàn cờ 2D, không camera/robot/viewer |
| **Mô phỏng 3D** | Robot FR3 ảo, physics và viewer |
| **Robot thật** | Camera, controller và viewer; kết nối ban đầu chỉ đọc |

### Phiên robot thật

1. Kết nối đúng bộ thiết bị và xếp bàn khai cuộc.
2. Mở START.bat, chọn **Robot thật** và chế độ chơi.
3. Kiểm tra ảnh camera/bàn cờ. Dùng tùy chọn **Chấm lại 4 góc bàn từ camera** khi cần hiệu chuẩn lại.
4. Kiểm tra robot/kẹp, tool/frame, vùng chuyển động và E-stop; nhấn **F9 → F10** để xác nhận quyền chuyển động khi hệ thống đủ điều kiện.
5. Theo dõi kết quả thực thi, camera và FEN trước khi đi nước tiếp.

### Điều khiển

Các phím phụ thuộc chế độ và trạng thái hiện tại; xem thông báo trên giao diện.

| Điều khiển | Chức năng |
|---|---|
| Chuột | Chọn quân/đích, nút và menu |
| V / Continue | Đối soát hoặc thử lại nước đang chờ theo trạng thái |
| SPACE | Xác nhận nước người bằng camera trong mode hỗ trợ |
| F4; 1 / 2 | Quét toàn bàn; xác nhận lượt Đỏ/Đen khi được yêu cầu |
| O | Mở cửa sổ người Đen trong **2 người + robot** |
| F2 | Về menu/đổi phiên qua luồng điều khiển session |
| F5 | Thử lại yêu cầu AI |
| F6 / F7 / F8 | Self-play liên tục / bước tiếp trong step mode / dừng |
| F9 → F10 | Yêu cầu và xác nhận bật quyền physical motion |
| Ctrl+F8 / Ctrl+F9 | Xác nhận theo hướng dẫn phục hồi stop/controller |
| F12 | Khởi tạo lại phiên lỗi khi đủ điều kiện đối soát/dừng |
| T / H / Y | Test gắp–thả / hover / đo lại điểm gắp khi mode cho phép |
| M / Z | Emergency camera / undo history khi mode cho phép |

Undo history không tự trả quân thật. Mode **2 người + robot** không cho SPACE đi tay, emergency, undo hoặc test gắp.

Đóng cửa sổ máy chủ/game chính hoặc Ctrl+C hiện **Thoát / Ở lại**. Xác nhận Thoát đóng phần mềm ngay, không gửi lệnh dừng robot/kẹp; không coi đóng phần mềm là xác nhận thiết bị đã dừng. Cửa sổ người Đen đóng trực tiếp khi bấm X.

<a id="phan-5"></a>
## PHẦN 5: CHẾ ĐỘ CHƠI VÀ AI

| Chế độ | Cách chơi |
|---|---|
| **VS Robot** | Người chơi Đỏ, AI chơi Đen |
| **Human vs Human** | Hai người nhập chuột trên cùng bàn ảo, không robot thật |
| **Robot vs Robot** | Hai AI, dùng chung một executor/robot cho hai màu |
| **2 người + robot** | Hai người chọn nước, một executor/robot thực hiện; không AI |

**2 người + robot:** chọn **Mô phỏng 3D** hoặc **Robot thật**, sau đó chọn mode. Đỏ dùng máy chủ; nhấn **O / Mở người Đen** hoặc **Vào phòng / Người Đen** và nhập mã sáu ký tự. Hai cửa sổ chạy trên cùng PC qua localhost; chưa hỗ trợ LAN/Internet. Mất client thì khóa nước mới, máy chủ giữ trách nhiệm đối với giao dịch đang dở. Xem [Hướng dẫn mode](docs/TWO_HUMAN_ROBOT_MODE.md).

Capsule dùng engine **Moonfish local**. Các mức độ được chọn trên giao diện; kết quả tìm nước gắn với phiên/lượt để loại bỏ kết quả cũ. Mô phỏng có profile `detailed` và `fast`; thay profile không đổi tốc độ robot thật.

<a id="phan-6"></a>
## PHẦN 6: CAMERA VÀ CALIBRATION

| Dữ liệu | Phạm vi |
|---|---|
| `perspective.npy` | Ảnh camera → giao điểm bàn cờ |
| Intrinsics/profile vision | Tham số camera cho mode geometry tương ứng |
| Teaching points và board/contact calibration | Bàn cờ → robot base/tool target |

Lưới logic có 9 cột × 10 hàng, nước đi dùng `(col, row)`. SDK dùng mm/deg; các module mô phỏng chuyển đơn vị ở ranh giới riêng. R1–R4 là bốn giao điểm ngoài cùng của lưới, không phải mép tấm bàn.

Profile physical mặc định nằm tại `calibration/physical_teaching_points_user0.json`. Đây là dữ liệu của một bộ thiết bị cụ thể; việc copy phần mềm sang PC khác không hiệu chuẩn một robot/bàn/camera khác. Camera hoặc bàn xê dịch cần kiểm tra lại perspective; đổi camera/focus/resolution cần kiểm tra lại profile tương ứng.

<a id="phan-7"></a>
## PHẦN 7: CẤU HÌNH VÀ DỮ LIỆU

- **Capsule:** `settings.json` chọn sẵn môi trường, camera index và IP controller. Mặc định là simulation, vision CPU và engine local.
- **Source:** `config.py`, CLI và session profile xác định môi trường/capability; `calibration/` và `shared/` chứa dữ liệu theo setup.
- **Journal:** `app/data/runtime/` trong capsule, `data/runtime/` khi chạy source. Giữ lại khi có giao dịch chưa giải quyết.
- **Logs:** `app/logs/` trong capsule; lỗi launcher nằm ở `state/launcher-error-*.log`.
- **Spectator:** tích hợp tùy chọn khi chạy source, cấu hình credential ngoài Git. Capsule không mang credential của máy phát triển.

<a id="phan-8"></a>
## PHẦN 8: KIỂM THỬ VÀ XỬ LÝ LỖI

### Kiểm thử từ source

```powershell
.\.venv312\Scripts\python.exe -m pip install pytest pytest-xdist
$env:PATH = (Join-Path $PWD '.venv312\Scripts') + ';' + $env:PATH
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_windows_capsule.py
npm run test:viewer
```

Để kiểm tra bản capsule từ terminal: `START.bat --check`. Lệnh này kiểm tra file/model offline, không mở camera/controller. `START.bat --smoke` thêm kiểm tra renderer không màn hình.

### Xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra |
|---|---|
| Capsule không mở | Giải nén đầy đủ, kiểm tra quyền ghi và `state/launcher-error-*.log` |
| Viewer trống | Capsule: kiểm tra/giải nén lại bộ đầy đủ; source: cài asset bằng SETUP |
| Không thấy camera | Camera index, driver, model và calibration |
| Controller mất kết nối | Cáp, adapter, IP/subnet và telemetry; xem [Kết nối robot](ROBOT_CONNECTION.md) |
| Nước đang pending/recovery | Giữ journal; xử lý theo hướng dẫn đối soát/dừng trên UI |
| Client Đen mất kết nối | Kiểm tra máy chủ/mã phòng; không gửi lại nước đã bắt đầu |

Bản đóng gói đã được kiểm tra local với model/engine thật, mô phỏng và đường dẫn tiếng Việt. Kiểm tra này chưa thay thế nghiệm thu PC Windows sạch thứ hai, cả ván UI/browser hoặc robot thật. Các vấn đề và phạm vi kiểm chứng được ghi trong [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

<a id="phan-9"></a>
## PHẦN 9: TÀI LIỆU THAM KHẢO

| Chủ đề | Tài liệu |
|---|---|
| Vận hành capsule | [CAPSULE_OPERATOR.md](docs/CAPSULE_OPERATOR.md) |
| Build bản portable | [WINDOWS_CAPSULE_BUILD.md](docs/WINDOWS_CAPSULE_BUILD.md) |
| Khởi động từ source | [START_PROJECT.md](docs/START_PROJECT.md) |
| Hai người + robot | [TWO_HUMAN_ROBOT_MODE.md](docs/TWO_HUMAN_ROBOT_MODE.md) |
| Log và chẩn đoán | [LOGGING.md](docs/LOGGING.md) |
| Camera và visual correction | [VISUAL_V2_INTEGRATION.md](docs/VISUAL_V2_INTEGRATION.md) |
| Robot-base / board calibration | [ROBOT_FRAME_BASE_ONLY.md](docs/ROBOT_FRAME_BASE_ONLY.md), [BRD_XY_CALIBRATION.md](docs/BRD_XY_CALIBRATION.md) |
