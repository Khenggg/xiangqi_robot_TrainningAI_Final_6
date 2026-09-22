# BÁO CÁO KỸ THUẬT TOÀN DIỆN: HỢP NHẤT KIẾN TRÚC ROBOT CỜ TƯỚNG FAIRINO FR3
**Branch tích hợp:** `integration/unified-fr3-system`  
**Base Architecture Authority:** `feature/virtual-robot-3d-simulator`  
**Ngày hoàn thành:** 22/09/2026  

---

## 1. Tóm Tắt Điều Hành (Executive Summary)

Dự án đã hoàn thành quá trình tích hợp toàn bộ tính năng vượt trội từ 5 nhánh phát triển độc lập:
1. `feature/virtual-robot-3d-simulator`: Cơ sở toán học, hình học FR3, Digital Twin, mô hình chuyển đổi tọa độ chuẩn +90° Yaw.
2. `main`: Chu trình trò chơi Xiangqi, tích hợp AI Engine (Moonfish/Cloud), quản lý lượt đi.
3. `function/new-gripper-controls`: Điều khiển kẹp 2 cổng DO với xung kích hoạt và cơ chế an toàn.
4. `feature/visual-correction-v2`: Thuật toán bù tâm gắp đa khung hình (Multi-frame Visual Pick), phát hiện bàn cờ tự động bằng ONNX CChess, giám sát tay người chơi (Turn Completion Monitor).
5. `test/merging-newest`: Dashboard giám sát trạng thái và telemetry độc lập.

Quy trình tích hợp được thực hiện tuần tự qua **9 Phase**, tuân thủ nguyên tắc không merge mù quáng, viết unit test xác minh độc lập cho từng subsystem và đảm bảo 100% không làm gãy các bất biến hình học (geometry invariants).

---

## 2. Kiến Trúc Hợp Nhất (Unified Architecture Blueprint)

```
+-----------------------------------------------------------------------------------+
|                                     GAMEPLAY                                      |
|                               (main.py / GameState)                               |
+-----------------------------------------------------------------------------------+
       |                                      |                               |
       v                                      v                               v
+------------------+             +-------------------------+            +-----------+
| AI Controller    |             | Motion Coordinator      |            | Vision    |
| (Moonfish/Cloud) |             | (src/motion/coordinator)|            | Pipeline  |
+------------------+             +-------------------------+            +-----------+
                                              |                               |
                   +--------------------------+--------------------+          | (col, row)
                   |                                               |          v
                   v                                               v   +----------------+
        +----------------------+                        +--------------| Visual Pick    |
        | BoardPlacementState  |                        | RobotBackend | Aggregator     |
        | (T_robot_from_board) |                        | Abstraction  | (Multi-frame)  |
        +----------------------+                        +--------------+----------------+
                   |                                            |
         +---------+---------+                     +------------+------------+
         |                   |                     |                         |
         v                   v                     v                         v
+-----------------+ +-----------------+ +--------------------+ +--------------------+
| FixedBoardPose  | | Virtual World   | | PhysicalFR3Backend | | VirtualFR3Backend  |
| Provider (Real) | | Placement (Sim) | | (FAIRINO RPC SDK)  | | (PyBullet / URDF)  |
+-----------------+ +-----------------+ +--------------------+ +--------------------+
                                                   |                         |
                                        +--------------------+     +--------------------+
                                        | TwoOutputGripper   |     | Virtual Gripper    |
                                        | Driver (DO0 / DO1) |     | Constraint Attach  |
                                        +--------------------+     +--------------------+
```

---

## 3. Ma Trận Tích Hợp Nhánh (Branch Integration Matrix)

| Subsystem / Tính năng | Nhánh nguồn gốc | Module đích trong kiến trúc | Quyết định kỹ thuật & Bất biến hình học |
|---|---|---|---|
| **Domain Board Pose** | `feature/virtual-robot-3d-simulator` | `src/domain/board_pose.py` | Tách biệt khỏi mô phỏng. Trở thành cơ quan tối cao sở hữu ma trận chuyển đổi tọa độ $T_{robot\_from\_board}$. |
| **Physical Backend** | `main` & FAIRINO SDK | `src/hardware/backends/physical_fr3.py` | Kế thừa `RobotBackend` protocol; chuẩn hóa interface move_joint, move_cartesian, set_gripper, get_state_snapshot. |
| **Two-Output Gripper** | `function/new-gripper-controls` | `src/hardware/gripper/two_output.py` | Enforce mutual exclusion (DO0 đóng, DO1 mở), chống cháy van với xung 0.3s và deadtime 0.1s. |
| **Board Pose Provider** | `feature/virtual-robot-3d-simulator` | `src/domain/board_pose_provider.py` | Chuyển đổi 4 điểm teaching R1-R4 sang `BoardPlacementState` thay vì nội suy bilinear tùy tiện. |
| **CChess Auto-Calib** | `feature/visual-correction-v2` | `src/vision/auto_calibrate.py` | Tự động phát hiện 4 góc bằng mạng ONNX pose + layout nano, fallback sang chọn tay. |
| **Multi-Frame Visual Pick** | `feature/visual-correction-v2` | `src/vision/visual_pick_estimator.py` | Gom $N=3$ frame, yêu cầu tối thiểu $K=2$ mẫu ổn định, giới hạn lệch tối đa $\pm 0.25$ ô cờ. |
| **Motion Coordinator** | Thiết kế mới | `src/motion/coordinator.py` | Tách rời choreography gắp/đặt/ăn quân khỏi chi tiết phần cứng. |
| **Hand Turn Monitor** | `feature/visual-correction-v2` | `src/vision/turn_completion_monitor.py` | Giám sát tay người vào/ra khỏi bàn cờ. Mặc định `AUTO_MOVE_CONFIRM_ENABLED = False` (SPACE là authority). |
| **Debug Dashboard** | `test/merging-newest` | `src/ui/debug_dashboard.py` | Chạy tiến trình con riêng biệt, đọc telemetry từ `RobotBackend` mà không làm chậm game. |

---

## 4. Quyền Hạn Tọa Độ & Mô Hình Không Gian (Domain & Spatial Authority)

- **Hệ quy chiếu chuẩn (Orientation Authority):**
  - Yaw = $+90.0^\circ$ theo quy ước chuẩn:
    $$\begin{aligned}
    +col &\rightarrow -X_{robot} \\
    +row &\rightarrow -Y_{robot} \\
    +z   &\rightarrow +Z_{robot}
    \end{aligned}$$
  - Ma trận xoay chuẩn:
    $$R_{robot\_from\_board} = \begin{bmatrix} -1 & 0 & 0 \\ 0 & -1 & 0 \\ 0 & 0 & 1 \end{bmatrix}$$
- **Kích thước vật lý chuẩn:**
  - Nguồn duy nhất: `shared/physical_geometry.json` (367mm ngang, 410mm dọc, bước ô đều 40.0mm).
- **Phân định rõ ràng trách nhiệm Homography vs Robot:**
  - Camera Homography: Chuyển đổi từ tọa độ ảnh pixel $(x_p, y_p) \rightarrow$ tọa độ ô cờ liên tục $(col, row) \in [0, 8] \times [0, 9]$.
  - Robot Spatial Transform: Thuộc quyền quản lý của `BoardPlacementState.cell_to_robot_xyz(row, col, z_rel_m)`.

---

## 5. An Toàn Cơ Khí & Trình Điều Khiển Kẹp (Two-Output Gripper)

- **Nguyên lý khóa chéo (Mutual Exclusion):**
  - Tool DO0 (Đóng kẹp) và Tool DO1 (Mở kẹp) không bao giờ được phép cùng mang giá trị HIGH (1).
- **Chu kỳ kích xung an toàn (Pulse & Deadtime Execution):**
  1. Reset an toàn: Cả DO0 và DO1 về LOW (0).
  2. Thời gian trễ an toàn (Deadtime): Nghỉ 0.10s.
  3. Kích xung: Bật DO tương ứng lên HIGH trong 0.30s.
  4. Trở về trạng thái nghỉ (Safe Idle): Khối `finally` bảo đảm tắt cả DO0 và DO1 về 0 ngay cả khi xảy ra exception.

---

## 6. Chiến Lược Hiệu Chuẩn Bàn Cờ (Calibration Strategy)

- **Tự động (Auto Calibration via ONNX):**
  - Sử dụng 2 model ONNX: `pose_4_v6.onnx` (phát hiện 4 góc) và `layout_nano_v3.onnx` (phát hiện giao điểm lưới).
  - Tự động tính toán ma trận Homography $3 \times 3$ lưu vào `perspective.npy`.
- **Thủ công (Manual Fallback):**
  - Click 4 góc bàn cờ (Top-Left, Top-Right, Bottom-Right, Bottom-Left) khi ánh sáng hoặc góc quay không thuận lợi.
  - Tái sử dụng `perspective.npy` cũ bằng phím tắt `S`.
- **Tọa độ vật lý Robot:**
  - Sử dụng `FixedBoardPoseProvider.from_teaching_points(teaching_points)` để tính tâm và hướng bàn cờ mà không phụ thuộc vào phép nội suy bilinear méo mó.

---

## 7. Pipeline Thị Giác & Bù Sai Lệch (Visual Pick & Detection)

- **Visual Pick Aggregation:**
  - Khi chuẩn bị gắp, hệ thống chụp liên tiếp 3 frame trước khi tay robot vào che khuất tầm nhìn.
  - Phân cụm các điểm phát hiện và tính median nhằm loại bỏ rung khung hình (jitter).
  - Áp dụng hệ số chân quân cờ `foot_ratio = 0.85` để bù thị sai góc nghiêng camera.
- **Xác nhận kết thúc nước đi (Turn Completion):**
  - `TurnCompletionMonitor` yêu cầu tay người chơi hiện diện tối thiểu 0.25s và sau đó rút hoàn toàn khỏi bàn cờ ít nhất 0.80s trước khi cho phép auto-confirm.
  - Mặc định giữ quyền xác nhận thủ công qua phím **SPACE** để đảm bảo 100% an toàn cho người thật.

---

## 8. Chu Trình Thực Thi Nước Đi (Gameplay Execution Pipeline)

1. Người chơi hoàn thành nước đi $\rightarrow$ Xác nhận qua phím **SPACE** (hoặc hand monitor khi bật).
2. `SnapshotDetector` so sánh trạng thái bàn cờ với Baseline T1, phát hiện nước đi hợp lệ theo luật cờ tướng.
3. AI Controller (Moonfish Engine cục bộ hoặc Cloud API) tính toán nước đi phản hồi tối ưu trong 1-5s.
4. `HardwareManager.move_piece` kích hoạt `MotionCoordinator`:
   - Nếu có ăn quân:
     - Gắp quân bị ăn tại ô đích $\rightarrow$ Thả vào `CAPTURE_BIN` (tọa độ vật lý an toàn).
   - Di chuyển quân tấn công:
     - Gắp quân tại ô nguồn $\rightarrow$ Đặt vào ô đích.
   - Nâng lên cao độ an toàn `SAFE_CLEARANCE_Z_MM = 40.0mm` ở mỗi bước trung gian.
5. Cập nhật FEN, chụp lại Baseline T1 mới, chuyển lượt về người chơi.

---

## 9. Ma Trận So Sánh Tính Năng (Virtual vs Physical Capability Matrix)

| Tiêu chí | Mô phỏng số (Virtual Simulator) | Robot thật (Physical FR3 Arm) |
|---|---|---|
| **Cơ chế truyền động** | PyBullet Physics & URDF Kinematics | FAIRINO Ethernet RPC Controller (`192.168.58.2`) |
| **Kiểu chuyển động** | MoveJ (khớp), MoveL (thẳng) mô phỏng tức thời | MoveJ (khớp), MoveCart (thẳng Cartesian) thực tế |
| **An toàn va chạm** | Ray-cast & AABB collision query trong PyBullet | Safe Z lift + Giới hạn phần mềm bộ điều khiển |
| **Kiểm soát ngàm kẹp** | Liên kết động lực học ảo (constraint attach) | `TwoOutputGripperDriver` (Tool DO0 / DO1 xung 0.3s) |
| **Tần số Telemetry** | Đồng bộ trực tiếp theo chu kỳ tính toán (60Hz) | Gói tin `robot_state_pkg` thời gian thực (10-50Hz) |
| **Bù sai lệch thị giác** | Hỗ trợ đầy đủ qua $(row, col)$ liên tục | Hỗ trợ đầy đủ qua $(row, col)$ liên tục |
| **Môi trường chạy** | Headless hoàn toàn, chạy được trên mọi máy tính | Đòi hỏi robot công nghiệp kết nối mạng LAN |

---

## 10. Bằng Chứng Kiểm Thử & Đo Lường (Test Evidence)

Toàn bộ 71 test tích hợp cốt lõi đã hoàn thành với tỷ lệ đạt **100%**:

```text
Ran 71 tests in 87.905s
OK
```

Chi tiết các suite:
- `tests/unit/test_phase3_dynamic_board_placement.py`: 20/20 PASSED
- `tests/unit/test_phase3_board_orientation_90.py`: 18/18 PASSED
- `tests/unit/test_physical_fr3_backend.py`: 4/4 PASSED
- `tests/unit/test_two_output_gripper.py`: 7/7 PASSED
- `tests/unit/test_board_pose_provider.py`: 3/3 PASSED
- `tests/unit/test_visual_pick_estimator.py`: 5/5 PASSED
- `tests/unit/test_motion_coordinator.py`: 7/7 PASSED
- `tests/unit/test_hardware_manager_integration.py`: 2/2 PASSED
- `tests/unit/test_turn_completion_monitor.py`: 3/3 PASSED
- `tests/unit/test_debug_dashboard.py`: 2/2 PASSED
- `tests/test_cchess_integration.py`: 4/4 PASSED

---

## 11. Khuyến Nghị Triển Khai Trên Robot Thật

1. **Khởi động an toàn:**
   - Luôn khởi chạy với `DRY_RUN = True` trước khi cấp nguồn cho robot thật để kiểm tra luồng nhận diện và AI.
2. **Dạy điểm chuẩn (Teaching Points):**
   - Đảm bảo điểm `HOMECHESS`, `R1`, `R2`, `R3`, `R4`, `R_Trash` đã được lưu trên bộ điều khiển FAIRINO.
3. **Cấu hình phần cứng:**
   - Trong `config.py`, xác định đúng IP (`ROBOT_IP = "192.168.58.2"`), `ROBOT_BACKEND = "PHYSICAL"`.
   - Cổng DO: `TOOL_DO_OPEN = 1`, `TOOL_DO_CLOSE = 0`.
4. **Vận hành thi đấu:**
   - Đặt phím **SPACE** làm cơ chế xác nhận chính thống trong các trận đấu chính thức để tránh sai số do bóng đổ hoặc chuyển động ngoài ý muốn.
