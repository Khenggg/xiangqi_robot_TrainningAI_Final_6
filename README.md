# [⬇ TẢI CAPSULE.ZIP — WINDOWS X64](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/capsule-windows-x64-20261105-r2/Xiangqi-Capsule-Windows-x64-20261105-r2.zip)

**368,8 MiB · Giải nén toàn bộ → mở START.bat · Những lần sau chỉ mở lại START.bat.**

[Xem Release và checksum](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105-r2) · [Source và hướng dẫn bản bàn giao trên nhánh final](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/tree/final)

---

# XIANGQI ROBOT CỜ TƯỚNG VIP — SPECIFICATION DOCUMENT

> Bản bàn giao Windows x64 CPU — nhánh **`final`**, ngày **05/11/2026**.
> Code nền `need-review@30649c4`, gồm chế độ 2 người + robot và xác nhận thoát; capsule được build riêng từ nhánh này. Những kết quả phần cứng trong báo cáo cũ chỉ có giá trị tại setup và thời điểm của báo cáo đó.

**Mang đi sự kiện / bàn giao:** tải [Xiangqi Capsule Windows x64 — 368,8 MiB](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/capsule-windows-x64-20261105-r2/Xiangqi-Capsule-Windows-x64-20261105-r2.zip), giải nén toàn bộ và mở **`START.bat`**. Không cần cài Python, Node.js, Git hay CUDA; không chạy SETUP và không tải thư viện tại sự kiện. Màn hình đầu cho chọn môi trường và kiểu chơi; mặc định là mô phỏng FR3.

[Trang Release](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105-r2) · [Checksum SHA256](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/capsule-windows-x64-20261105-r2/Xiangqi-Capsule-Windows-x64-20261105-r2.zip.sha256)

Hướng dẫn người vận hành: [CAPSULE_OPERATOR.md](docs/CAPSULE_OPERATOR.md). Hướng dẫn team tạo ZIP: [WINDOWS_CAPSULE_BUILD.md](docs/WINDOWS_CAPSULE_BUILD.md). `SETUP_WINDOWS.bat` → `RUN.bat` bên dưới là luồng **phát triển từ source**, không phải luồng dùng capsule.

README giữ bố cục tài liệu cũ và mô tả bản bàn giao trên `final`. Không áp dụng hướng dẫn rollback/manual-rollback hoặc bộ cài của nhánh `feat/player-vs-robot` cho nhánh này.

## 📋 TỔNG QUAN HỆ THỐNG

### Hệ thống là gì?

Ứng dụng cờ tướng có giao diện Pygame, luật cờ/FEN, engine Moonfish, nhận diện camera và một runtime mô phỏng FR3 với viewer Three.js. Phiên physical dùng camera và adapter điều khiển robot; viewer physical nhận telemetry để hiển thị, không phải bộ lập đường chống va chạm cho robot thật.

Tên lớp `FR5Robot` trong `src/hardware/robot_VIP.py` là tên tương thích của code điều khiển cũ. Mô hình robot trong subsystem mô phỏng hiện tại là FAIRINO FR3; phải xác minh đúng model/controller thực tế trước khi dùng phần cứng.

### Hệ thống có thể làm gì?

| Chức năng | Trạng thái/phạm vi hiện tại |
|---|---|
| Người đấu AI | Nhập chuột ở virtual; camera và robot ở physical nếu đủ các gate |
| Người đấu người | Hai bên nhập trên cùng bàn ảo; session được ép về virtual |
| 2 người + robot | Máy chủ Đỏ và cửa sổ Đen trên cùng PC; một executor/robot thực hiện hai màu, không AI |
| Robot đấu robot | Hai AI điều khiển hai màu, dùng một executor/robot; không phải hai cánh tay độc lập |
| Mô phỏng 3D | FR3, bàn/quân, gắp/thả/ăn quân, physics và collision checks |
| Viewer physical | Hiển thị trạng thái tay và bàn; căn chỉnh XY/chiều cao có trạng thái xác minh riêng |
| Camera | YOLO occupancy + CChess ONNX, calibration phối cảnh, xác nhận bàn và hậu kiểm |
| Phục hồi | Pending move, journal/outbox, stop barrier, quét đối soát và khởi tạo phiên mới |
| Spectator từ xa | Tùy chọn, cần credential do chủ dịch vụ cấp; độc lập với viewer local |
| Phòng người Đen | Mã 6 ký tự, cửa sổ riêng quay bàn 180°; localhost cùng máy, không LAN/Internet |

Không suy ra độ chính xác gắp, khả năng chống va chạm phần cứng hay nghiệm thu một ván hoàn chỉnh chỉ từ việc unit test hoặc simulation chạy được.

### Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Giao diện game | Python, Pygame |
| Camera/geometry | OpenCV, NumPy, Ultralytics/PyTorch |
| Nhận diện 90 ô | ONNX Runtime, RTMPose và layout classifier |
| Engine cờ | Moonfish Python; Cloud engine là đường cấu hình khác |
| Mô phỏng | PyBullet, FR3 kinematics, collision guard |
| Viewer | Three.js, ES modules, STL/CAD loader local |
| Đồng bộ | WebSocket, HTTP/API, journal/outbox JSON |
| Kiểm thử | pytest, pytest-xdist, Node test runner |

### Kiến trúc tổng thể

```text
Chuột / Camera → luật cờ + GameState/FEN + AI
                          ↓
             MoveContext + execution binding
                          ↓
              Worker / executor được chọn
                 ├─ Virtual FR3 → PyBullet + collision guard
                 └─ Physical adapter → controller + xác minh camera
                          ↓
                Commit bàn và identity map
                          ↓
          Projection → Three.js / spectator / log
```

Viewer không được tự bước physics hoặc phát lại một nước robot chỉ để sửa hình ảnh. Trong physical, simulation là mirror; kết quả collision của virtual không tự cấp quyền chuyển động thật.

## Mục lục

- [Phần 0 — Nhận capsule và setup source](#phan-0)
- [Phần 1 — Cấu trúc thư mục](#phan-1)
- [Phần 2 — Kiến trúc và luồng game](#phan-2)
- [Phần 3 — Các module](#phan-3)
- [Phần 4 — Vận hành và phím tắt](#phan-4)
- [Phần 5 — AI và các chế độ chơi](#phan-5)
- [Phần 6 — Camera, tọa độ và calibration](#phan-6)
- [Phần 7 — Cấu hình, lưu trạng thái và API](#phan-7)
- [Phần 8 — Kiểm thử và xử lý lỗi](#phan-8)
- [Phần 9 — FAQ và tài liệu chi tiết](#phan-9)

---

<a id="phan-0"></a>
# PHẦN 0: BÀN GIAO CAPSULE & MÔI TRƯỜNG PHÁT TRIỂN

### 0.1. Bàn giao capsule — dành cho người vận hành

1. Tải asset **`Xiangqi-Capsule-Windows-x64-20261105-r2.zip`** từ [Release capsule](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105-r2), copy sang máy Windows 10/11 x64 có trình duyệt. Không chọn `Source code (zip)` hay nút Download ZIP mã nguồn trên GitHub: chúng không có runtime/model.
2. Giải nén toàn bộ vào thư mục local có quyền ghi, ví dụ `D:\Xiangqi`.
3. Mở `START.bat`, chọn chế độ và chơi. Không mở trực tiếp trong ZIP, không copy riêng file START.

Những lần sau chỉ mở lại `START.bat`. Đây là ứng dụng portable: giữ nguyên cả thư mục `runtime/`, `app/` và dữ liệu đi kèm; không có bước cài môi trường lặp lại trên máy sử dụng.

Runtime CPU, thư viện, Moonfish, model nhận diện, Three.js/CAD và font quân cờ nằm sẵn trong bundle. Chơi local không cần Internet. Camera/controller vẫn cần kết nối và driver của bộ thiết bị; thay vị trí camera/bàn hoặc robot cần xác minh calibration. Capsule không tự cấp quyền chuyển động; luồng xác nhận physical giữ nguyên.

Team chuẩn bị `settings.json` cho máy/bộ thiết bị trước sự kiện. Xem [hướng dẫn ngắn](docs/CAPSULE_OPERATOR.md) để xử lý lỗi hoặc tìm log. Không mang `.venv` của máy phát triển sang máy nhận.

**Bản capsule đã kiểm chứng:** 386.748.507 byte, SHA256 `c0616011ef822978d269744516d1f99c0796e76419bb28cdab49374d4c227e15`. Gồm CPython 3.12.10, 47 package đã pin, vision CPU, model YOLO/CChess, Moonfish, Three.js/CAD và font CJK. Runtime/DLL được nạp từ bundle; không mang journal, log hay credential của workstation.

Kiểm chứng local: **105 tests đạt**; ZIP nguyên gốc được giải nén sang đường dẫn có dấu/khoảng trắng, chạy model thật, nước hợp lệ từ engine, mô phỏng 32 quân, HTTP JS/WASM và mở/đóng menu ứng dụng. Chưa nghiệm thu trên một PC Windows sạch thứ hai, cả ván UI/browser hoặc robot thật. Xem [bằng chứng đóng gói](reports/final-capsule-r2-20261105/REPORT.md).

### 0.2. Môi trường phát triển từ source — chỉ dành cho team

Các yêu cầu và lệnh SETUP sau đây chỉ áp dụng khi **clone source để phát triển/build**, không áp dụng cho người nhận capsule.

- Windows x64, Python **3.12 x64** có Python Launcher `py`, Node.js/npm trong PATH.
- Internet cho lần cài thư viện Python và Three.js. Nhánh này không tự cài Python hay Node.js.
- Virtual/game-only không cần camera và controller. Physical cần thiết bị, calibration và trọng số nhận diện được chuẩn bị riêng.
- GPU không bắt buộc. CPU chạy được; hiệu năng inference tùy máy. Không có cam kết FPS chung.

#### Clone đúng nhánh và cài môi trường

```powershell
git clone --branch final https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6.git
cd xiangqi_robot_TrainningAI_Final_6
.\SETUP_WINDOWS.bat
if ($LASTEXITCODE -ne 0) { throw 'SETUP thất bại. Xử lý lỗi cài đặt trước khi chạy game.' }
.\RUN.bat
```

**Lần đầu trên máy mới: phải chạy SETUP thành công trước khi RUN.** Chờ terminal báo `Setup complete.` và kết thúc với mã `0`. Nếu SETUP báo lỗi hoặc dừng giữa chừng, xử lý lỗi rồi chạy lại SETUP; chưa chuyển sang RUN. Nếu mở file bằng chuột, hãy mở `SETUP_WINDOWS.bat` từ terminal để giữ lại log khi có lỗi.

`SETUP_WINDOWS.bat` tạo `.venv312` nếu chưa có, cài `requirements.txt`, chọn CPU ONNX nếu máy chưa có GPU ONNX, kiểm tra import và chạy `npm ci --include=dev`. Bộ cài không tải checkpoint camera, không đo camera, không đổi teaching points và không vận hành arm.

Sau khi setup thành công, những lần sử dụng tiếp theo chỉ cần chạy `RUN.bat` với mode mong muốn. Chạy lại SETUP khi dependency thay đổi hoặc môi trường/asset bị thiếu. `RUN.bat` chọn Python, kiểm tra một số dependency và mở game; nó không tự cài môi trường thay SETUP.

Chạy SETUP lại có thể chạy lại pip/npm; nhánh này dùng requirements theo dải phiên bản, không có luồng lock/cache validation giống bộ cài của `feat/player-vs-robot`. Không sao chép `.venv312` từ máy khác.

### 0.3. Model và engine

Trọng số `.pt`/`.onnx` đã được bỏ khỏi Git. Clone thành công không có nghĩa là đã có model camera.

| Tài nguyên | Đặt tại | Nguồn/ghi chú |
|---|---|---|
| YOLO nhận diện quân | `models/best.pt` | Checkpoint tương thích do nhóm dự án cung cấp |
| Pose bàn | `models/cchess/pose_4_v6.onnx` | Xem [nguồn CChess](models/cchess/README.md) |
| Layout 90 ô | `models/cchess/layout_nano_v3.onnx` | Xem [nguồn CChess](models/cchess/README.md) |
| Engine local | `moonfish/moonfish_ucci.py` | Đã có source trong repo; không cần tải Pikafish/NNUE cho đường mặc định |
| Three.js | `node_modules/three/` | Do `npm ci --include=dev` cài theo `package-lock.json` |
| CAD loader | `robot-3d-viewer/vendor/occt-import-js/` | Đã vendor cùng nhánh, gồm JS/WASM và license |

Physical yêu cầu cả YOLO và CChess. Chưa có model thì dùng simulation/game-only để kiểm tra phần mềm; không bỏ gate camera để chạy arm.

### 0.4. Cập nhật bản mới

Đóng phiên game cũ theo luồng dừng an toàn, rồi cập nhật trong đúng thư mục đang chạy:

```powershell
git branch --show-current
git status --short
git pull --ff-only origin final
git rev-parse --short HEAD
```

Giữ lại các thay đổi calibration/config cục bộ trước khi pull. Nếu dependency thay đổi, chạy SETUP lại. Khởi động lại game; tải lại viewer bằng Ctrl+F5 để không dùng module trình duyệt cũ.

### 0.5. Team tạo bản bàn giao

Sau khi chuẩn bị model trên máy build, chạy `BUILD_CAPSULE.bat --models "D:\path\to\models"`. Builder đóng gói runtime/dependency CPU, model, engine, viewer và font; kiểm tra bộ đóng gói rồi xuất thư mục portable, ZIP và SHA256 trong `dist/`. Source/pipeline nằm trên nhánh `final`; ZIP/runtime/model phát hành qua GitHub Releases, không đưa binary nặng vào lịch sử Git. Hướng dẫn build và nghiệm thu: [WINDOWS_CAPSULE_BUILD.md](docs/WINDOWS_CAPSULE_BUILD.md).

---

<a id="phan-1"></a>
# PHẦN 1: CẤU TRÚC THƯ MỤC CỐT LÕI

```text
xiangqi_robot_TrainningAI_Final_6/
├── main.py                         # Launcher, menu, lifecycle và game loop
├── config.py                       # Cấu hình thực thi
├── RUN.bat / SETUP_WINDOWS.bat      # Khởi động / cài dependency Windows
├── BUILD_CAPSULE.bat               # Team tạo bộ portable ZIP để bàn giao
├── SETUP_GPU.bat                    # Chuyển sang stack GPU riêng
├── requirements.txt                # Dependency runtime
├── package.json / package-lock.json # Three.js và viewer checks
├── pytest.ini                      # Chỉ thu thập tests/unit
├── PROJECT_CONTEXT.md              # Kiến trúc + ghi chú nguồn chuẩn/lịch sử
├── REPO_MAP.md                      # Định tuyến subsystem
├── CURRENT_STATE.md / KNOWN_ISSUES.md
├── calibration/                    # Profile camera/teaching/calibration
├── models/                         # Đặt checkpoint camera ở đây; không tracked
├── moonfish/                       # Engine local Python
├── shared/                         # Geometry, scene, physics và dữ liệu tham chiếu
├── robot-3d-viewer/                 # Viewer Three.js local
├── src/
│   ├── core/                       # Game, session, journal, worker, self-play
│   ├── ai/                         # Moonfish, cloud và controller
│   ├── api/                        # Spectator/API transport
│   ├── vision/                     # Camera, nhận diện, mapping, consensus
│   ├── hardware/                   # SDK, adapter, stop và telemetry
│   ├── domain/                     # Move identity, board pose/XY, capture layout
│   ├── digital_twin/               # Projection/mirror và relay telemetry
│   ├── simulation/                 # Runtime, FR3 backend và PyBullet physics
│   ├── kinematics/                 # FK/IK FR3
│   └── ui/                         # Renderer, input và recovery status
├── scripts/                        # Công cụ calibration/đo geometry
├── tools/
│   ├── test_fast.ps1               # Runner tests theo subsystem/marker
│   ├── capsule/                    # Builder, launcher và acceptance probe
│   ├── hardware_tests/             # Chẩn đoán có thể tác động robot thật
│   └── simulation/                 # Server, demo và công cụ virtual
├── tests/unit/                     # Kiểm thử tự động Python/Node
├── docs/                           # Hướng dẫn theo tính năng
├── reports/                        # Báo cáo và bằng chứng theo commit
├── logs/                           # Tạo khi chạy; không tracked
└── data/runtime/                   # Journal/outbox cục bộ; không tracked
```

Giữ các `__init__.py`, `.keep`, asset CAD và profile cần cho runtime. Không xóa journal/calibration để làm mất thông báo lỗi mà chưa hiểu trạng thái đang được giữ.

---

<a id="phan-2"></a>
# PHẦN 2: KIẾN TRÚC TỔNG THỂ & LUỒNG GAME

### 2.1. Khởi động và session

1. Parse CLI, khởi tạo log và ghi phiên bản code.
2. Hiện launcher; chọn kiểu chơi và môi trường có khả năng tương ứng.
3. Tạo session profile, worker và các backend cần dùng.
4. Mỗi phiên mới bắt đầu từ **FEN khai cuộc, Đỏ đi trước**; lịch sử cũ được archive. Launcher không có chức năng tiếp tục nguyên ván cũ.
5. Nếu có lệnh phần cứng chưa giải quyết, phiên mới vẫn giữ recovery latch. Restart không tự phát lại motion, cũng không chứng minh arm/kẹp đã an toàn.

### 2.2. Lượt người và lượt AI

```text
Người: chuột hoặc camera
  → xác định nguồn/đích → kiểm tra luật, lượt và board revision
  → commit nước hợp lệ → đồng bộ identity/bàn

AI: snapshot FEN/board
  → engine → kiểm tra nước đi → tạo pending context/binding
  → executor thực hiện và xác minh theo môi trường
  → commit một lần → projection/viewer/spectator → lượt tiếp
```

Physical yêu cầu camera xác nhận bàn và hậu kiểm trước khi commit nước robot. Bảng log đã nhận nước người không chứng minh arm đã gắp/đặt thành công. Lỗi viewer/spectator sau commit không được làm robot phát lại nước đã thực hiện.

### 2.3. Board, FEN và identity

- Board logic có 10 hàng × 9 cột; API nước đi dùng `(col, row)`.
- Cột `0..8` tương ứng `a..i`, hàng `0..9` giữ theo client; ví dụ `h0 → g2`.
- Ký hiệu nội bộ gồm `r_K`, `b_N`, `r_C`, `.`; `r/b` là Đỏ/Đen.
- FEN là trạng thái luật; identity map và `MoveContext` dùng để giữ đúng quân/capture trong executor và viewer.
- Pending context gắn session/epoch/calibration; thay mode hoặc dữ liệu hiệu chuẩn có thể làm binding cũ không còn hợp lệ.

### 2.4. Hết ván và lỗi đang dở

Thắng/thua dựa trên luật và bàn đã commit. Đầu hàng, hết nước và lỗi engine/controller là các sự kiện khác nhau. Không coi camera chưa xác nhận hay RPC lỗi là bằng chứng một phe thua. Xem trạng thái cụ thể và kết quả tests của phiên bản đang chạy; không dùng các số PASS lịch sử làm nghiệm thu phần cứng.

---

<a id="phan-3"></a>
# PHẦN 3: TÀI LIỆU CÁC MODULE

| Nhóm | File chính | Trách nhiệm |
|---|---|---|
| Luật và FEN | `src/core/xiangqi.py`, `fen_utils.py` | Nước hợp lệ, chiếu, chuyển board/FEN |
| Game state | `src/core/game_state.py` | Lượt, history, pending, commit và đối soát |
| Profile/khởi tạo | `session_profile.py`, `session_startup.py` | Tách kiểu chơi khỏi môi trường, tạo session mới |
| Lifecycle | `session_control.py`, `session_disposal.py` | Dừng/pause/reset/home/quit theo stop barrier |
| Lưu trạng thái | `game_persistence.py`, `session_journal.py` | Checkpoint, receipt, archive và recovery |
| Worker | `motion_worker.py`, `projection_worker.py` | Tách chuyển động khỏi projection/UI |
| Binding | `execution_binding.py`, `src/domain/game_move.py` | Quyền thực thi gắn với ngữ cảnh hiện tại |
| AI | `src/ai/ai_controller.py`, `moonfish_engine.py`, `cloud_engine.py` | Quản lý engine, tìm nước và thời gian chờ |
| Self-play | `src/core/self_play_controller.py` | Điều phối hai màu qua cùng hệ thực thi |
| Phần cứng | `hardware_manager.py`, `robot_VIP.py`, `robot_sdk_core.py` | Khởi tạo, read-only/enable, mapping và RPC |
| Adapter/stop | `simulation_adapter.py`, `controlled_stop.py` | Nối executor với backend và xác minh dừng |
| Camera | `camera_monitor.py`, `camera_startup.py`, `auto_calibrate.py` | Vòng đời ảnh, calibration và health |
| Nhận diện | `cchess_recognizer.py`, `snapshot_detector.py`, `board_diagnostics.py` | Layout, occupancy và chẩn đoán lệch bàn |
| Điểm gắp | `visual_pick_modes.py`, `height_pick_geometry.py`, `pick_consensus.py` | Chọn geometry và target có kiểm soát |
| Simulation | `src/simulation/runtime.py`, `virtual_fr3_backend.py`, `physics/` | Orchestration, FK/IK, collision và physics |
| Twin | `src/digital_twin/`, `src/hardware/telemetry_publisher.py` | Mirror/telemetry; không thay motion authority |
| UI | `src/ui/board_renderer.py`, `input_handler.py` | Vẽ board/menu, input và trạng thái phục hồi |
| API/log | `src/api/simulation_client.py`, `project_logging.py` | Spectator, retry dữ liệu, log và redaction |

Đường dẫn viết tắt trong bảng thuộc `src/core/`, `src/hardware/`, `src/vision/` hoặc `src/ui/` theo nhóm. [REPO_MAP.md](REPO_MAP.md) cung cấp routing chi tiết. Tài liệu context có các snapshot cũ; cấu hình/code hiện tại và provenance của calibration quyết định hành vi thực thi.

---

<a id="phan-4"></a>
# PHẦN 4: HƯỚNG DẪN CHẠY HỆ THỐNG

### 4.1. Lệnh khởi động

**Bản bàn giao:** giải nén ZIP, mở `START.bat`. Không có bước SETUP trên máy sự kiện. Chọn **Chơi trên máy**, **Mô phỏng 3D** hoặc **Robot thật** trên màn hình đầu; xem [CAPSULE_OPERATOR.md](docs/CAPSULE_OPERATOR.md).

**Chạy source để phát triển:** máy mới/clone lần đầu phải chạy `SETUP_WINDOWS.bat` trước. Tại thư mục repo, sau khi đã cài Python 3.12 và Node.js/npm:

```powershell
.\SETUP_WINDOWS.bat
if ($LASTEXITCODE -ne 0) { throw 'SETUP thất bại. Xử lý lỗi cài đặt trước khi chạy game.' }
.\RUN.bat
```

Chỉ chạy RUN khi SETUP báo `Setup complete.` và trả mã `0`. SETUP chuẩn bị thư viện Python và asset viewer; RUN không tự cài các thành phần này. Xem [phần cài đặt lần đầu](#phan-0) để chuẩn bị model/camera nếu dùng physical.

**Các lần sau, khi môi trường đã được cài thành công**, chọn một lệnh RUN dưới đây tại thư mục repo:

| Lệnh | Môi trường |
|---|---|
| `.\RUN.bat` | Simulation FR3 + Pygame + viewer, mặc định |
| `.\RUN.bat --sim` | Chọn simulation tường minh |
| `.\RUN.bat --board-only` | Bàn 2D, không physics/camera/robot/viewer |
| `.\RUN.bat --virtual` | Alias của `--board-only`; không có nghĩa là bật simulator |
| `.\RUN.bat --physical` | Camera + controller + mirror; ban đầu read-only |
| `.\RUN.bat --robot` | Alias của `--physical` |
| `.\RUN.bat --no-viewer` | Giữ môi trường đã chọn, không mở viewer |
| `.\RUN.bat --physical --recalibrate-camera` | Yêu cầu calibration camera tương tác |
| `.\RUN.bat --simulation-profile fast` | Phát simulation nhanh hơn, vẫn giữ physics/checks |
| `.\RUN.bat --viewer-port 8090 --telemetry-port 8770` | Đổi cổng local |
| `.\RUN.bat --help` | Xem CLI, không mở phần cứng |

Sau SETUP có thể gọi trực tiếp Python của môi trường:

```powershell
.\.venv312\Scripts\python.exe main.py --board-only
```

`RUN.bat` ưu tiên `.venv312`, rồi `.venv`, rồi Python/py trong PATH. `XIANGQI_NO_PAUSE=1` bỏ chờ ở cuối script. Không ghép `--physical` với `--virtual`, hay `--simulation-profile` với physical/game-only.

### 4.2. Chơi bằng robot thật

1. Dùng capsule do team chuẩn bị cho bộ thiết bị, hoặc hoàn tất SETUP/model nếu chạy source. Kết nối camera/controller và xác minh bộ teaching/calibration đúng setup.
2. Xếp đủ 32 quân khai cuộc, mở `START.bat` và chọn **Robot thật**. Với source, dùng `RUN.bat --physical`.
3. Camera đọc frame mới và xác nhận bàn. Calibration đã lưu có thể dùng lại nếu setup không đổi; dùng `--recalibrate-camera` khi cần chấm lại.
4. Kết nối ban đầu chỉ đọc. Sau khi người vận hành xác nhận tool/frame, khoảng hở, vùng chuyển động, tốc độ và E-stop, nhấn **F9**, rồi **F10** trong khoảng xác nhận của UI để xin bật motion.
5. Thiếu telemetry mới/idle, board confirmation hoặc còn recovery/pending thì bị từ chối. Không đổi số calibration hoặc tắt guard để vượt gate.
6. Di quân, rút tay, dùng SPACE/luồng xác nhận đang được hỗ trợ; theo dõi hậu kiểm và FEN trước khi đi nước tiếp.

Bộ profile mặc định hiện đọc `calibration/physical_teaching_points_user0.json` với robot base/user 0. Không tự lấy lại teaching/WObj của controller trong đường này. Đây là dữ liệu của setup đã ghi, không phải bộ tọa độ dùng chung cho mọi robot. Đối chiếu [ROBOT_FRAME_BASE_ONLY.md](docs/ROBOT_FRAME_BASE_ONLY.md) và [BRD_XY_CALIBRATION.md](docs/BRD_XY_CALIBRATION.md).

### 4.3. Phím và nút

Phím chỉ có tác dụng khi profile/trạng thái cho phép. Dùng nhãn và thông báo trên UI để xác nhận hành động hiện tại.

| Điều khiển | Chức năng |
|---|---|
| Chuột | Chọn quân/đích trong profile cho nhập chuột; bấm nút/menu |
| SPACE | Xác nhận nước người bằng camera khi đang ở lượt/phân hệ phù hợp |
| V / Continue | Quét, đồng bộ hoặc retry cùng nước đang chờ theo trạng thái; không phải bỏ qua lỗi |
| F4 | Quét toàn bàn; thay đổi nhiều ô có thể yêu cầu xác nhận lượt |
| 1 / 2 | Xác nhận Đỏ/Đen khi UI đang chờ xác nhận lượt sau rescan |
| F2 | Xin về launcher/đổi mode; giữ stop/disposal barrier |
| O | Mở cửa sổ người Đen trong mode 2 người + robot |
| F5 | Yêu cầu thử AI khi phiên không có lỗi đồng bộ đang chặn |
| F6 / F7 / F8 | Self-play liên tục / từng bước / dừng, theo mode hiện tại |
| F9 → F10 | Xin và xác nhận bật quyền physical motion; không tự xử lý controller fault |
| Ctrl+F8 | Xác nhận đã kiểm tra arm/kẹp theo luồng read-only stop recovery |
| Ctrl+F9 | Xác nhận controller đã được tắt trên pendant trong nhánh mất disable ACK |
| F12 | Xin xóa phiên lỗi sau đối soát và kiểm tra dừng; không reset controller |
| T | Vào/ra test gắp–thả; chọn quân rồi ô trống, không cập nhật FEN ván |
| H | Hover/đo target theo capability của mode |
| Y | Thử lại điểm gắp của cùng nước, khi trạng thái cho phép |
| M | Emergency camera/client mode; không phải phím tắt vượt motion gate |
| Z | Hoàn tác history khi được phép; không phải physical rollback của nhánh khác |
| SURRENDER / NEW GAME | Đầu hàng / xin tạo ván mới qua lifecycle hiện tại |

Không giữ mô tả E/A/X của rollback-arm cũ: nhánh này dùng session/history/recovery khác. Các phím nguy hiểm hoặc không phù hợp có thể bị chặn trong lúc worker đang sở hữu robot.

### 4.4. Hoàn tác và khôi phục

`undo_round()` dùng history snapshot trong RAM. Không có transaction arm tự trả hai nước như bản rollback cũ. Không xem Z là lệnh di chuyển quân thật; physical/history change có gate riêng và yêu cầu đối soát bàn khi cần. Xem panel recovery thay vì tiếp tục đi trên một bàn chưa khớp FEN.

Mỗi lần chạy/chọn ván là một khai cuộc mới. Journal vẫn giữ biên nhận và recovery của lệnh phần cứng chưa giải quyết; F2/New Game/restart không phải lệnh xóa hậu quả của motion đang dở.

Đóng cửa sổ máy chủ/game chính hoặc Ctrl+C hiện hỏi **Thoát / Ở lại**. Xác nhận Thoát đóng phần mềm ngay theo implementation của nhánh, không phát lệnh đến robot/kẹp và không hoàn tất giao dịch đang dở; journal đã ghi được giữ nguyên. Không coi việc đóng ứng dụng là bằng chứng robot đã dừng.

---

<a id="phan-5"></a>
# PHẦN 5: AI CHESS ENGINE & CÁC CHẾ ĐỘ CHƠI

### 5.1. Các mode

| Mode | Người/AI | Virtual | Physical |
|---|---|---|---|
| `HUMAN_VS_ROBOT` | Người Đỏ, AI Đen | Chuột + adapter virtual | Camera + robot nếu được enable |
| `HUMAN_VS_HUMAN` | Hai người, không AI | Hai bên nhập trên bàn ảo | Profile này ép về virtual; dùng mode riêng 2 NGƯỜI + ROBOT khi cần robot thực hiện |
| `ROBOT_VS_ROBOT` | AI cả hai màu | Cùng executor mô phỏng | Một robot thực hiện hai màu; chỉ khi đủ quyền/gate |
| `HUMAN_VS_HUMAN_ROBOT` | Hai người chọn nước, không AI | Một executor mô phỏng, hai cửa sổ | Một robot thực hiện hai màu; camera/stop/recovery gate giữ nguyên |

### 5.2. Hai người chọn nước, một robot thực hiện

Chọn **MÔ PHỎNG 3D** hoặc **ROBOT THẬT**, rồi **2 NGƯỜI + ROBOT**. Máy chủ chơi Đỏ; nhấn **O / MỞ NGƯỜI ĐEN** để mở cửa sổ Đen hoặc chọn **VÀO PHÒNG / NGƯỜI ĐEN** và nhập mã 6 ký tự. Hai cửa sổ cùng máy, không chơi qua LAN/Internet; client không sở hữu camera/controller.

Cả hai màu chọn nước bằng chuột, máy chủ thực hiện và commit sau xác minh. Mất kết nối thì khóa nước mới; không phát lại yêu cầu đã gửi. Mode này không có AI, SPACE đi tay, emergency, rollback hay test gắp. Xem [TWO_HUMAN_ROBOT_MODE.md](docs/TWO_HUMAN_ROBOT_MODE.md).

### 5.3. Engine và thời gian nghĩ

Đường local dùng source Moonfish. `AIController` hỗ trợ cấu hình LOCAL/CLOUD/HYBRID; lựa chọn difficulty và backend phải được đối chiếu với code/menu thực tế. Không mặc định cho rằng mọi cấp độ hay model policy đều đang được launcher dùng.

Engine chạy ngoài luồng UI, kết quả gắn với phiên/lượt. Kết quả cũ sau đổi mode, rescan hoặc reset không được tự cấp quyền phát một nước mới. Lỗi engine và lỗi thực thi là hai nhóm lỗi riêng; đọc `ENGINE_FAILED`, pending move và recovery để quyết định retry.

### 5.4. Playback simulation

`detailed` mặc định phát chậm để quan sát; `fast` thay tốc độ phát nhưng giữ physics, samples và collision checks. Profile không đổi tốc độ robot thật. Tham khảo [SIMULATION_PLAYBACK.md](docs/SIMULATION_PLAYBACK.md); chưa có cam kết FPS/thời gian hoàn tất trên mọi máy.

---

<a id="phan-6"></a>
# PHẦN 6: CAMERA, TỌA ĐỘ VÀ CALIBRATION

### 6.1. Ba dữ liệu khác nhau

| Dữ liệu | Chức năng |
|---|---|
| `perspective.npy` | Biến đổi ảnh camera sang giao điểm bàn; phụ thuộc camera/bàn hiện tại |
| Intrinsics/profile vision | Dùng khi mode height/ring/top-face tương ứng được chọn; phụ thuộc ống kính/resolution/focus |
| R1–R4 và board/contact calibration | Liên hệ lưới/board metric với robot base; không được suy ra chỉ từ confidence ảnh |

Camera/bàn xê dịch thì kiểm tra lại perspective; đổi camera, focus hoặc độ phân giải thì kiểm tra lại intrinsics. SETUP không tự đo các sai số này.

### 6.2. Hệ tọa độ

```text
image_px → board_grid (col,row) → board_metric → robot_base → tool target
```

Board logic là cột/hàng; SDK dùng mm/deg cho pose. Kinematics/scene có thể dùng m/rad ở ranh giới riêng; phải chuyển đơn vị rõ ràng. Viewer có phép chuyển robot-base sang trục Three.js riêng, không lấy trực tiếp XYZ màn hình làm tọa độ robot.

R1 `(col0,row0)`, R2 `(8,0)`, R3 `(8,9)`, R4 `(0,9)` là giao điểm lưới ngoài cùng, không phải mép tấm bàn. Đường board XY hiện có SE(2) và dữ liệu mặt bàn/Z riêng; không trộn với bilinear/offset của đường physical donor hoặc với scene nominal.

### 6.3. Visual correction và độ lệch

Có nhiều mode trong `src/vision/visual_pick_modes.py`, cùng các cờ height/ring/top-face. Chọn theo config và nhãn/log runtime; không suy ra nhánh này đang dùng cùng mặc định PvP-foot của `feat/player-vs-robot`.

Bù XY, offset tool, độ cao và orientation là các vấn đề độc lập. Không tăng ngưỡng confidence/offset hoặc sửa wrist angle theo phỏng đoán để làm một case chạy qua. Dùng [VISUAL_V2_INTEGRATION.md](docs/VISUAL_V2_INTEGRATION.md), [VISUAL_V2_MOTION_PROFILE.md](docs/VISUAL_V2_MOTION_PROFILE.md) và [geometry-measurement.md](docs/geometry-measurement.md).

### 6.4. Viewer physical và giới hạn safety

Physical viewer có thể hiển thị arm telemetry ngay cả khi board contact/Z chưa được đo. XY từ profile không chứng minh mặt bàn/Z hay vị trí tiếp xúc đã đúng. Badge unverified/preview phải được giữ đúng nghĩa. Mirror không kiểm tra an toàn đường thực tế và FEN32 đúng không giải quyết lỗi controller hoặc tool/user mismatch.

---

<a id="phan-7"></a>
# PHẦN 7: CẤU HÌNH, LƯU TRẠNG THÁI & API

### 7.1. Nguồn cấu hình

| Nguồn | Phạm vi |
|---|---|
| CLI | Môi trường, viewer/cổng, playback, recalibration, log |
| `SessionProfile` | Capability theo kiểu chơi, mouse/camera/AI/robot |
| `config.py` | Mặc định runtime, profile, đường model, tham số vận hành |
| `calibration/` và `shared/` | Artifact theo setup và geometry có provenance riêng |
| Biến môi trường | Các lựa chọn có khai báo thực sự trong config/launcher |

Các tên thường cần đối chiếu: `GAME_MODE`, `ROBOT_BACKEND`, `DRY_RUN`, `VISION_DEVICE`, `PHYSICAL_TEACHING_POINTS_FILE`, `BOARD_CALIBRATION_OFFSET_MM`, `ENGINE_TYPE`. CLI và session profile có thể ghi đè mặc định; đổi file config trong khi game còn chạy không bảo đảm module đã nạp được cập nhật.

Profile gripper hiện tại đã có lịch sử đổi dây. Mapping được đọc từ config; không dùng bảng DO1/DO0 trong tài liệu FR5 cũ cho setup này. Không đoán pulse hoặc đảo kênh dựa trên việc API trả 0.

### 7.2. Journal và projection

- `data/runtime/` chứa trạng thái phiên/biên nhận/outbox theo implementation của journal.
- Lưu trạng thái là một phần của transaction, không phải bằng chứng command vật lý đã hoàn tất.
- Sau commit, projection sang viewer/spectator có thể retry dữ liệu. Không retry arm để sửa projection.
- Phiên cũ được archive khi tạo phiên mới; pending command/recovery chưa giải quyết không được xóa âm thầm.

### 7.3. Spectator và credential

Spectator từ xa là tùy chọn. Credential lấy qua `XIANGQI_SIMULATION_TOKEN`; không cần credential này để chơi local/viewer. Không đưa token vào README, Git hay log. Xem [BRD_CREDENTIAL_CONFIGURATION.md](docs/BRD_CREDENTIAL_CONFIGURATION.md) và [simulation_api_guide.md](docs/simulation_api_guide.md).

---

<a id="phan-8"></a>
# PHẦN 8: KIỂM THỬ, LOG & XỬ LÝ LỖI

### 8.1. Kiểm thử tự động

Runtime requirements không bao gồm đầy đủ công cụ phát triển. Cài test tooling trong môi trường riêng rồi dùng runner của repo:

```powershell
.\.venv312\Scripts\python.exe -m pip install pytest pytest-xdist
$env:PATH = (Join-Path $PWD '.venv312\Scripts') + ';' + $env:PATH
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_simple_launch_sync.py
```

| Mục đích | Lệnh |
|---|---|
| Một subsystem | `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_session_modes.py` |
| Regression không slow | `.\tools\test_fast.ps1 -Mode Balanced` |
| Chạy riêng tests có marker serial | `.\tools\test_fast.ps1 -SerialOnly -Tests tests/unit/test_session_user_flows.py` |
| Viewer checks theo package | `npm run test:viewer` |

`pytest.ini` thu thập `tests/unit`; marker `hardware` luôn bị loại khỏi runner tự động, `slow` mặc định không chạy. Các script `tools/hardware_tests/` không phải unit tests và có thể gửi lệnh thật. Không tự chạy chúng trong quá trình review/tài liệu.

Không lấy con số tests PASS trong README/báo cáo cũ làm kết quả hiện tại. Mỗi báo cáo cần SHA, lệnh, môi trường và exit code. Review nhánh này chỉ áp dụng đúng snapshot trong báo cáo đính kèm, không phải chứng nhận toàn bộ khả năng phần cứng.

### 8.2. Nhật ký phiên

Với capsule, log game nằm ở `app/logs/<id-phien>/`, log lỗi launcher ở `state/launcher-error-*.log`. Với source, mỗi lần chạy tạo `logs/<id-phien>/` tại repo. Terminal in đường dẫn; đọc `errors.log` trước, rồi `run.log` và dữ liệu có cấu trúc theo [LOGGING.md](docs/LOGGING.md).

```powershell
.\RUN.bat --log-level DEBUG
.\RUN.bat --log-dir logs-review
```

Khi báo lỗi, ghi lại branch/HEAD, môi trường/mode, bước vừa thao tác, FEN/pending và log đúng phiên. Đừng chỉ dùng ảnh thanh status đã bị rút gọn.

### 8.3. Bảng xử lý nhanh

| Hiện tượng | Kiểm tra/bước tiếp theo |
|---|---|
| Source thiếu Python hoặc npm | Cài prerequisite, mở terminal mới, chạy SETUP lại |
| Source SETUP lỗi cài PyBullet | Đọc lỗi wheel/compiler; chưa được coi là setup thành công |
| Physical không khởi tạo vision | Kiểm tra đủ `best.pt`, hai ONNX, camera, providers và calibration |
| Viewer trống/lỗi module | Capsule: kiểm tra/giải nén lại ZIP đầy đủ; source: `npm ci --include=dev`. Xem `VIEWER_FAILED`, Ctrl+F5 |
| Viewer OFFLINE/board chưa khớp | Kiểm tra telemetry/bridge và trạng thái calibration; không sửa FEN để che lệch |
| Nhận nước nhưng robot chưa chạy | Kiểm tra pending, motion enable, controller/worker/binding và mã lỗi thực tế |
| RPC/GetControllerIP chập chờn | Kiểm tra kết nối theo [ROBOT_CONNECTION.md](ROBOT_CONNECTION.md); không bật motion khi link không ổn định |
| Controller main/sub có lỗi | Xử lý trên phần cứng theo quy trình vận hành; F12/new session không reset controller |
| 112/14 hoặc tiếp cận thất bại | Giữ receipt/log và setup; camera khớp không chứng minh joint branch/path an toàn |
| Kẹp không hoạt động | Đối chiếu cấu hình và wiring hiện tại; phản hồi RPC thành công không đo được hành trình ngàm |
| Bàn không khớp FEN | Dừng/đối soát qua V/F4 hoặc F12 khi đủ điều kiện; không phát lại command đang completion-unknown |
| Quét được 32 quân nhưng vẫn recovery | Kiểm tra stop/idle, controller fault, tool/user và pending receipts riêng |

### 8.4. Giới hạn hiện tại

`KNOWN_ISSUES.md` giữ các vấn đề còn mở, gồm startup/recovery/controller, tool context, xác minh đường physical sau mất điện, calibration mặt bàn và nghiệm thu gameplay. Các ghi nhận controller/cáp là quan sát lịch sử theo setup, không phải chẩn đoán cho mọi lỗi mới. Cần bằng chứng hiện tại trước khi quy nguyên nhân cho phần cứng hay phần mềm.

---

<a id="phan-9"></a>
# PHẦN 9: FAQ & TÀI LIỆU THAM CHIẾU

### Q1. Vì sao `--virtual` không mở robot 3D?

Đây là alias game-only của dự án. Dùng `RUN.bat` hoặc `--sim` để mở simulation/viewer.

### Q2. Clone rồi chạy SETUP đã đủ chơi bằng camera chưa?

Chưa. Checkpoint không nằm trong Git; phải bổ sung model, camera và calibration tương thích. SETUP chỉ chuẩn bị dependency/asset viewer.

### Q3. Cần tải Pikafish/NNUE không?

Không cho đường local mặc định Moonfish. Các đoạn README cũ yêu cầu Pikafish không áp dụng cho nhánh này.

### Q4. Physical có tự bật motor khi mở game không?

Không theo hợp đồng khởi tạo hiện tại. F9/F10 và các gate camera/telemetry/recovery điều khiển quyền motion. Chưa có quyền không có nghĩa là setup đã được nghiệm thu an toàn.

### Q5. Robot vs Robot là hai robot thật?

Không. Hai màu AI được điều phối qua cùng một executor/FR3 trong phiên đó.

### Q6. Có PvP qua phòng mạng hoặc hai người dùng robot thật chưa?

`HUMAN_VS_HUMAN` vẫn virtual. Chọn `2 NGƯỜI + ROBOT` để dùng mode riêng có máy chủ Đỏ/cửa sổ Đen, simulation hoặc physical; phòng chỉ localhost, không LAN/Internet.

### Q7. Z có tự trả quân thật không?

Không. Đây là history undo có giới hạn theo trạng thái; không phải transaction rollback-arm hay manual-camera rollback của nhánh khác. Physical phải qua các gate đối soát hiện hành.

### Q8. F12 có chữa lỗi controller/collision không?

Không. F12 phục hồi trạng thái ứng dụng sau kiểm tra cần thiết. Controller fault, tool/frame và đường cơ khí phải được xác minh riêng.

### Q9. Dùng được offline không?

Capsule dùng engine local, model và viewer asset đi kèm; không cần tải dependency khi sử dụng. Máy build cần mạng để chuẩn bị bộ phát hành. Spectator/cloud là tính năng riêng cần dịch vụ bên ngoài; launcher capsule mặc định LOCAL và không mang credential.

### Q10. Tài liệu nào cần đọc tiếp?

| Chủ đề | Tài liệu |
|---|---|
| Khởi động và CLI | [START_PROJECT.md](docs/START_PROJECT.md) |
| Luồng game/mode/Three.js | [GAME_MODES_AND_THREEJS_CODE_FLOW_20261023.md](docs/GAME_MODES_AND_THREEJS_CODE_FLOW_20261023.md) |
| Context và ranh giới module | [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), [REPO_MAP.md](REPO_MAP.md) |
| Log và mã lỗi | [LOGGING.md](docs/LOGGING.md) |
| Kết nối controller | [ROBOT_CONNECTION.md](ROBOT_CONNECTION.md) |
| Robot-base frame | [ROBOT_FRAME_BASE_ONLY.md](docs/ROBOT_FRAME_BASE_ONLY.md) |
| Board XY và mặt bàn | [BRD_XY_CALIBRATION.md](docs/BRD_XY_CALIBRATION.md) |
| Credential spectator | [BRD_CREDENTIAL_CONFIGURATION.md](docs/BRD_CREDENTIAL_CONFIGURATION.md) |
| Calibration/vision | [VISUAL_V2_INTEGRATION.md](docs/VISUAL_V2_INTEGRATION.md) |
| GPU camera | [CAMERA_MONITOR_GPU_FIX_20261013.md](docs/CAMERA_MONITOR_GPU_FIX_20261013.md) |
| Playback | [SIMULATION_PLAYBACK.md](docs/SIMULATION_PLAYBACK.md) |
| Chất lượng/giới hạn | [CURRENT_STATE.md](CURRENT_STATE.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md) |

Các thư mục `reports/`, `plans/` và tài liệu có ngày trong tên chứa cả bằng chứng lịch sử. Luôn đối chiếu SHA và phạm vi kiểm chứng trước khi sử dụng làm hướng dẫn cho phần cứng hiện tại.
