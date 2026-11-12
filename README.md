<div align="center">

# Xiangqi-FR3

**Hệ thống cờ tướng người – robot: camera nhận diện bàn cờ, AI Moonfish và cánh tay FAIRINO FR3.**

Chơi trên bàn 2D, xem robot ảo trong mô phỏng 3D, hoặc đấu với robot thật trên bàn cờ thật.

### [⬇ Tải Xiangqi-FR3.zip — Windows 10/11 x64](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-fr3-20261112/Xiangqi-FR3.zip)

[Cài đặt nhanh](#cai-dat) · [Sổ tay sử dụng](docs/guides/USER_MANUAL.md) · [Tài liệu](#tai-lieu) · [Báo lỗi](#bao-loi)

</div>

---

## Video demo

<!-- TODO: thay video YouTube demo mới (thumbnail + link) tại đây. -->
[![Video demo Xiangqi-FR3 — bấm để xem trên YouTube](https://img.youtube.com/vi/PShKIGPRk10/hqdefault.jpg)](https://youtu.be/PShKIGPRk10)

## Mục lục

- [Tính năng](#tinh-nang)
- [Cài đặt nhanh (bản capsule)](#cai-dat)
- [Sử dụng](#su-dung)
- [Vận hành robot thật](#robot-that)
- [Chạy từ mã nguồn](#source)
- [Cấu trúc thư mục](#cau-truc)
- [Kiểm thử](#kiem-thu)
- [Build bản phát hành](#build)
- [Tài liệu](#tai-lieu)
- [Ghi chú phát hành](#phat-hanh)
- [Giới hạn hiện tại](#gioi-han)
- [Báo lỗi](#bao-loi)
- [Giấy phép và thành phần bên thứ ba](#giay-phep)

<a id="tinh-nang"></a>
## Tính năng

| Nhóm | Mô tả |
|---|---|
| Ba môi trường | **CHƠI TRÊN MÁY** (bàn 2D), **MÔ PHỎNG 3D** (FR3 ảo trên viewer), **ROBOT THẬT** (camera + controller + viewer mirror) |
| Kiểu chơi | **VS ROBOT** với AI Moonfish 4 mức (Easy / Medium / Hard / Impossible); **2 NGƯỜI + ROBOT** (Đỏ trên máy chủ, Đen trên cửa sổ riêng, robot thực hiện nước cho cả hai) |
| Nhận diện | YOLO (`best.pt`) và ONNX (`cchess` pose/layout) đọc bàn cờ từ camera; ưu tiên CUDA khi có GPU NVIDIA, tự dùng CPU khi không có |
| Mô phỏng | PyBullet cho động học/va chạm FR3, viewer Three.js trên trình duyệt; với robot thật viewer là mirror chỉ để quan sát |
| An toàn | Robot thật bắt đầu ở READ-ONLY; giao dịch nước đi có journal; lỗi gắp/đặt phục hồi qua **HOMECHESS → R/H**; thoát ứng dụng không gửi lệnh chuyển động |
| Bộ cài | `Xiangqi-FR3.bat` kiểm tra máy, chỉ cài phần còn thiếu, không ghi đè thư viện đang có, rồi khởi động game |

<a id="cai-dat"></a>
## Cài đặt nhanh (bản capsule)

### Yêu cầu

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Windows 10/11 x64, thư mục có quyền ghi |
| Python | Không cần cài trước; bộ cài tự cài Python 3.12 cho user hiện tại nếu chưa có |
| Internet | Chỉ cần khi máy còn thiếu thư viện (lần đầu trên máy trống có thể tải vài GB, gồm PyTorch) |
| GPU | Không bắt buộc; GPU NVIDIA có driver phù hợp sẽ được dùng cho nhận diện |
| Robot thật | FAIRINO FR3 đã commission, camera USB, mạng Ethernet tới controller, E-stop sẵn sàng |

### Các bước

1. Tải **[Xiangqi-FR3.zip](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-fr3-20261112/Xiangqi-FR3.zip)** (~144 MB, đã gồm model). Chuột phải → **Properties → Unblock** để Windows không chặn script.
2. Giải nén vào thư mục local, ví dụ `D:\Games`. Không chạy bên trong ZIP; tránh `Program Files` và thư mục OneDrive.
3. Mở **`Xiangqi-FR3.bat`** ở đầu thư mục `Xiangqi-FR3`.
   - Lần đầu: kiểm tra và chỉ cài phần thiếu — Python 3.12, môi trường `.venv312` (dùng lại thư viện đã có trên máy), thư viện Python, Three.js, model.
   - Nếu một thư viện đã có nhưng **sai phiên bản**, bộ cài hỏi trước khi thêm bản tương thích cho riêng project. Từ chối thì giữ nguyên bản cũ (project có thể không chạy đúng).
   - Sau đó game mở theo luồng chuẩn `scripts\windows\RUN.bat`. Các lần sau chỉ kiểm tra lại vài giây rồi vào game.
4. Chọn môi trường và kiểu chơi trên menu (xem [Sử dụng](#su-dung)).

| Lệnh | Tác dụng |
|---|---|
| `Xiangqi-FR3.bat` | Kiểm tra, cài phần thiếu, mở game |
| `Xiangqi-FR3.bat --setup-only` | Chỉ kiểm tra và cài, không mở game |
| `Xiangqi-FR3.bat --help` | Xem tùy chọn khởi động; mọi tham số khác của `RUN.bat` được chuyển nguyên vẹn (ví dụ `--robot`, `--no-3d`) |
| `set XIANGQI_SETUP_MODE=yes` / `no` | Tự trả lời câu hỏi thay phiên bản thư viện |

Kết quả lần kiểm tra gần nhất: `build\installer\last-check.json`. Bộ cài không gửi lệnh nào tới robot.

<a id="su-dung"></a>
## Sử dụng

1. **Chọn môi trường:** CHƠI TRÊN MÁY để bắt đầu nhanh nhất, MÔ PHỎNG 3D để xem robot ảo, ROBOT THẬT khi bộ thiết bị đã sẵn sàng.
2. **Chọn kiểu chơi:** VS ROBOT rồi chọn độ khó (chuột hoặc phím **1–4**), hoặc 2 NGƯỜI + ROBOT (cần mô phỏng hoặc robot thật; phím **O** mở cửa sổ người Đen).
3. **Đi quân:** bấm quân Đỏ rồi bấm ô đích; Đỏ đi trước. Trên robot thật, người đi quân Đỏ trên bàn rồi bấm **SPACE** để xác nhận.

| Phím | Tác dụng |
|---|---|
| SPACE | Xác nhận nước người qua camera (robot thật) |
| V | Quét/đối soát camera hoặc chạy lại nước đang chờ |
| R / H | Phục hồi tại HOMECHESS: chạy lại đúng nước chờ / về HOMECHESS lại |
| F5 | Yêu cầu AI tính lại khi engine lỗi |
| F2 | Đóng phiên, về menu |
| F11 / Esc | Toàn màn hình / thoát toàn màn hình |
| X / Ctrl+C | Hỏi thoát ứng dụng |

Bảng phím đầy đủ, ý nghĩa trạng thái và cách phục hồi: [Sổ tay sử dụng](docs/guides/USER_MANUAL.md) — [Phím tắt](docs/guides/USER_MANUAL.md#phim-tat), [Phục hồi](docs/guides/USER_MANUAL.md#phuc-hoi), [Tra lỗi](docs/guides/USER_MANUAL.md#xu-ly-loi).

<a id="robot-that"></a>
## Vận hành robot thật

> [!WARNING]
> Chỉ vận hành khi bộ thiết bị đã được hiệu chuẩn, camera thấy đủ bàn, controller không lỗi, vùng chuyển động trống và **E-stop trong tầm tay**. Viewer 3D không chứng minh tay/kẹp ngoài đời đã ở đúng vị trí.

- Phiên ROBOT THẬT mở ở chế độ chỉ đọc; quyền chuyển động chỉ được bật sau các kiểm tra startup.
- Mất kết nối robot là sự cố cần xử lý, phần mềm không tự chuyển sang mô phỏng.
- Profile mặc định `calibration/physical_teaching_points_user0.json` chỉ đúng cho bộ bàn/robot đã đo; bộ khác phải hiệu chuẩn lại.
- Chuẩn bị và bật: [Sổ tay — Robot thật](docs/guides/USER_MANUAL.md#robot-that) · Kết nối: [ROBOT_CONNECTION.md](docs/hardware/ROBOT_CONNECTION.md) · Cân chỉnh camera: [Sổ tay — Camera](docs/guides/USER_MANUAL.md#camera) · Phục hồi HOMECHESS: [Sổ tay — R/H](docs/guides/USER_MANUAL.md#homechess-recovery).

<a id="source"></a>
## Chạy từ mã nguồn

Dành cho developer: cần **Git**, **Python 3.12 x64** (launcher `py`) và Internet. Node.js chỉ cần nếu dùng `SETUP_WINDOWS.bat`; `Xiangqi-FR3.bat` tự lấy Three.js mà không cần Node.

```powershell
git clone --branch capsule https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6.git
cd xiangqi_robot_TrainningAI_Final_6
.\Xiangqi-FR3.bat --setup-only      # hoặc .\scripts\windows\SETUP_WINDOWS.bat
.\scripts\windows\RUN.bat
```

Model không nằm trong Git: đặt `models/best.pt`, `models/cchess/pose_4_v6.onnx`, `models/cchess/layout_nano_v3.onnx` (team cung cấp; ONNX có thể tải bằng `scripts/models/download_cchess_models.py`). Thiếu model thì bàn 2D và mô phỏng vẫn chạy, nhận diện camera thì không.

| Lệnh | Tác dụng |
|---|---|
| `RUN.bat --board-only` | Chọn sẵn bàn 2D (alias `--virtual`) |
| `RUN.bat --sim` | Chọn sẵn mô phỏng 3D (mặc định) |
| `RUN.bat --robot` | Chọn sẵn robot thật, ban đầu chỉ đọc (alias `--physical`) |
| `RUN.bat --physical --recalibrate-camera` | Mở luồng chấm lại 4 góc camera |
| `RUN.bat --no-3d` | Không mở viewer (alias `--no-viewer`) |
| `RUN.bat --simulation-profile fast` | Playback mô phỏng nhanh hơn |
| `RUN.bat --viewer-port 8098 --telemetry-port 8898` | Đổi cổng viewer/WebSocket (mặc định 8088/8765) |
| `RUN.bat --help` | Xem tùy chọn, không mở thiết bị |

`RUN.bat` nằm trong `scripts\windows\`. Camera dùng `VIDEO_INDEX` nếu có, nếu không dùng `config.VIDEO_SOURCE`. Cấu hình đang thực thi: [config.py](config.py).

<a id="cau-truc"></a>
## Cấu trúc thư mục

```text
.
├── Xiangqi-FR3.bat          # Cửa vào: kiểm tra/cài phần thiếu rồi khởi động
├── main.py, config.py       # Entry point và cấu hình runtime
├── src/                     # Mã nguồn: core, ui, vision, hardware, motion, simulation, ai, modes
├── shared/                  # Hình học, profile robot, scene, dataset reachability
├── calibration/             # Dữ liệu hiệu chuẩn robot/bàn
├── models/                  # Trọng số nhận diện (không commit)
├── moonfish/                # AI engine Moonfish (UCCI)
├── robot-3d-viewer/         # Viewer Three.js và mô hình FR3/FR5
├── assets/                  # Ảnh UI, bảng checkerboard
├── scripts/
│   ├── windows/             # RUN, SETUP_WINDOWS, SETUP_GPU, BUILD_*, CALIBRATE_*, MEASURE_GEOMETRY (.bat)
│   ├── calibration/         # Công cụ hiệu chuẩn camera và hình học gắp
│   ├── training/            # Sinh dữ liệu và huấn luyện policy
│   └── models/              # Tải model ONNX
├── tools/
│   ├── installer/           # Bộ cài Xiangqi-FR3 và trình build ZIP
│   ├── capsule/             # Trình build capsule portable cũ
│   ├── simulation/  diagnostics/  hardware_tests/
│   └── test_fast.ps1        # Test runner song song
├── docs/
│   ├── guides/              # Sổ tay, khởi động, logging, đo hình học
│   ├── architecture/        # Kiến trúc mô phỏng, hợp đồng hình học, chế độ chơi
│   ├── hardware/            # Kết nối robot, kẹp, hiệu chuẩn bàn
│   ├── api/  build/  reviews/  specs/  notes/
├── tests/                   # Unit test (pytest) và test viewer (node)
├── reports/  plans/         # Báo cáo kiểm chứng và kế hoạch
└── AGENTS.md, PROJECT_CONTEXT.md, REPO_MAP.md, CURRENT_STATE.md, KNOWN_ISSUES.md
```

<a id="kiem-thu"></a>
## Kiểm thử

```powershell
.\tools\test_fast.ps1                                              # toàn bộ test không đánh dấu slow, chạy song song
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_xiangqi_fr3_installer.py
npm run test:viewer                                                # test viewer bằng Node
```

Test runner dùng `python` trên `PATH`; kích hoạt `.venv312` trước khi chạy. Test trong `tools/hardware_tests/` điều khiển robot thật: **chỉ chạy tuần tự, khi có người vận hành ủy quyền và FR3 sẵn sàng**.

<a id="build"></a>
## Build bản phát hành

```powershell
.\scripts\windows\BUILD_XIANGQI_FR3.bat --models "D:\path\to\models" [--force]
```

Tạo `Xiangqi-FR3.zip` ở gốc repo (được `.gitignore` bỏ qua): file project từ Git (không gồm `tests/`, `reports/`, `plans/`, `.agents/`, `.codex/`), toàn bộ model, Three.js theo `package-lock.json` và manifest. Capsule portable cũ vẫn build bằng `scripts\windows\BUILD_CAPSULE.bat`. Chi tiết: [WINDOWS_CAPSULE_BUILD.md](docs/build/WINDOWS_CAPSULE_BUILD.md).

<a id="tai-lieu"></a>
## Tài liệu

| Chủ đề | Tài liệu / mã nguồn |
|---|---|
| Sổ tay người chơi và vận hành | [USER_MANUAL.md](docs/guides/USER_MANUAL.md), [START_PROJECT.md](docs/guides/START_PROJECT.md) |
| Capsule và bộ cài | [WINDOWS_CAPSULE_BUILD.md](docs/build/WINDOWS_CAPSULE_BUILD.md), [CAPSULE_OPERATOR.md](docs/guides/CAPSULE_OPERATOR.md), [tools/installer/](tools/installer/) |
| Menu, độ khó, dừng/thoát | [main.py](main.py), [board_renderer.py](src/ui/board_renderer.py), [exit_confirmation.py](src/ui/exit_confirmation.py) |
| Chế độ và tham số khởi động | [session_profile.py](src/core/session_profile.py), [launch_options.py](src/core/launch_options.py) |
| Player vs Robot và 2 người + robot | [HVR_VSC_V3.md](docs/architecture/HVR_VSC_V3.md), [TWO_HUMAN_ROBOT_MODE.md](docs/architecture/TWO_HUMAN_ROBOT_MODE.md), [robot_pvp.py](src/core/robot_pvp.py) |
| Phím, phục hồi, đối soát | [input_handler.py](src/ui/input_handler.py), [game_state.py](src/core/game_state.py), [recovery_status.py](src/ui/recovery_status.py), [session_control.py](src/core/session_control.py) |
| Robot, kẹp, frame | [ROBOT_CONNECTION.md](docs/hardware/ROBOT_CONNECTION.md), [GRIPPER_DO_PATCH.md](docs/hardware/GRIPPER_DO_PATCH.md), [ROBOT_FRAME_BASE_ONLY.md](docs/architecture/ROBOT_FRAME_BASE_ONLY.md), [hardware_manager.py](src/hardware/hardware_manager.py) |
| Hiệu chuẩn camera/bàn | [BRD_XY_CALIBRATION.md](docs/hardware/BRD_XY_CALIBRATION.md), [camera_offset_notes.md](docs/hardware/camera_offset_notes.md), [geometry-measurement.md](docs/guides/geometry-measurement.md), [teaching_points_guide.md](docs/guides/teaching_points_guide.md) |
| Mô phỏng và viewer | [SIMULATION_ARCHITECTURE.md](docs/architecture/SIMULATION_ARCHITECTURE.md), [PHYSICAL_GEOMETRY_CONTRACT.md](docs/architecture/PHYSICAL_GEOMETRY_CONTRACT.md), [robot-3d-viewer/](robot-3d-viewer/README.md) |
| Log và journal | [LOGGING.md](docs/guides/LOGGING.md), [project_logging.py](src/core/project_logging.py), [game_persistence.py](src/core/game_persistence.py) |
| Bối cảnh dự án và trạng thái | [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), [REPO_MAP.md](REPO_MAP.md), [CURRENT_STATE.md](CURRENT_STATE.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md) |

<a id="phat-hanh"></a>
## Ghi chú phát hành

**12/11/2026 — `Xiangqi-FR3.zip` (release [`xiangqi-fr3-20261112`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/xiangqi-fr3-20261112), nhánh `capsule`)**
- Repo được tổ chức lại: launcher vào `scripts/windows/`, script vào `scripts/{calibration,training,models}/`, tài liệu vào `docs/{guides,architecture,hardware,…}/`. Luồng chạy game không đổi.
- Bộ cài một chạm `Xiangqi-FR3.bat`; ZIP đã gồm model và Three.js.

**11/11/2026 — phục hồi HOMECHESS:** VS ROBOT trên robot thật phục hồi lỗi gắp/đặt bằng **HOMECHESS → lấy quân và khôi phục bàn → R chạy lại đúng nước chờ**. Đã bỏ `Ctrl+F8`. Camera thử index 0–2, tự enable khi kiểm tra đạt; Player vs Robot dùng logic `vsc-v3` riêng.

**10/11/2026 — chiều kẹp DO0 mở / DO1 đóng:** mở tối đa rồi khép về khe an toàn trước mỗi lần gắp; đặt quân bằng mở tối đa rồi khép lại sau khi nhấc. Xung: mở tối đa 0,25 s, đóng gắp 0,20 s. Gồm sửa lỗi R1–R4. **Không dùng bản vá cũ `xiangqi-do1-open-do0-close-patch.zip`** — nó đảo chiều DO, ngược với dây thực tế. Chi tiết: [GRIPPER_DO_PATCH.md](docs/hardware/GRIPPER_DO_PATCH.md).

**Nâng cấp từ capsule portable cũ (`start.bat` / `app/`):** thoát ứng dụng, sao lưu `app/config.py` nếu đã chỉnh riêng. Chỉ chép lại các giá trị camera/IP riêng sang `config.py` mới — không chép nguyên config cũ vì sẽ đảo chiều DO và thời gian xung. Giữ journal (`app/data/runtime/`) và calibration của máy cho tới khi phiên cũ đã đóng.

<a id="gioi-han"></a>
## Giới hạn hiện tại

- Bản capsule mới chưa được nghiệm thu trên một máy Windows sạch (chưa có Python / Visual C++ Redistributable).
- Chưa nghiệm thu đầy đủ camera, controller và robot thật cho cả ván; kết quả test cũ chỉ có giá trị trong phạm vi và ngày đã ghi.
- Còn vấn đề physical đã ghi nhận sau mất nguồn, lỗi controller/tool context và kiểm chứng nhả kẹp có tải. Auto-enable hoặc V/F12 **không chứng minh** đường đi sau sự cố là an toàn — dừng vận hành và để team kiểm tra.
- Kẹp điều khiển theo xung, không có cảm biến vị trí ngàm.
- Phòng Đỏ–Đen chỉ chạy localhost trên cùng PC; menu chưa có tiếp tục ván cũ.

Chi tiết: [KNOWN_ISSUES.md](KNOWN_ISSUES.md) và [Sổ tay — Giới hạn](docs/guides/USER_MANUAL.md#gioi-han).

<a id="bao-loi"></a>
## Báo lỗi

1. Chụp cửa sổ game/panel phục hồi, Camera Monitor và bàn thật nếu liên quan; ghi giờ xảy ra.
2. Ghi môi trường, kiểu chơi, lượt, ô nguồn–đích, nút vừa bấm và robot đã chạy tới đâu.
3. Gửi thư mục log của phiên trong `logs/<id-phien>/`: đọc `errors.log` trước, rồi `run.log`; kèm `events.jsonl` và `session.json`.
4. Nếu chưa vào được game: gửi `build\installer\last-check.json` và nội dung cửa sổ `Xiangqi-FR3.bat`.
5. Giữ nguyên journal (`data/runtime/`) và calibration tại máy để team đối soát; nêu release ZIP hoặc commit đang dùng.

<a id="giay-phep"></a>
## Giấy phép và thành phần bên thứ ba

Repo chưa có file giấy phép chung cho mã nguồn dự án. Thành phần bên thứ ba giữ giấy phép riêng:

| Thành phần | Giấy phép |
|---|---|
| Moonfish | [moonfish/LICENSE.md](moonfish/LICENSE.md) |
| Three.js | MIT (`node_modules/three/LICENSE`) |
| occt-import-js | [robot-3d-viewer/vendor/occt-import-js/LICENSE.md](robot-3d-viewer/vendor/occt-import-js/LICENSE.md) |
| Python 3.12 (bộ cài đi kèm) | PSF License |
| Model nhận diện | Do team quản lý; kiểm tra quyền phân phối trước khi chia sẻ công khai |

Sổ tay này không thay tài liệu commissioning hay hướng dẫn bảo trì của controller/robot FAIRINO.
