# XIANGQI ROBOT CỜ TƯỚNG VIP — SPECIFICATION DOCUMENT

> **Tài liệu kỹ thuật đầy đủ cho hệ thống Robot chơi Cờ Tướng tự động**  
> Phiên bản: 2.2 | Cập nhật: 2026-03-14

---

## 📋 **TỔNG QUAN HỆ THỐNG**

### **Hệ thống là gì?**
Đây là một hệ thống robot tự động chơi cờ tướng (Xiangqi), kết hợp:
- 🤖 **Robot cánh tay FR5** - Gắp và di chuyển quân cờ vật lý
- 📷 **Camera + YOLO AI** - Nhận diện nước đi của người chơi
- 🧠 **Chess Engine** - Tính toán nước đi tốt nhất (Cloud + Local)
- 🎮 **Pygame UI** - Hiển thị bàn cờ ảo và trạng thái game

### **Hệ thống có thể làm gì?**
✅ Chơi cờ tướng với người thật (Robot cầm quân Đen)  
✅ Tự động nhận diện nước đi qua camera  
✅ Tính toán nước đi tốt nhất bằng AI  
✅ Điều khiển robot gắp/đặt quân chính xác ±0.1mm  
✅ Truyền hình trực tiếp lên web (tuongkydaisu.com)  
✅ Rollback nước đi (phím Z)  
✅ Manual override khi camera lỗi  

### **Công nghệ sử dụng**
| Thành phần | Công nghệ |
|------------|-----------|
| **Ngôn ngữ** | Python 3.8+ |
| **Robot** | Fairino FR5 (6-DOF) |
| **Vision** | YOLO11 (Occupancy model) |
| **AI Engine** | Pikafish (UCI) + Cloud API |
| **UI** | Pygame |
| **Camera** | OpenCV (USB/Built-in) |

### **Kiến trúc tổng thể**
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Camera    │────▶│  YOLO Model  │────▶│  Snapshot   │
│  (OpenCV)   │     │  (best.pt)   │     │  Detector   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                                                 ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Pygame    │◀────│  Game State  │◀────│   Xiangqi   │
│     UI      │     │   (FEN)      │     │    Rules    │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                           ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Robot     │◀────│ AI Controller│◀────│Cloud/Local  │
│    FR3      │     │  (Hybrid)    │     │   Engine    │
└─────────────┘     └──────────────┘     └─────────────┘
```

---

# PHẦN 0: HƯỚNG DẪN CÀI ĐẶT DÀNH CHO NGƯỜI MỚI (STANDALONE REPO)
Repository này có thể hoạt động ĐỘC LẬP không cần phụ thuộc vào mã nguồn gốc. Để chạy được hệ thống, bạn cần làm đúng 3 bước:

[BƯỚC 1] CÀI ĐẶT THƯ VIỆN PYTHON
```bash
pip install -r requirements.txt
# hoặc: pip install pygame numpy opencv-python requests ultralytics
```

[BƯỚC 2] TẢI MÔ HÌNH NHẬN DIỆN BÀN CỜ (YOLO)
File trọng số AI đã được đính kèm sẵn trong mã nguồn tại: `models/best.pt`.

[BƯỚC 3] TẢI CHESS ENGINE LOCAL (TÙY CHỌN - DÀNH CHO OFFLINE)
Mặc định hệ thống sẽ sử dụng Cloud Engine API để tính toán. Tuy nhiên, để dự phòng khi mất mạng, bạn nên trang bị thêm Pikafish Local.
Vì file này rất nặng nên KHÔNG ĐƯỢC PUSH lên Git. Bạn tự tải như sau:
1. Tải **Pikafish 2026-01-02 AVX2** (cho Windows/Linux) từ: [Official Pikafish Releases](https://github.com/official-pikafish/Pikafish/releases)
   👉 Giải nén file 7z vừa tải thẳng vào thư mục: `pikafish/`
2. Tải **Neural Network (.nnue)** trực tiếp từ API: [Pikafish NNUE Latest](https://pikafish.org/api/nnue/download/latest)
   👉 Bỏ riêng file `pikafish.nnue` tải được vào thư mục `pikafish/`.

---

# PHẦN 1: CẤU TRÚC THƯ MỤC CỐT LÕI

Dự án được tổ chức theo kiến trúc Modular, chia nhỏ logic theo từng domain con:

```text
Dự-án-gốc/
├── main.py                   # Điểm vào chính của chương trình (Game Loop)
├── config.py                 # File cấu hình trung tâm (Camera, Robot, Path, Constants)
├── RUN.bat                   # Script khởi động nhanh toàn bộ hệ thống
├── notes.md                  # Tài liệu hướng dẫn & kiến trúc hệ thống
├── perspective.npy           # Dữ liệu ma trận góc nhìn Camera (Calibrate data)
│
├── models/                   # Chứa trọng số mô hình AI nhận dạng hình ảnh
│   └── best.pt               # File weights YOLO26 đã train (nhận diện 1 class)
│
├── pikafish/                 # Thư mục chứa engine AI Cờ Tướng (Dự phòng Offline) 
│   ├── pikafish.nnue         # Mạng Neural Network của Pikafish
│   └── Windows/              # Thư mục con chứa file thực thi exe của Pikafish
│
├── src/                      # MÃ NGUỒN CHÍNH (CORE SOURCE CODE)
│   ├── api/                  # Module Giao tiếp Mạng & API
│   │   └── simulation_client.py # Client đồng bộ bàn cờ trực tiếp lên tuongkydaisu.com
│   │
│   ├── ai/                   # Module Trí Tuệ Nhân Tạo
│   │   ├── pikafish_engine.py# Bộ giao tiếp biên dịch lệnh UCI trực tiếp với file Exe (Local)
│   │   ├── cloud_engine.py   # Kết nối REST API lên tuongkydaisu.com (Cloud) 
│   │   └── ai_controller.py  # Wrapper quản lý tầng cao giao tiếp với Game (Worker Thread)
│   │
│   ├── core/                 # Module Xử lý Thể thức & Logic Game
│   │   ├── xiangqi.py        # Trái tim của Luật cờ tướng (Move validation, Check/Checkmate)
│   │   ├── fen_utils.py      # Chuyển đổi qua lại giữa mảng Board Array và chuỗi FEN chuẩn
│   │   └── game_state.py     # Quản lý vòng đời trạng thái Game (State Management)
│   │
│   ├── hardware/             # Module phần cứng & thiết bị ngoại vi
│   │   ├── hardware_manager.py# Khởi tạo tổng hợp An toàn cho Robot, AI, Camera
│   │   ├── robot_VIP.py      # Bộ thư viện điều khiển các khớp tay máy Fairino FR5
│   │   └── robot_sdk_core.*  # Các file mã C/Python biên dịch cấp thấp của hãng Fairino
│   │
│   ├── ui/                   # Module Giao diện người dùng đồ họa
│   │   ├── board_renderer.py # Vẽ và cập nhật Game Board lên màn hình qua Pygame
│   │   └── input_handler.py  # Lắng nghe & Xử lý sự kiện Phím/Chuột từ người dùng
│   │
│   └── vision/               # Module Thị giác máy tính (Computer Vision)
│       ├── calibrate_camera.py  # Module căn chỉnh góc tọa độ bàn cờ
│       ├── camera_monitor.py    # Chạy luồng nền xả Queue OpenCV để lấy frame thời gian thực
│       └── snapshot_detector.py # So sánh điểm khác biệt 2 snapshot để xuất ra nước cờ
│
└── tests/                    # Thư mục Test kỹ thuật
    └── test_*.py             # Kịch bản test độc lập từng thành phần (Mocking)
```

> [!WARNING] LƯU Ý VỀ CÁC FILE ĐẶC BIỆT (TUYỆT ĐỐI KHÔNG ĐƯỢC XÓA TRONG SUỐT QUÁ TRÌNH LÀM VIỆC):
> - **`.keep` (nằm tại `pikafish/.keep`)**: Git mặc định sẽ tàng hình/bỏ qua các thư mục nếu nó rỗng. File `.keep` đóng vai trò là "mỏ neo", bắt buộc Git phải giữ lại vỏ thư mục `pikafish/` này trên kho lưu trữ đám mây (đỡ phải tạo folder khi clone repo mới về).
> - **`__init__.py` (nằm trong mọi thư mục con của `src/` và `tests/`)**: Dù đây là các file trống `0 KB`, nhưng chúng là "Thẻ căn cước" hệ thống bắt buộc của ngôn ngữ Python. Nó cho phép Python hiểu các thư mục này là một gói thư viện (Package). Nếu lỡ tay xóa đi, toàn bộ lệnh kết nối chéo giữa các tầng như `from src.core import...` sẽ lập tức báo lỗi file không tồn tại và làm ứng dụng sập.

---

# PHẦN 2: KIẾN TRÚC TỔNG THỂ & LUỒNG GAME

### 2.1. LUỒNG GAME

  Khởi động → FEN bộ nhớ = vị trí ban đầu

  [Lượt Người]
    1. Di chuyển quân thật trên bàn
    2. Bấm SPACE
    3. Camera chụp T2 → YOLO detect → so sánh với T1 (FEN bộ nhớ)
    4. Phát hiện nước đi (src→dst) → validate luật cờ
    5. Cập nhật FEN bộ nhớ

  [Lượt AI]
    1. Gửi FEN hiện tại cho AIController
    2. Ưu tiên gọi Cloud Engine API (tuongkydaisu.com) để lấy nước đi tốt nhất
    3. Tự động Fallback sang Local Pikafish nếu Cloud gặp sự cố (Lỗi mạng/Timeout)
    4. Nhận kết quả và ra lệnh cho Robot thực hiện thao tác gắp nhả (src/hardware/robot_VIP.py)
    5. Cập nhật FEN bộ nhớ → chụp T1 baseline mới
    6. Quay lại lượt Người

  [Rollback — phím Z]
    → Khôi phục toàn bộ state (board, FEN, T1 baseline) về trước SPACE vừa bấm

### 2.2. BOARD & FEN

  Board lưu dạng list 10x9: board[row][col] = "r_P", "b_K", "."
  FEN string dùng trực tiếp cho Pikafish (gửi qua UCI: "position fen ...")

  MAPPING QUÂN CỜ (ARRAY → FEN):
    r_K→K   b_K→k
    r_A→A   b_A→a
    r_E→B   b_E→b   (Elephant = Bishop)
    r_N→N   b_N→n
    r_R→R   b_R→r
    r_C→C   b_C→c
    r_P→P   b_P→p

### 2.3. NHẬN DIỆN YOLO (1-CLASS OCCUPANCY MODEL)

  Chỉ detect "có quân cờ" hay "ô trống" (1 class duy nhất).
  Bộ nhớ FEN đã biết quân gì ở đâu → không cần YOLO nói màu/loại.

  KẾT QUẢ TRAINING YOLO26:
    Model:      yolo26m.pt | 80 epochs | imgsz=640
    Precision:  95.5%  |  Recall: 99.2%  |  mAP50: 95.4%
    Weights:    runs/detect/chess_vision/yolo26_occupancy_run/weights/best.pt

### 2.4. CÁC RỦI RO & GIẢI PHÁP

- **[R1]** YOLO nhấp nháy → Pattern filter xử lý (Recall 99.2%, ít xảy ra)
- **[R2]** Xếp bàn cờ ban đầu sai → Xếp đúng chuẩn
- **[R3]** Perspective calibrate sai → Bấm V để calibrate lại
- **[R4]** Ăn quân (ambiguous) → Blind Capture Resolution (pixel absdiff)
- **[R5]** Bấm SPACE trước khi đi xong → Bỏ qua, hiển thị thông báo
- **[R6]** Khi ăn quân, YOLO detect quân đỏ tại ô đích → occupancy không đổi
  👉 Đã fix bằng Loại 3 dst_candidates_capture_stable (xem Phần 3.4.3)
- **[R7]** Lỗi MoveCart 101 khi go_to_home_chess() làm robot.connected=False sai
  👉 Đã fix: tách `connect()` và `go_to_home_chess()` thành 2 try riêng

### 2.5. PHÍM TẮT

- `SPACE` → Chụp T2 snapshot, detect nước đi người chơi
- `Z` → Rollback về trước SPACE vừa bấm (undo 1 nước)
- `Q` → Thoát cửa sổ camera

### 2.6. CHECKLIST

  [x] Train YOLO26 (Precision 95.5%, Recall 99.2%)
  [x] Chuyển board sang FEN string
  [x] Tích hợp Pikafish engine
  [x] Phím SPACE để chụp snapshot
  [x] Xử lý pattern di chuyển thường + ăn quân (Blind Capture Resolution)
  [x] Chỉnh PICK_Z/PLACE_Z (PICK_Z=183, PLACE_Z=190 — cập nhật 2026-03-06)
  [x] Pikafish config (PIKAFISH_EXE, PIKAFISH_NNUE, PIKAFISH_THINK_MS)
  [x] Tải Pikafish 2026-01-02
  [x] Rollback (phím Z)
  [x] robot_VIP.py — Tool DO0
  [x] Tách file logic khỏi main.py vào kiến trúc Modular src/
  [x] Fix robot.connected bị set False sai khi go_to_home_chess lỗi
  [x] Fix snapshot_detector: detect ăn quân khi YOLO thấy quân đỏ tại ô đích
  [x] Thiết kế RUN.bat — double-click để chạy, tự động check thư viện
  [x] Khắc phục tay máy bị Singularity (Lỗi 101/14/112) bằng Teaching Points R1-R4 + Bilinear Interpolation
  [x] Implement Bilinear Interpolation với độ chính xác ±0.1mm từ 4 góc teaching points
  [x] Tự động tính CELL_SIZE từ teaching points thực tế thay vì hardcode
  [x] Hỗ trợ Bilinear Interpolation: Ưu tiên teaching points trực tiếp, nội suy 2D cho vị trí khác
  [x] Gỡ bỏ yêu cầu bấm SPACE tạo baseline lần 2 sau lượt AI (Auto Snapshot)
  [x] Tích hợp bộ thư viện Robot SDK `robot_sdk_core.*` vào module phần cứng `src/hardware/`
  [x] Tích hợp API Simulation của tuongkydaisu.com (Truyền real-time FEN lên xem trên web)
  [ ] Xác định và lưu điểm HOMECHESS lên bộ nhớ Robot để sửa lỗi err=143
  [ ] Verify bàn cờ lúc bắt đầu game (tùy chọn)

---

# PHẦN 3: TÀI LIỆU CÁC MODULE (CHI TIẾT THEO THƯ MỤC)
  
### 3.1. MODULE CORE (`src/core/`)
Đảm nhiệm logic cờ và lưu trữ trạng thái Game. Không phụ thuộc Pygame.

#### 3.1.1. `xiangqi.py`
Chứa toàn bộ "Luật Cờ Tướng" (Game Rules) cốt lõi của hệ thống.
EXPORT:
  - `initial_board`: Mảng 2D (10x9) định nghĩa vị trí quân cờ lúc bắt đầu.
  - `is_valid_move(src, dst, board, color)`: Trái tim của file. Validate quy tắc di chuyển cho từng loại quân cờ (Xe đi thẳng, Mã đi chữ L có cản, Pháo ăn qua ngòi, Tướng không xuất tướng...).
  - `is_king_in_check(color, board)`: Kiểm tra trạng thái "Bị chiếu tướng".
  - Zobrist Hashing (`get_zobrist_key`): Băm trạng thái bàn cờ hiện tại thành chuỗi mã hóa để tối ưu lưu vết bộ nhớ.

#### 3.1.2. `fen_utils.py`
Module thuần (pure functions), không có side effect, dễ test độc lập.
EXPORT:
  - `INITIAL_FEN`: FEN vị trí ban đầu chuẩn
  - `board_array_to_fen(board, color='r', move_number=1)` → str
  - `fen_to_board_array(fen)` → (board, color)

#### 3.1.3. `game_state.py`
Chứa class `GameState`. Quản lý toàn bộ vòng đời data, xóa bỏ biến Global.
Lưu giữ: `board`, `turn`, `current_fen`, `move_history`, `game_over`
Method chính: `update_fen_from_board()`, `reset_game()`, `handle_rollback()`, `process_human_move()`, `handle_game_over()`.

---

### 3.2. MODULE AI (`src/ai/`)
Giao tiếp với Engine cờ tướng bên ngoài. Hỗ trợ hệ thống HYBRID (Cloud first, Local fallback).

#### 3.2.1. `pikafish_engine.py`
Hoạt động như một "Phiên dịch viên" (UCI Bridge) trực tiếp nói chuyện với phần mềm Pikafish độc lập thông qua Subprocess. Đóng gói các tác vụ giao tiếp luồng (stdin/stdout).
CLASS PikafishEngine:
  - `start() / stop() / _atexit_cleanup()`: Quản lý vòng đời tiến trình con chạy `pikafish-avx2.exe`. Bắt buộc dùng `atexit` để dọn rác tiến trình khi luồng game chính bị sập, tránh rác RAM.
  - `board_to_fen()`: Tự động lật hệ tọa độ (Rank 0-9 Array của mình sang Rank 9-0 của UCI FEN).
  - `pick_best_move(board, color, movetime_ms)`: Gửi lệnh `go movetime...` để ép AI suy nghĩ, block luồng chờ kết quả `bestmove`, tự bóc tách chuỗi tọa độ `a0`-`i9` trả về index lưới game.

#### 3.2.2. `cloud_engine.py`
Module tương tác với REST API `tuongkydaisu.com/api/engine/bestmove`.
CLASS CloudEngine:
  - Không cần duy trì subprocess con.
  - Sử dụng chung phương thức `board_to_fen` và xử lý kết quả bóc tách chuỗi tọa độ (Ví dụ `"h2e2"`).
  - Cực kỳ tiết kiệm hiệu năng CPU / Memory cho thiết bị Local.

#### 3.2.3. `ai_controller.py`
Wrapper quản lý Pikafish engine và Cloud engine, tách logic UCI khỏi luồng chính.
CLASS AIController:
  - Nhận Local / Cloud engines instance và config module.
  - `pick_move(board_snapshot, color="b")`: Chạy Engine lấy nước cờ tốt nhất ở dạng chuỗi. Áp dụng cơ chế bắt lỗi Error Catching, tự động luân chuẩn chuyển quyền cho Local `PikafishEngine` nếu gọi `CloudEngine` thất bại (Timeout/Error). Chạy trong Thread phụ để không khóa render GUI.

---

### 3.3. MODULE HARDWARE (`src/hardware/`)
Thư viện quản lý thiết bị cứng và điều phối tín hiệu.

#### 3.3.1. `robot_VIP.py`
File điều khiển cánh tay robot FR5.

**HỆ THỐNG TỌA ĐỘ (BILINEAR INTERPOLATION - Độ chính xác tuyệt đối):**

Robot sử dụng **Bilinear Interpolation** từ 4 góc teaching points, tăng độ chính xác từ ±3-5mm xuống **±0.1mm**.

```python
# Bilinear Interpolation từ 4 góc R1, R2, R3, R4:
def board_to_pose_bilinear(col, row, z_height):
    # Tọa độ logic (0-8 cho col, 0-9 cho row)
    col_ratio = col / 8.0  # 0.0 → 1.0
    row_ratio = row / 9.0  # 0.0 → 1.0
    
    # Nội suy theo chiều ngang (col)
    top_x = r1[0] + (r2[0] - r1[0]) * col_ratio    # Hàng 0
    top_y = r1[1] + (r2[1] - r1[1]) * col_ratio
    bottom_x = r4[0] + (r3[0] - r4[0]) * col_ratio # Hàng 9
    bottom_y = r4[1] + (r3[1] - r4[1]) * col_ratio
    
    # Nội suy theo chiều dọc (row)
    final_x = top_x + (bottom_x - top_x) * row_ratio
    final_y = top_y + (bottom_y - top_y) * row_ratio
    
    return [final_x, final_y, z_height, Rx, Ry, Rz]
```

**Lưu ý quan trọng về hệ tọa độ:**
- Bàn cờ logic: col (0-8) = ngang, row (0-9) = dọc
- Robot FR5: X = dọc (trên-dưới), Y = ngang (trái-phải)
- Bilinear Interpolation tự động xử lý hoán đổi và méo hình học

**Ưu điểm:**
- ✅ Chính xác tuyệt đối ±0.1mm
- ✅ Tự động bù méo hình học bàn cờ
- ✅ Không phụ thuộc ánh sáng, góc camera
- ✅ Thích ứng với bàn cờ không vuông góc hoàn hảo
- ✅ Tự động tính CELL_SIZE từ teaching points thực tế

**CÁC HÀM CHÍNH:**
  - `connect()`: Kết nối robot qua RPC SDK, tự động load teaching points R1-R4
  - `_load_teaching_points()`: Đọc teaching points R1, R2, R3, R4 (bắt buộc có đủ 4 góc)
  - `_calculate_cell_sizes_from_corners()`: Tự động tính CELL_SIZE từ 4 góc thực tế
  - `_get_teaching_point_for_position()`: Map (col,row) → teaching point name
  - `board_to_pose()`: Chuyển (col,row) → (x,y,z) bằng Bilinear Interpolation
  - `board_to_pose_bilinear()`: Nội suy 2D từ 4 góc với độ chính xác ±0.1mm
  - `move_safe_pose()`: Di chuyển an toàn. Dùng MoveJ khi có teaching points, MoveCart khi không có
  - `move_to_extra_safe()`: Nâng lên độ cao an toàn (SAFE_Z) khi di chuyển xa
  - `go_to_home_chess()`: Về home bằng MoveJ (tránh Singularity)
  - `pick_at()` / `place_at()` / `place_in_capture_bin()` / `gripper_ctrl()`
  - `move_piece(s,d,capture)`: Hàm chính được main.py gọi

**HỆ THỐNG BILINEAR INTERPOLATION (Độ chính xác tuyệt đối):**

Hệ thống sử dụng **Bilinear Interpolation** từ 4 góc teaching points để tính toán vị trí chính xác:

1. **Teaching Points (Bắt buộc):**
   - Đọc R1, R2, R3, R4 từ robot controller khi `connect()`
   - Lưu cả pose (x,y,z,rx,ry,rz) và joint angles (j1-j6)
   - Tự động tính CELL_SIZE từ khoảng cách thực tế giữa 4 góc
   - Log: "📏 Tự động tính CELL_SIZE từ 4 góc"

2. **Bilinear Interpolation:**
   - Nội suy 2D từ 4 góc cho mọi vị trí (col, row)
   - Độ chính xác: **±0.1mm** thay vì ±3-5mm
   - Tự động bù méo hình học bàn cờ
   - Log: "🎯 Bilinear Interpolation (col,row) → X=..., Y=..."

3. **Ưu tiên Teaching Points trực tiếp:**
   - Nếu có teaching point cho vị trí cụ thể (R1, R2, R3, R4)
   - Dùng **MoveJ** với joint angles → Tránh Singularity ✅
   - Log: "📍 Dùng teaching point R2 cho (8,0)"

**Mapping Teaching Points:**
- R1 = (0,0) - Xe Đen Trái (gốc tọa độ): `X=-191.761, Y=255.212, Z=182.847`
- R2 = (8,0) - Xe Đen Phải (góc xa, dễ Singularity): `X=-187.582, Y=576.582, Z=187.760`
- R3 = (8,9) - Xe Đỏ Phải (góc xa, dễ Singularity): `X=164.929, Y=569.474, Z=184.730`
- R4 = (0,9) - Xe Đỏ Trái (ít Singularity hơn): `X=154.034, Y=248.179, Z=182.267`

**Xem hướng dẫn chi tiết:** `docs/teaching_points_guide.md`

#### 3.3.2. `robot_sdk_core.py` & `robot_sdk_core.c`
Bộ SDK điều khiển Robot nguyên bản do hãng Fairino cung cấp.
  - `robot_sdk_core.py`: File mã nguồn Python chứa toàn bộ giao thức mạng để nói chuyện với tụ điện điều khiển của tay máy FR5. Dùng XML-RPC (port 20003) để gửi lệnh và dùng TCP Socket (port 20004) để nhận dữ liệu thời gian thực. Định nghĩa sẵn cấu trúc dữ liệu khổng lồ `RobotStatePkg`.
  - `robot_sdk_core.c`: File mã C được sinh ra bởi công cụ Cython (biên dịch Python sang C). Phục vụ cho việc tăng tốc độ thực thi của SDK, giúp Python chạy tiệm cận tốc độ máy.

#### 3.3.3. `hardware_manager.py`
Chứa class `HardwareManager`. Điểm chạm kết nối thiết bị vật lý và trí tuệ nhân tạo.
Gói gọn: `FR3Robot`, `PikafishEngine`, `CameraMonitor`, `YoloSnapshotDetector`. Khởi tạo tất cả theo nguyên tắc bật thiết bị và dọn bộ nhớ tự động với `initialize_all()` và `cleanup()`.

---

### 3.4. MODULE VISION (`src/vision/`)
Thị giác máy tính. Tính toán góc camera và xuất tọa độ nước đi người dùng.

#### 3.4.1. `calibrate_camera.py`
Hiệu chỉnh perspective camera, click 4 góc bàn cờ để map kích thước lên mảng 2D.
Xuất ra Output là file: `perspective.npy` (ma trận 3x3 float32, M: pixel → grid).
Luồng: Tự động chạy khi khởi động game → Nếu có file cũ bấm 'S' để skip → Click 4 góc: Đen Trái, Đen Phải, Đỏ Phải, Đỏ Trái.

#### 3.4.2. `camera_monitor.py`
SINGLE CAMERA OWNER — Thread chạy ngầm thu hoạch hình ảnh liên tục.
FIX Lag Delay (2026-03-05): Dùng `cap.grab()` xả hàng đợi cũ của OpenCV để lấy chính xác tấm ảnh không trễ thời gian thực. Bỏ sleep() vì YOLO chạy đủ tốn CPU rồi.
API: `get_fresh_snapshot()` (blocking để phục vụ SPACE), `get_latest_frame_and_detections()` (non-blocking để debug/render).

#### 3.4.3. `snapshot_detector.py`
So sánh T1 (Baseline) và T2 (Sau khi đi) để đoán nước đi của người chơi.
Thuật toán chia ra thành 4 lớp độ ưu tiên. Tích hợp Blind Capture Resolution (Chụp ảnh và lấy absdiff để quét mảnh màu tìm thay đổi khi ăn quân).
Giải quyết lỗi loại 3: Ô đối phương T1=True & T2=True (Stable). Lấy ô đích nếu quân đỏ chèn lên đúng vị trí cũ mà occupancy không đổi.

---

### 3.5. MODULE UI (`src/ui/`)
Giao diện người dùng đồ họa bằng Pygame và trình quản lý sự kiện.

#### 3.5.1. `input_handler.py`
Điều phối tác vụ do người dùng tạo ra vào GameState và HardwareManager.
  - **Phím** (`SPACE` để chạy luồng Vision so sánh ảnh, `Z` để Rollback cả dữ liệu cờ lẫn ảnh Baseline gốc). Nếu vision thất bại, chặn đứng màn hình và bật mode Manual Override.
  - **Chuột** (Kéo thả Manual Override hoạt động độc lập không xài robot; Nút Surrender/New Game).

#### 3.5.2. `board_renderer.py`
Render giao diện bàn cờ Pygame màn hình 800x600. Vẽ Highlight ô đỏ/xanh biểu thị lỗi, nước đi gần nhất. Tính toán layout hiển thị Game Over Banner bằng Font.

---

### 3.6. MODULE API (`src/api/`)
Giao tiếp với nền tảng máy chủ trực tuyến.

#### 3.6.1. `simulation_client.py`
Xử lý các cuộc gọi REST API tới tuongkydaisu.com.
  - Quản lý REST Header (JWT Bearer Token lấy từ `config.py`).
  - Giao tiếp 3 Endpoints: Khởi tạo phòng chiếu trực tiếp (`create_match`), Đồng bộ FEN mỗi nước đi (`send_move_update_board`), Khai báo kết thúc tàn cuộc (`end_match`).
  - Giúp truyền hình trực tiếp cho khán giả theo dõi ván cờ của Máy và Robot qua mạng Internet (Một chiều).

---

### 3.7. CÁC FILE Lõi (ROOT FILES)

#### 3.7.1. `main.py`
Vòng lặp game chính (Game Loop 30FPS). Kiến trúc gọn nhẹ, đóng vai trò Controller trung tâm gọi Renderer, đưa Event vào InputHandler, và chạy Thread chờ AI đánh cờ. Hỗ trợ kích hoạt DRY_RUN tắt phụ thuộc phần mềm.

#### 3.6.2. `RUN.bat`
Script tự kích hoạt và xác minh Virtual Environment, khởi chạy luồng game và cảnh báo nếu thiếu Local AI.

#### 3.6.3. `perspective.npy`
File trọng số sinh ra bởi Calibrate Camera. Mất file → Hệ thống hỏng tính năng chụp ảnh AI. Mỗi khi calibrate xong thì sẽ tạo ra 1 file `perspective.npy` ghi đè lên file cũ

---

# PHẦN 4: HƯỚNG DẪN CHẠY HỆ THỐNG

### 4.1. KHỞI ĐỘNG NHANH (QUICK START)

**Cách 1: Dùng RUN.bat (Windows - Khuyến nghị)**
```bash
# Double-click file RUN.bat
# Script sẽ tự động:
# - Kiểm tra Python environment
# - Kiểm tra thư viện cần thiết
# - Cảnh báo nếu thiếu Pikafish
# - Khởi động game
```

**Cách 2: Chạy trực tiếp bằng Python**
```bash
python main.py
```

### 4.2. SETUP PHẦN CỨNG (LẦN ĐẦU SỬ DỤNG)

#### 4.2.1. Kết nối Robot FR5

**Bước 1: Chuẩn bị kết nối**
1. Bật nguồn robot FR5
2. Kết nối máy tính với robot qua Ethernet (có thể dùng USB to LAN adapter)
3. Cấu hình IP tĩnh cho adapter Ethernet:
   - IP address: `192.168.58.100`
   - Subnet mask: `255.255.255.0`
   - Default gateway: để trống (nếu dùng Wi-Fi song song)
4. Kiểm tra kết nối: `ping 192.168.58.2`
5. Kiểm tra IP robot trong `config.py`:
```python
ROBOT_IP = "192.168.58.2"  # Đổi nếu IP robot khác
```

**Bước 2: Test kết nối (Tùy chọn)**

Để test kết nối robot trước khi chạy game, mở Python console và chạy:

```python
# Mở terminal/cmd tại thư mục project, gõ: python
# Sau đó chạy từng dòng:
from src.hardware.robot_VIP import FR5Robot
import config

robot = FR5Robot()
robot.connect()  # Phải thấy "[ROBOT] ✅ Đã kết nối tới 192.168.58.2"
```

Nếu kết nối thành công, có thể chạy game bình thường. Nếu lỗi, kiểm tra lại IP và kết nối mạng.

**Lưu ý về kết nối mạng:**
- Nếu dùng USB to LAN adapter trên Windows 11, adapter sẽ được nhận diện bình thường
- Có thể dùng song song Wi-Fi (internet) và Ethernet (robot) mà không xung đột
- Không cần đặt Default Gateway cho Ethernet để tránh xung đột routing

#### 4.2.2. Dạy điểm R1 (BOARD_ORIGIN) - BẮT BUỘC

Điểm R1 là góc Đen-Trái của bàn cờ (tọa độ 0,0). Đây là điểm gốc để tính toán tất cả các ô khác.

**Tọa độ R1 thực tế:** `X=-191.761, Y=255.212, Z=182.847`

**Cách dạy điểm R1:**

1. Mở phần mềm điều khiển robot FR5 (Fairino Controller)
2. Chuyển sang chế độ Teaching (dạy tay)
3. Di chuyển tay robot đến vị trí:
   - Chính giữa ô góc Đen-Trái (col=0, row=0)
   - Đầu kẹp hướng xuống
   - Tọa độ tham khảo: `X=-191.761, Y=255.212, Z=182.847`
4. Lưu điểm này với tên: **`R1`** (chữ hoa, không dấu cách)
5. Khởi động lại chương trình

**Hệ thống sẽ tự động:**
- Đọc tọa độ R1 từ robot khi khởi động
- Ghi đè giá trị `BOARD_ORIGIN_X` và `BOARD_ORIGIN_Y` trong `config.py`
- Hiển thị log: `✅ Đã lấy gốc R1 thực tế: X=..., Y=...`

**Nếu không có R1:**
- Hệ thống sẽ báo lỗi: `Error getting teaching point R1`
- Robot sẽ bị vô hiệu hóa
- Game vẫn chạy được nhưng không có robot (chỉ có camera + UI)

**Lưu ý quan trọng:**
- Không cần cập nhật `config.py` thủ công
- Giá trị trong `config.py` chỉ là giá trị mặc định cho DRY_RUN
- Robot thật luôn đọc từ teaching point R1

#### 4.2.2b. Dạy điểm R2, R3, R4 (BẮT BUỘC - Bilinear Interpolation)

**⚠️ QUAN TRỌNG:** Hệ thống yêu cầu **đủ 4 góc R1, R2, R3, R4** để sử dụng Bilinear Interpolation với độ chính xác ±0.1mm.

**Dạy điểm R2 (Xe Đen Phải - col=8, row=0):**

**Tọa độ R2 thực tế:** `X=-187.582, Y=576.582, Z=187.760`

1. Mở phần mềm điều khiển robot FR5
2. Chuyển sang chế độ Teaching
3. Di chuyển robot đến:
   - Chính giữa ô góc Đen-Phải (col=8, row=0)
   - Đầu kẹp hướng xuống
   - Tọa độ tham khảo: `X=-187.582, Y=576.582, Z=187.760`
   - **QUAN TRỌNG:** Tránh tư thế Singularity (các khớp không thẳng hàng)
4. Lưu điểm này với tên: **`R2`** (chữ hoa, không dấu cách)

**Dạy điểm R3 (Xe Đỏ Phải - col=8, row=9):**

**Tọa độ R3 thực tế:** `X=164.929, Y=569.474, Z=184.730`

1. Di chuyển robot đến:
   - Chính giữa ô góc Đỏ-Phải (col=8, row=9)
   - Đầu kẹp hướng xuống
   - Tọa độ tham khảo: `X=164.929, Y=569.474, Z=184.730`
   - **QUAN TRỌNG:** Tránh tư thế Singularity
2. Lưu điểm này với tên: **`R3`** (chữ hoa, không dấu cách)

**Dạy điểm R4 (BẮT BUỘC - Xe Đỏ Trái - col=0, row=9):**

**Tọa độ R4 thực tế:** `X=154.034, Y=248.179, Z=182.267`

1. Di chuyển robot đến góc Đỏ-Trái (col=0, row=9)
2. Tọa độ tham khảo: `X=154.034, Y=248.179, Z=182.267`
3. Lưu điểm này với tên: **`R4`**

**Hệ thống Bilinear Interpolation:**
- Khi có đủ 4 góc → Dùng **Bilinear Interpolation** với độ chính xác ±0.1mm ✅
- Tự động tính CELL_SIZE từ khoảng cách thực tế
- Tự động bù méo hình học bàn cờ

**Kiểm tra sau khi dạy:**

Khởi động lại và xem log:
```
[ROBOT] 📍 Đang load teaching points...
[ROBOT]   ✅ Loaded R1: X=-191.761, Y=255.212, Z=182.847
[ROBOT]   ✅ Loaded R2: X=-187.582, Y=576.582, Z=187.760
[ROBOT]   ✅ Loaded R3: X=164.929, Y=569.474, Z=184.730
[ROBOT]   ✅ Loaded R4: X=154.034, Y=248.179, Z=182.267
[ROBOT] 📏 Tự động tính CELL_SIZE từ 4 góc:
[ROBOT]   CELL_SIZE_X = 40.17mm (ngang)
[ROBOT]   CELL_SIZE_Y = 38.79mm (dọc)
[ROBOT] ✅ Đã load 4 teaching points
[ROBOT] 🎯 Sử dụng Bilinear Interpolation cho tất cả vị trí
```

**Xem hướng dẫn chi tiết:** `docs/teaching_points_guide.md`

#### 4.2.3. Dạy điểm HOMECHESS (TÙY CHỌN - Khuyến nghị)

Điểm HOMECHESS là vị trí "về nhà" của robot sau mỗi nước đi, tránh che camera.

**Cách dạy điểm HOMECHESS:**

1. Mở phần mềm điều khiển robot FR5
2. Di chuyển robot đến vị trí:
   - Xa bàn cờ (không che camera)
   - Tránh tư thế Singularity (các khớp thẳng hàng)
   - Ví dụ: X=-72, Y=200, Z=278 (xem `config.py`)
3. Lưu điểm này với tên: **`HOMECHESS`** (chữ hoa, không dấu cách)

**Nếu không có HOMECHESS:**
- Hệ thống sẽ fallback về điểm IDLE (định nghĩa trong `config.py`)
- Vẫn hoạt động bình thường nhưng có thể che camera

#### 4.2.4. Hiệu chỉnh Camera (Calibration) - TỰ ĐỘNG KHI KHỞI ĐỘNG

Camera cần được hiệu chỉnh để chuyển đổi pixel → tọa độ bàn cờ.

**Khi nào cần calibrate:**
- Lần đầu chạy (bắt buộc)
- Khi di chuyển camera
- Khi thay đổi góc nhìn
- Khi file `perspective.npy` bị mất

**Cách calibrate:**

1. Khởi động game (`python main.py`)
2. Cửa sổ camera sẽ tự động hiện ra với thông báo calibration
3. **Nếu đã có file `perspective.npy` cũ:**
   - Bấm `S` để dùng lại (Skip)
   - Hoặc click 4 góc để calibrate lại
4. **Nếu chưa có file (lần đầu):**
   - Click lần lượt 4 góc bàn cờ theo thứ tự:
     1. Góc Đen-Trái (0,0)
     2. Góc Đen-Phải (8,0)
     3. Góc Đỏ-Phải (8,9)
     4. Góc Đỏ-Trái (0,9)
5. File `perspective.npy` sẽ được tạo tự động
6. Game sẽ tự động tiếp tục sau khi calibrate xong

**Lưu ý:**
- Click chính xác vào tâm góc bàn cờ
- Đảm bảo ánh sáng đủ
- Không có bóng đổ lên bàn cờ
- Không có phím `V` để calibrate giữa chừng (khác với mô tả cũ)

#### 4.2.5. Kiểm tra YOLO Model

Model YOLO đã được đính kèm sẵn trong repo:

```bash
# Verify model file tồn tại:
ls models/best.pt

# Test detection (optional):
python -c "from ultralytics import YOLO; model = YOLO('models/best.pt'); print('Model loaded OK')"
```

### 4.3. LUỒNG CHƠI GAME THỰC TẾ

**Bước 1: Khởi động hệ thống**
```bash
python main.py
# hoặc
py main.py
# hoặc double-click RUN.bat
```

**Bước 2: Calibrate camera (tự động)**
- Cửa sổ camera sẽ hiện ra
- Nếu đã có `perspective.npy`: Bấm `S` để skip hoặc click 4 góc để calibrate lại
- Nếu chưa có: Click 4 góc bàn cờ theo thứ tự (Đen-Trái → Đen-Phải → Đỏ-Phải → Đỏ-Trái)

**Bước 3: Xếp bàn cờ ban đầu**
- Xếp quân cờ theo vị trí chuẩn Xiangqi
- Đảm bảo quân cờ đặt chính giữa ô

**Bước 4: Hệ thống tự động chụp baseline**
- Sau khi calibrate xong, hệ thống tự động chụp baseline (T1) đầu tiên
- Đợi 1-2 giây để camera ổn định
- **KHÔNG CẦN** bấm SPACE lần đầu (khác với phiên bản cũ)

**Bước 5: Bắt đầu chơi**

**Lượt Người chơi (Đỏ):**
1. Di chuyển quân cờ vật lý trên bàn
2. Bấm `SPACE` để hệ thống nhận diện nước đi
3. Hệ thống sẽ:
   - Chụp snapshot T2
   - So sánh với T1 để tìm nước đi
   - Validate theo luật cờ tướng
4. Nếu hợp lệ:
   - Cập nhật bàn cờ
   - Chuyển sang lượt AI
5. Nếu không hợp lệ:
   - Hiển thị thông báo lỗi (ô đỏ nhấp nháy)
   - Đặt quân về vị trí cũ và thử lại

**Lượt AI (Đen):**
1. Hệ thống tự động tính toán nước đi tốt nhất:
   - Ưu tiên Cloud Engine (nhanh, mạnh)
   - Fallback sang Local Pikafish nếu Cloud lỗi
2. Hiển thị "AI thinking..." trên UI
3. Robot tự động thực hiện:
   - Nếu ăn quân: Gắp quân địch → thả vào bãi thải
   - Gắp quân mình từ ô nguồn
   - Đặt quân mình vào ô đích
   - Về vị trí HOMECHESS (hoặc IDLE)
4. Tự động chụp baseline mới (T1 mới)
5. Chuyển lại lượt Người

**Rollback (nếu cần):**
- Bấm `Z` để hoàn tác nước vừa đi
- Hệ thống sẽ:
  - Khôi phục trạng thái bàn cờ
  - Khôi phục baseline T1 cũ
  - Hiển thị thông báo "Rollback successful"
- **Lưu ý:** 
  - Chỉ rollback được 1 nước (nước vừa đi)
  - Phải đặt quân cờ vật lý về đúng vị trí cũ
  - Không rollback được khi đang lượt AI

**Kết thúc game:**
- Chiếu hết → Hiển thị banner thắng/thua
- Bấm nút "New Game" để chơi lại (xếp lại bàn cờ)
- Hoặc bấm nút "Surrender" để đầu hàng
- Bấm `Q` trên cửa sổ camera để thoát

### 4.4. CHẾ ĐỘ DRY RUN (TEST KHÔNG CẦN ROBOT)

Để test logic game mà không cần robot thật:

**Cách 1: Sửa trong config.py**
```python
DRY_RUN = True
```

**Cách 2: Dùng biến môi trường**
```bash
# Windows CMD:
set DRY_RUN=1
python main.py

# Windows PowerShell:
$env:DRY_RUN=1
python main.py

# Linux/Mac:
DRY_RUN=1 python main.py
```

**Chế độ DRY_RUN sẽ:**
- ✅ Chạy đầy đủ logic game
- ✅ Hiển thị UI Pygame
- ✅ Cho phép di chuyển quân bằng chuột (Manual Override)
- ✅ AI vẫn hoạt động (Cloud/Local)
- ❌ Không kết nối robot thật
- ❌ Không chạy camera/YOLO (khác với mô tả cũ)
- ❌ Không có snapshot detection

**Cách chơi trong DRY_RUN:**
1. Khởi động game với `DRY_RUN=True`
2. Kéo thả quân cờ bằng chuột trên UI Pygame:
   - Click vào quân cần di chuyển
   - Click vào ô đích
3. AI sẽ tự động đánh (hiển thị trên UI)
4. Tiếp tục kéo thả quân của bạn

**Khi nào dùng DRY_RUN:**
- Test logic game mới
- Debug AI engine
- Phát triển tính năng mới
- Không có robot/camera
- Chơi thử nhanh không cần setup phần cứng

**Lưu ý:**
- Trong DRY_RUN, robot.connected = False
- Nếu robot không kết nối được, hệ thống tự động chuyển sang chế độ tương tự DRY_RUN
- Có thể bấm SPACE nhưng sẽ báo lỗi vì không có camera

Chế độ này sẽ:
- ✅ Chạy đầy đủ logic game
- ✅ Hiển thị UI Pygame
- ✅ Nhận diện camera + YOLO
- ❌ Không kết nối robot thật
- ❌ Giả lập robot.move_piece() thành công

---

# PHẦN 5: AI CHESS ENGINE (HYBRID / CLOUD / LOCAL)

**Config trung tâm lưu tại (`config.py`):**
```python
ENGINE_TYPE       = "HYBRID" # Lựa chọn: "HYBRID", "CLOUD", "LOCAL"
CLOUD_API_URL     = "https://tuongkydaisu.com/api/engine/bestmove"
PIKAFISH_EXE      = "pikafish/pikafish-avx2.exe"
PIKAFISH_NNUE     = "pikafish/pikafish.nnue"
PIKAFISH_THINK_MS = 3000   # (ms mỗi nước, dành cho Local)
```

- **Phiên bản đang dùng:** Pikafish 2026-01-02 (tải 2026-03-05)
- **Source:** [Pikafish-2026-01-02](https://github.com/official-pikafish/Pikafish/releases/tag/Pikafish-2026-01-02)
- **Cài đặt Local:** File `Pikafish.2026-01-02.7z` → giải nén → copy `Windows/pikafish-avx2.exe` vào `pikafish/`

*(Lưu ý: File exe + nnue KHÔNG push git do đã set trong `.gitignore`. Người mới vui lòng tải thủ công từ nguồn release)*

---

# PHẦN 9: FAQ (FREQUENTLY ASKED QUESTIONS)

### Q1: Tại sao cần file .keep trong thư mục pikafish?
**A:** Git không track thư mục rỗng. File `.keep` giúp giữ cấu trúc thư mục khi clone repo mới, người dùng chỉ cần copy file Pikafish vào mà không cần tạo folder.

### Q2: Tại sao không push file pikafish lên Git?
**A:** File Pikafish + NNUE rất nặng (>100MB), vượt quá giới hạn GitHub. Người dùng tự tải từ official release.

### Q3: Có thể chơi offline hoàn toàn không?
**A:** Có. Đặt `ENGINE_TYPE = "LOCAL"` trong config.py và tải Pikafish về.

### Q4: Làm sao để tăng độ mạnh của AI?
**A:** Tăng `PIKAFISH_THINK_MS` trong config.py (ví dụ: 5000ms = 5 giây). Lưu ý: AI mạnh hơn = chậm hơn.

### Q5: Có thể dùng robot khác thay FR5 không?
**A:** Có, nhưng cần viết lại `src/hardware/robot_VIP.py` để tương thích với SDK của robot mới.

### Q11: Robot gắp sai vị trí, làm sao để debug?
**A:** 
1. Kiểm tra log khi robot di chuyển, sẽ thấy:
   - `[ROBOT] 🔍 DEBUG: s_col=..., s_row=..., d_col=..., d_row=...`
   - `[ROBOT] 📐 board(col=...,row=...) → delta_x=... (row*...), delta_y=... (col*...)`
   - `[ROBOT] 📐 ORIGIN=(...) + delta → X=...mm, Y=...mm`
2. So sánh tọa độ logic (col, row) với vị trí robot thực tế gắp
3. Kiểm tra các thông số trong `config.py`:
   - `BOARD_ORIGIN_X`, `BOARD_ORIGIN_Y` (từ teaching point R1)
   - `ROBOT_DIR_X`, `ROBOT_DIR_Y` (chiều hướng: 1 hoặc -1)
   - `CELL_SIZE_X`, `CELL_SIZE_Y` (kích thước ô)
4. Nếu sai lệch đều, có thể do:
   - Teaching point R1 chưa đúng → Dạy lại R1
   - CELL_SIZE không chính xác → Đo lại bàn cờ
   - ROBOT_DIR sai dấu → Đổi 1 thành -1 hoặc ngược lại
5. **Lưu ý:** Hệ tọa độ robot có X=dọc, Y=ngang (khác với logic col=ngang, row=dọc). Code đã xử lý hoán đổi tự động.

### Q12: Robot hất quân cờ khác khi di chuyển, làm sao khắc phục?
**A:**
Vấn đề này xảy ra vì robot dùng `MoveCart` (point-to-point) thay vì `MoveL` (linear), tạo đường cong tự nhiên giữa các điểm.

**Giải pháp đã implement:**
1. **Tăng độ cao an toàn:**
   - `SAFE_Z`: 217mm → 270mm (độ cao an toàn)

2. **Logic thông minh:**
   - Hệ thống tự động tính khoảng cách di chuyển
   - Nếu ≥4 ô → Dùng SAFE_Z (bay cao hơn)
   - Nếu <4 ô → Dùng SAFE_Z thông thường

3. **Điều chỉnh nếu cần:**
   - Tăng `SAFE_Z` lên 280-300mm trong `config.py`
   - Giảm ngưỡng từ `distance >= 4` xuống `>= 3` trong `robot_VIP.py`

**Tại sao không dùng MoveL?**
- MoveL chỉ đảm bảo đường thẳng trong không gian 3D
- Nếu 2 điểm cùng độ cao → vẫn đi ngang qua quân khác
- Tăng độ cao là giải pháp đơn giản, hiệu quả, tiêu chuẩn trong robotics

### Q13: Sự khác biệt giữa MoveL và MoveCart?
**A:**
- **MoveL (Move Linear):** TCP di chuyển theo đường thẳng trong không gian 3D. Chậm hơn nhưng chính xác. Dùng `blendR` (blend radius, đơn vị mm).
- **MoveCart (Move Cartesian):** Di chuyển điểm-đến-điểm, robot tự chọn quỹ đạo tối ưu (thường là cong). Nhanh hơn. Dùng `blendT` (blend time, đơn vị ms).

Hệ thống hiện tại dùng MoveCart vì nhanh hơn, và giải quyết va chạm bằng cách tăng độ cao thay vì ép đường thẳng.

### Q6: Làm sao để retrain YOLO với quân cờ mới?
**A:** 
1. Chụp ảnh dataset mới (>500 ảnh)
2. Label bằng LabelImg hoặc Roboflow
3. Train lại: `yolo train data=dataset.yaml model=yolo11m.pt epochs=80`
4. Copy `best.pt` vào `models/`

### Q7: Tại sao robot đôi khi bị lỗi Singularity?
**A:** 
Robot ở tư thế khớp thẳng hàng, đặc biệt khi di chuyển đến các góc xa (R2, R3).

**Giải pháp:**
1. **Dạy đủ 4 teaching points R1, R2, R3, R4** (BẮT BUỘC):
   - Hệ thống sử dụng Bilinear Interpolation với độ chính xác ±0.1mm
   - Tự động dùng MoveJ với joint angles an toàn cho các góc
   - Xem chi tiết: `docs/teaching_points_guide.md`

2. **Kiểm tra log:**
   ```
   [ROBOT] 📍 Đang load teaching points...
   [ROBOT] 🎯 Sử dụng Bilinear Interpolation cho tất cả vị trí
   [ROBOT] 📍 Dùng teaching point R2 cho (8,0)
   ```

**Lưu ý:** Hệ thống hiện tại yêu cầu đủ 4 góc để hoạt động. Không có fallback linear.

### Q8: Có thể chơi với 2 người không (không có AI)?
**A:** Hiện tại chưa hỗ trợ. Cần thêm mode "HUMAN_VS_HUMAN" trong game_state.py.

### Q9: Làm sao để stream lên web?
**A:** Cập nhật `SIMULATION_API_TOKEN` trong config.py với token từ tuongkydaisu.com.

### Q14: Hệ thống tính toán vị trí như thế nào?
**A:**
**Hệ thống Bilinear Interpolation:**

1. **Yêu cầu bắt buộc:** Phải có đủ 4 góc R1, R2, R3, R4
   - Hệ thống sẽ báo lỗi và dừng nếu thiếu bất kỳ góc nào
   - Không có fallback linear

2. **Tự động tính CELL_SIZE:**
   ```python
   CELL_SIZE_X = (R1→R2 + R4→R3) / (2 * 8)  # Từ khoảng cách thực tế
   CELL_SIZE_Y = (R1→R4 + R2→R3) / (2 * 9)  # Từ khoảng cách thực tế
   ```

3. **Bilinear Interpolation:**
   - Nội suy 2D từ 4 góc cho mọi vị trí (col, row)
   - Độ chính xác: ±0.1mm
   - Tự động bù méo hình học

4. **Ưu tiên teaching points trực tiếp:**
   - Nếu có teaching point cho vị trí cụ thể → Dùng trực tiếp
   - Nếu không có → Dùng Bilinear Interpolation

**Lợi ích:** Chính xác tuyệt đối, tự động thích ứng với bàn cờ thực tế.

---

**🎉 Chúc bạn thành công với dự án Xiangqi Robot!**