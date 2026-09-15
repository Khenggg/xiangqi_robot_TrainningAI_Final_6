# ACTIONABLE SIMULATION GAPS & DEFECT CATALOG

**Repository:** `Khenggg/xiangqi_robot_TrainningAI_Final_6`  
**Branch:** `feature/virtual-robot-3d-simulator`  
**HEAD SHA:** `410910638e81d35305b22a2ab9a0a04c136875fc`  
**Audit Baseline:** Phase P0  

---

### SIM-GAP-001: Thiếu hoàn toàn Kinematics cho Robot FR3 trong Python Backend
- **Severity:** **CRITICAL**
- **Evidence:** Trong `src/hardware/telemetry_publisher.py` chỉ tồn tại class `FR5Kinematics` với kích thước link của FR5 ($a_2=425\text{ mm}, a_3=395\text{ mm}$). Gói tin JSON phát ra cố định `"robot_model": "FR5"`. Không có file hoặc class nào chứa kinematics cho Fairino FR3 ($a_2=280\text{ mm}, a_3=240\text{ mm}$).
- **Impact:** Simulator hoàn toàn không thể tính toán góc khớp cho cánh tay robot FR3 thật sự. Nếu ép dữ liệu khớp FR5 vào mô hình FR3, cánh tay FR3 trong 3D sẽ bị sai lệch vị trí đầu gắp nghiêm trọng do sải tay ngắn hơn 300 mm.
- **Recommended Phase:** **Phase P2**

---

### SIM-GAP-002: Lỗi Đảo Ngược Bố Trí Bàn Cờ Đỏ/Đen Trong 3D Viewer
- **Severity:** **CRITICAL**
- **Status:** **RESOLVED IN P1**
- **Evidence:** Trong `robot-3d-viewer/board.mjs` (dòng 161–171), mảng `START_LAYOUT` bố trí quân Đỏ (`r`) ở `row=0..3` và quân Đen (`b`) ở `row=6..9`. Trong khi đó, toàn bộ quy ước của dự án (`PROJECT_CONTEXT.md` mục 3.1, `src/core/xiangqi.py`, `src/core/fen_utils.py`) đều quy định phe Đen (Robot) ở `row=0..4` và phe Đỏ (Người chơi) ở `row=5..9`.
- **Impact:** Khi robot AI tính nước đi cho quân Đen, thao tác hiển thị trên 3D viewer sẽ diễn ra trên quân Đỏ của người chơi, gây đảo lộn hoàn toàn ngữ nghĩa bàn cờ.
- **Resolution in P1:** Tạo module `robot-3d-viewer/layout.mjs` định nghĩa `START_LAYOUT` chuẩn hóa: Black ở `row=0..4` (Tướng Đen tại `(4, 0)`), Red ở `row=5..9` (Tướng Đỏ tại `(4, 9)`). `board.mjs` nạp trực tiếp từ `layout.mjs`. Đã kiểm chứng qua unit test `tests/unit/test_board_layout.py`.

---

### SIM-GAP-003: Chế Độ DRY_RUN Không Thực Thi Mô Phỏng Chuyển Động Robot
- **Severity:** **CRITICAL**
- **Status:** **PENDING (Phase P2 & P4)**
- **Evidence:** Trong `src/hardware/robot_VIP.py`, các hàm `move_safe_pose()`, `movel_pose()`, `movej_joint()` chỉ in ra terminal `[ROBOT] DRY Move...` và `time.sleep(0.2)` mà không gọi `TelemetryPublisher.animate_to_pose()`. Đặc biệt, trong `main.py` (dòng 172), khi `config.DRY_RUN = True`, toàn bộ khối gọi `hw.robot.move_piece()` bị bỏ qua hoàn toàn.
- **Impact:** Khi chạy dry-run, cánh tay robot 3D trên trình duyệt đứng yên hoàn toàn, không có bất kỳ chuyển động nào được mô phỏng.
- **Recommended Phase:** **Phase P2 & Phase P4**

---

### SIM-GAP-004: Mâu Thuẫn và Trùng Lặp Khai Báo Kích Thước Hình Học Bàn Cờ
- **Severity:** **HIGH**
- **Status:** **PARTIALLY RESOLVED IN P1 (Virtual Board ↔ Robot Placement Deferred to P2)**
- **Evidence:** Kích thước bàn cờ và bước lưới từng bị phân tán và tính toán sai lệch giữa Python, JS, và teaching points.
- **Impact:** Sai số tích lũy giữa các module khiến vị trí gắp đặt ảo không khớp chính xác với tâm giao điểm bàn cờ 3D.
- **Resolution in P1 & P2 Roadmap:** 
  - **Đã giải quyết trong P1 (Hình học nội tại):** Xác lập `shared/physical_geometry.json` làm nguồn chân lý duy nhất (Single Source of Truth) cho kích thước vật lý đo đạc ($367 \times 410\text{ mm}$, ô $40 \times 40\text{ mm}$, quân $\varnothing 22.5 \times 9.43\text{ mm}$). Tạo `src/domain/geometry.py` kế thừa JSON và tính toán các giá trị phái sinh ($320 \times 360\text{ mm}$, lề $23.5\text{ mm}$ và $25.0\text{ mm}$). Cập nhật `config.py` làm alias tương thích ngược và `robot-3d-viewer/geometry.mjs` nạp động qua endpoint an toàn `/shared/physical_geometry.json`.
  - **Còn tồn đọng cần giải quyết trong P2 (Vị trí ngoại tại):** Các điểm dạy dry-run R1-R4 trong `robot_VIP.py` và hàm `_calculate_cell_sizes_from_corners()` vẫn đang dựa trên các tọa độ commissioning cũ (tính ra $44.45\text{ mm}$ và $45.08\text{ mm}$). Việc chuẩn hóa vị trí gắn kết bàn cờ ảo so với chân đế robot (`robot_base` ↔ `3d_world`) và calibration điểm dạy ảo sẽ được thực hiện đồng bộ trong **Phase P2** (Virtual FR3 Backend & Placement Calibration).


---

### SIM-GAP-005: 3D Viewer Từ Chối Kết Nối Khi Chọn Model FR3
- **Severity:** **HIGH**
- **Status:** **PENDING (Phase P2)**
- **Evidence:** Trong `robot-3d-viewer/live_state.mjs` (dòng 5–7), hàm `validateLivePacket` kiểm tra `payload.robot_model !== expectedModel`. Nếu người dùng chọn FR3 trên dropdown, `expectedModel` là `"FR3"`. Tuy nhiên Python backend luôn gửi `"FR5"`.
- **Impact:** Gói tin bị từ chối với thông báo `Live packet rejected: expected robot_model FR3` và robot 3D không cập nhật.
- **Recommended Phase:** **Phase P2**

---

### SIM-GAP-006: Thiếu Khai Báo Thư Viện `websockets` Trong `requirements.txt`
- **Severity:** **HIGH**
- **Status:** **RESOLVED IN P1**
- **Evidence:** `src/hardware/telemetry_publisher.py` import `websockets`. Tuy nhiên file `requirements.txt` chỉ có 5 thư viện (`pygame`, `opencv-python`, `numpy`, `requests`, `ultralytics`), hoàn toàn thiếu `websockets`.
- **Impact:** Khi triển khai trên môi trường máy mới, chương trình sẽ gặp lỗi `ImportError` hoặc WebSocket server âm thầm không chạy.
- **Resolution in P1:** Khai báo `websockets>=11.0` tường minh trong `requirements.txt`.

---

### SIM-GAP-007: Quân Cờ 3D Chỉ Là Khối Render Tĩnh (Không Có Mô Hình Vật Lý Ảo)
- **Severity:** **HIGH**
- **Status:** **PENDING (Phase P3)**
- **Evidence:** Trong `robot-3d-viewer/main.mjs`, quân cờ được vẽ một lần qua `buildPieces()`. Hàm `movePieceTo()` trong `board.mjs` chỉ dịch chuyển tức thời tọa độ XZ mà không có chuyển động nâng hạ, không có liên kết với đầu gẹp, và không được kết nối với luồng WebSocket.
- **Impact:** Robot ảo chuyển động nhưng quân cờ trên bàn 3D hoàn toàn đứng yên.
- **Recommended Phase:** **Phase P3**

---

### SIM-GAP-008: 3D Viewer Chưa Render Mesh Đầu Gắp (Gripper)
- **Severity:** **MEDIUM**
- **Status:** **PENDING (Phase P3)**
- **Evidence:** Trong `telemetry_publisher.py`, gói tin có chứa trường `"gripper": true/false`. Tuy nhiên trong `main.mjs` không có bất kỳ code nào tạo mesh đầu kẹp gắn vào `wrist3_link` và không đọc giá trị `payload.gripper`.
- **Impact:** Người dùng không quan sát được trạng thái đóng/mở của ngàm hút/kẹp trên Digital Twin.
- **Recommended Phase:** **Phase P3**

---

### SIM-GAP-009: 80% File Test Trong Repo Có Nguy Cơ Kích Hoạt Phần Cứng Thật
- **Severity:** **CRITICAL SAFETY RISK**
- **Status:** **RESOLVED IN P1**
- **Evidence:** Các file trong `tests/` (`test_4_rooks.py`, `test_corners.py`, `test_goto_xe_den.py`, `test_move_to_pos.py`, `test_tool_do0.py`) và trong `tools/hardware_tests/` (`run_gripper_test.py`, `test_gripper_diagnose.py`) đều kết nối trực tiếp IP `192.168.58.2` và phát lệnh `MoveCart`, `MoveJ`, `SetToolDO`.
- **Impact:** Nếu vô tình chạy tự động các file này trong môi trường có kết nối mạng tới robot thật, tay máy sẽ lập tức chuyển động vật lý, vi phạm nghiêm trọng quy chuẩn an toàn.
- **Resolution in P1:** Di chuyển toàn bộ script gọi robot thật vào `tools/hardware_tests/`. Thiết lập thư mục cô lập an toàn `tests/unit/` chỉ chứa unit tests thuần túy. Cấu hình `pytest.ini` với `testpaths = tests/unit` và `norecursedirs = tools/hardware_tests`, đảm bảo lệnh `pytest` tự động KHÔNG BAO GIỜ chạm vào robot thật.

