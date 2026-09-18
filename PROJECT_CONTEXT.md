# BẢN ĐẶC TẢ NGỮ CẢNH DỰ ÁN (PROJECT CONTEXT FOR LLM)

> **Mục đích:** File tài liệu này cung cấp toàn bộ ngữ cảnh kỹ thuật, kiến trúc, quy ước code và các lưu ý vật lý/phần cứng để các mô hình LLM khác có thể hiểu sâu sắc và tiếp tục phát triển dự án này mà không cần đọc lại toàn bộ mã nguồn.

---

## 1. TỔNG QUAN DỰ ÁN (EXECUTIVE SUMMARY)

* **Tên dự án:** Xiangqi Robot (Robot Cờ Tướng VIP)
* **Mục tiêu:** Hệ thống tự động chơi cờ tướng (Xiangqi) vật lý với người thật trên bàn cờ vật chất:
  - Người chơi cầm quân **Đỏ (Red)**, đi quân trực tiếp bằng tay trên bàn cờ vật lý.
  - Robot cầm quân **Đen (Black)**, tự động dùng tay máy gắp/đặt quân và thả quân bị ăn vào thùng rác.
* **Ngôn ngữ & Thư viện cốt lõi:**
  - Python 3.8+ (chạy tương thích tốt trên Python 3.10).
  - Thị giác máy tính: `OpenCV`, `Ultralytics YOLO11` (PyTorch).
  - Giao diện: `Pygame` (800x600 px).
  - Tính toán ma trận / tọa độ: `NumPy`.
  - Giao tiếp mạng: `requests` (giao tiếp REST API).
* **Phần cứng tích hợp:**
  - Tay máy công nghiệp: **Fairino FR5 (6 bậc tự do / 6-DOF)** kết nối qua giao thức mạng Ethernet Socket RPC (`192.168.58.2`).
  - Đầu gắp (Gripper): Van hút/kẹp khí nén điều khiển qua cổng Digital Output của robot (`Tool DO0`).
  - Camera: USB Webcam (độ phân giải 1280x720) nhìn từ trên xuống góc xiên.

---

## 2. KIẾN TRÚC MÃ NGUỒN (CODEBASE ARCHITECTURE)

Dự án tuân theo kiến trúc module hóa (Modular & Clean Architecture), chia thành các tầng độc lập trong thư mục `src/`:

```text
xiangqi_robot_TrainningAI_Final_6/
├── main.py                       # Điểm khởi chạy chính (Game Loop 30 FPS)
├── config.py                     # Cấu hình toàn bộ thông số hệ thống (Robot, Camera, Engine, API)
├── RUN.bat                       # Script khởi động 1-click trên Windows
├── perspective.npy               # Ma trận 3x3 Homography hiệu chỉnh góc nhìn camera
├── models/
│   └── best.pt                   # Weights YOLO11 (1-class occupancy model)
│
├── src/
│   ├── core/                     # TẦNG LOGIC CỜ TƯỚNG (THUẦN TÚY, KHÔNG DEPENDENCY UI)
│   │   ├── xiangqi.py            # Toàn bộ luật cờ tướng: is_valid_move, check/checkmate, Zobrist hash
│   │   ├── fen_utils.py          # Chuyển đổi qua lại giữa Board Array 10x9 và chuỗi FEN chuẩn
│   │   └── game_state.py         # Quản lý vòng đời trạng thái ván cờ, FEN, lượt đi, rollback
│   │
│   ├── vision/                   # TẦNG THỊ GIÁC MÁY TÍNH
│   │   ├── calibrate_camera.py   # Hiệu chỉnh 4 góc bàn cờ (Perspective Transform) tạo perspective.npy
│   │   ├── camera_monitor.py     # SINGLE CAMERA OWNER: Thread ngầm thu hoạch frame, flush buffer, predict YOLO
│   │   └── snapshot_detector.py  # So sánh 2 snapshot T1/T2, trích xuất nước đi, lọc hình học, Blind Capture
│   │
│   ├── hardware/                 # TẦNG GIAO TIẾP PHẦN CỨNG
│   │   ├── robot_VIP.py          # Wrapper điều khiển cánh tay Fairino FR5 (Bilinear Interpolation từ R1-R4)
│   │   ├── hardware_manager.py   # Quản lý vòng đời khởi tạo/dọn dẹp của Robot, Camera, AI Controller
│   │   └── robot_sdk_core.*      # SDK cấp thấp C/Python của hãng Fairino
│   │
│   ├── ai/                       # TẦNG ENGINE CỜ TƯỚNG
│   │   ├── ai_controller.py      # Thread điều phối tính toán nước đi (chạy nền không block UI)
│   │   ├── cloud_engine.py       # Gọi REST API https://tuongkydaisu.com/api/engine/bestmove
│   │   └── moonfish_engine.py    # Local fallback engine (giao thức UCCI, chạy Python thuần)
│   │
│   ├── ui/                       # TẦNG GIAO DIỆN
│   │   ├── board_renderer.py     # Render Pygame 800x600, vẽ bàn cờ, quân cờ, hiệu ứng nước đi
│   │   └── input_handler.py      # Xử lý phím SPACE (chụp T2), phím Z (Rollback), chuột (Manual Override)
│   │
│   └── api/
│       └── simulation_client.py  # Client đẩy nước đi FEN trực tiếp lên tuongkydaisu.com cho khán giả xem
│
└── tests/                        # Kịch bản kiểm thử (Test scripts & Unit tests)
    └── test_occupancy_filter.py  # Unit test kiểm thử bộ lọc hình học không gian
```

---

## 3. CÁC QUY ƯỚC DỮ LIỆU CỐT LÕI (DATA CONVENTIONS)

### 3.1. Bàn cờ (Board Array) & Tọa độ
* Kích thước: **10 hàng x 9 cột** (`board[row][col]`, với `0 <= row <= 9` và `0 <= col <= 8`).
* Phía quân Đen (Robot): `row = 0..4` (Hàng 0 là hàng đáy phe Đen).
* Sông (River): Nằm giữa `row = 4` và `row = 5`.
* Phía quân Đỏ (Người): `row = 5..9` (Hàng 9 là hàng đáy phe Đỏ).
* Ký hiệu quân cờ trong mảng 2D:
  - Quân Đỏ: `"r_K"` (Tướng), `"r_A"` (Sĩ), `"r_E"` (Tượng), `"r_N"` (Mã), `"r_R"` (Xe), `"r_C"` (Pháo), `"r_P"` (Tốt).
  - Quân Đen: `"b_K"`, `"b_A"`, `"b_E"`, `"b_N"`, `"b_R"`, `"b_C"`, `"b_P"`.
  - Ô trống: `"."`.

### 3.2. Chuyển đổi FEN
Chuỗi FEN chuẩn của cờ tướng theo định dạng:
`rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1`
* Chữ hoa = Đỏ, Chữ thường = Đen.
* Số = số ô trống liên tiếp. Dấu `/` = hết một hàng (từ hàng 0 đến hàng 9).
* Quản lý qua module thuần: [`src/core/fen_utils.py`](file:///d:/BIN/code/1.OJT/repo/xiangqi_robot_TrainningAI_Final_6/src/core/fen_utils.py).

---

## 4. CƠ CHẾ THỊ GIÁC & YOLO11 (VISION PIPELINE)

### 4.1. Bản chất: "1-Class Occupancy Model"
* Mô hình YOLO11 (`models/best.pt`) chỉ được huấn luyện cho **duy nhất 1 Class: `Occupancy`** (chỉ phát hiện có vật thể/quân cờ hay không).
* Không dựa vào YOLO để phân loại tên quân cờ. Loại quân cờ và phe cờ được duy trì chính xác tuyệt đối nhờ **Memory Board (FEN)** lưu trong RAM.

### 4.2. Khắc phục trễ hình (Buffer Lag)
OpenCV `cv2.VideoCapture` có bộ đệm ngầm gây trễ 1-2 giây. Để khắc phục, hàm `get_fresh_snapshot()` trong [`camera_monitor.py`](file:///d:/BIN/code/1.OJT/repo/xiangqi_robot_TrainningAI_Final_6/src/vision/camera_monitor.py) xả đệm trước khi đọc:
```python
for _ in range(5):
    self.cap.grab()
ret, frame = self.cap.read()
```

### 4.3. Bộ lọc Hình học Kép & Khoảng cách (Dual Geometry & Distance Filter)
Được triển khai trong `_build_occupancy()` tại [`snapshot_detector.py`](file:///d:/BIN/code/1.OJT/repo/xiangqi_robot_TrainningAI_Final_6/src/vision/snapshot_detector.py) để triệt tiêu việc nhận diện nhầm vật tròn ngoại cảnh:
1. **Aspect Ratio Gate:** Chỉ chấp nhận bounding box có tỷ lệ $0.55 \le \frac{w}{h} \le 1.80$.
2. **Chân quân cờ tiếp xúc bàn:** $cx = \frac{x_1 + x_2}{2}, cy = y_1 + 0.85 \times h$ (loại trừ góc chiếu xiên của camera).
3. **Strict Boundary:** Chuyển qua ma trận $M \rightarrow (c_{raw}, r_{raw})$. Chỉ chấp nhận giao điểm $0 \le c < 9$ và $0 \le r < 10$. Tuyệt đối **không clamp** các vật thể ngoài biên.
4. **Distance Gating:** Khoảng cách Euclide $\text{dist} = \sqrt{(c_{raw} - c)^2 + (r_{raw} - r)^2} \le 0.32$. Loại bỏ 100% các vật nằm giữa các ô cờ.
5. **Confidence Gate:** Thiết lập `conf=0.45` trong `CameraMonitor`.

### 4.4. Cơ chế So sánh Snapshot T1 / T2 & Blind Capture Resolution
* **T1 (Baseline):** Trạng thái bàn cờ trước khi người chơi đi.
* **T2 (Current):** Trạng thái bàn cờ sau khi người chơi đi và bấm `SPACE`.
* Tìm ô biến mất (`disappeared` quân Đỏ $\rightarrow$ ô `src`).
* Tìm ô xuất hiện (`appeared` $\rightarrow$ ô `dst`).
* **Trường hợp ăn quân (Stable Capture):** Tại ô đích, lúc T1 có quân Đen và T2 có quân Đỏ, Occupancy không đổi ($T1=\text{True}, T2=\text{True}$). Hệ thống dùng thuật toán **Blind Capture Resolution**: Cắt ảnh ô cờ tại T1 và T2, tính sai khác pixel qua `cv2.absdiff(prev_gray, curr_gray)`. Ô có độ biến thiên pixel lớn nhất chính là ô đã diễn ra thao tác ăn quân.

---

## 5. CƠ CHẾ ĐIỀU KHIỂN ROBOT VẬT LÝ (ROBOTICS)

### 5.1. Quy tắc tọa độ (QUAN TRỌNG NHẤT VỀ PHẦN CỨNG)
* **Hệ tọa độ Robot bị hoán vị so với Mảng cờ:**
  - Trục $X$ của Robot = Chiều dọc của bàn cờ (`row`).
  - Trục $Y$ của Robot = Chiều ngang của bàn cờ (`col`).
  - Mã nguồn trong [`robot_VIP.py`](file:///d:/BIN/code/1.OJT/repo/xiangqi_robot_TrainningAI_Final_6/src/hardware/robot_VIP.py) đã xử lý hoán đổi tự động.
* **4 Điểm dạy góc (Teaching Points R1–R4) & Bilinear Interpolation:**
  - $R_1$: Xe Đen Trái $(col=0, row=0)$
  - $R_2$: Xe Đen Phải $(col=8, row=0)$
  - $R_3$: Xe Đỏ Phải $(col=8, row=9)$
  - $R_4$: Xe Đỏ Trái $(col=0, row=9)$
  - Mọi tọa độ ô cờ $(col, row)$ đều được nội suy song tuyến tính (Bilinear Interpolation) từ 4 điểm thực tế này, đạt độ chính xác $\pm 0.1\text{ mm}$ và tự động bù méo hình học.

### 5.2. Các độ cao an toàn (Z Heights)
* `SAFE_Z = 210.0` (hoặc cao hơn khi di chuyển xa $\ge 4$ ô): Độ cao bay tự do tránh va quẹt quân khác.
* `PICK_Z = 185.0`: Độ cao hạ đầu kẹp xuống gắp quân.
* `PLACE_Z = 190.0`: Độ cao hạ đầu kẹp xuống nhả quân.
* `CAPTURE_BIN_Z = 291.68`: Độ cao thả quân bị ăn vào thùng chứa (`CAPTURE_BIN_X = -226.123, CAPTURE_BIN_Y = 225.024`).
* Điểm `HOMECHESS` / `IDLE`: Vị trí robot đậu sau khi đi xong để không che tầm nhìn của Camera.

---

## 6. QUY TRÌNH MỘT VÒNG NƯỚC ĐI (GAME LOOP FLOW)

1. **Khởi động:** Load FEN ban đầu $\rightarrow$ Init Hardware/Camera $\rightarrow$ Tự động chụp **Baseline T1**.
2. **Lượt Người chơi (Đỏ):**
   - Người di chuyển quân thật $\rightarrow$ Bấm `SPACE`.
   - Vision xả buffer camera $\rightarrow$ Chụp T2 $\rightarrow$ So sánh T1/T2 $\rightarrow$ Validate luật (`is_valid_move`).
   - Cập nhật FEN trong RAM $\rightarrow$ Gọi API đồng bộ lên web server.
   - Nếu Vision không nhận diện được $\rightarrow$ Cho phép **Manual Override** kéo thả chuột trên UI $\rightarrow$ Tự động chụp lại T1 mới.
3. **Lượt Robot AI (Đen):**
   - AI Controller gửi FEN hiện tại cho Engine tính toán:
     * Ưu tiên 1: Cloud Engine (`https://tuongkydaisu.com/api/engine/bestmove`).
     * Ưu tiên 2 (Fallback): Local Engine Moonfish (`moonfish_ucci.py`).
   - Nhận nước đi tốt nhất $(src \rightarrow dst)$.
   - Nếu là nước ăn quân: Robot di chuyển đến $dst \rightarrow$ gắp quân Đỏ mang thả vào `CAPTURE_BIN`.
   - Robot di chuyển đến $src \rightarrow$ gắp quân Đen $\rightarrow$ đặt vào $dst \rightarrow$ lùi về vị trí `HOMECHESS`.
   - Hệ thống đợi 1.0s và tự động gọi `capture_baseline_if_needed()` để lấy **Baseline T1 mới**.
   - Chuyển lại lượt cho Người chơi Đỏ.
4. **Hoàn tác (Rollback):**
   - Bấm phím `Z`: Khôi phục lại trạng thái FEN, mảng cờ và cả frame baseline T1 trước đó.

---

## 7. CÁC LƯU Ý KHI PHÁT TRIỂN TIẾP (DEVELOPMENT GUIDELINES)

1. **Chế độ phát triển không cần phần cứng (DRY_RUN):**
   - Trong [`config.py`](file:///d:/BIN/code/1.OJT/repo/xiangqi_robot_TrainningAI_Final_6/config.py), đặt `DRY_RUN = True` (hoặc set biến môi trường `$env:DRY_RUN=1`).
   - Ở chế độ này, hệ thống bỏ qua kết nối với tay máy robot thật, cho phép test toàn bộ logic game, FEN, AI Engine và điều khiển cờ bằng chuột trên màn hình Pygame.
2. **Quy tắc bảo vệ mã nguồn (File Protection Rules):**
   - **TUYỆT ĐỐI KHÔNG XÓA** các file `__init__.py` trong các thư mục con của `src/` và `tests/` (đây là các mốc package bắt buộc của Python).
   - **TUYỆT ĐỐI KHÔNG XÓA** các file `.keep` (ví dụ `moonfish/.keep`).
   - File `perspective.npy` là dữ liệu cân chỉnh camera thực tế; nếu làm việc offline không có camera, hãy giữ nguyên file này.
3. **Engine Context:** Mã nguồn hiện tại sử dụng **Moonfish Engine** cục bộ (`src/ai/moonfish_engine.py`), hãy lưu ý vì một số tài liệu cũ trong `README.md` từng nhắc tới Pikafish.
4. **Quy trình kiểm thử trước khi xác nhận hoàn thành (Verification Gate):**
   - Luôn chạy cú pháp: `python -m py_compile <file_da_sua>`
   - Chạy bộ unit test hình học: `py -3.10 tests/test_occupancy_filter.py`

