# ACTIONABLE SIMULATION GAPS & DEFECT CATALOG

**Repository:** `Khenggg/xiangqi_robot_TrainningAI_Final_6`  
**Branch:** `feature/virtual-robot-3d-simulator`  
**HEAD SHA:** `410910638e81d35305b22a2ab9a0a04c136875fc`  
**Audit Baseline:** Phase P0  

---

### SIM-GAP-001: Thiếu hoàn toàn Kinematics cho Robot FR3 trong Python Backend
- **Severity:** **CRITICAL**
- **Status:** **RESOLVED IN P2**
- **Evidence:** Trong `src/hardware/telemetry_publisher.py` chỉ tồn tại class `FR5Kinematics` với kích thước link của FR5 ($a_2=425\text{ mm}, a_3=395\text{ mm}$). Gói tin JSON phát ra cố định `"robot_model": "FR5"`. Không có file hoặc class nào chứa kinematics cho Fairino FR3 ($a_2=280\text{ mm}, a_3=240\text{ mm}$).
- **Impact:** Simulator hoàn toàn không thể tính toán góc khớp cho cánh tay robot FR3 thật sự. Nếu ép dữ liệu khớp FR5 vào mô hình FR3, cánh tay FR3 trong 3D sẽ bị sai lệch vị trí đầu gắp nghiêm trọng do sải tay ngắn hơn 300 mm.
- **Resolution in P2:**
  - Tạo generator `tools/simulation/generate_fr3_profile.py` trích xuất thông số hình học khớp chính thức từ `fairino3_v6.urdf` và xuất file `shared/robot_profiles/fr3.json`.
  - Phát triển module `src/simulation/kinematics/urdf_chain.py` và `src/simulation/kinematics/fr3.py` triển khai Forward Kinematics (biến đổi đồng nhất 4x4) và Inverse Kinematics (Damped Least Squares với multi-seed restart và cấu trúc `IKResult`).
  - Kiểm thử đạt 100% (90/90 điểm giao bàn cờ reachable với sai số vị trí tối đa $0.8641\text{ mm}$, biên góc khớp an toàn $\ge 2.65^\circ$).

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
- **Status:** **PARTIALLY RESOLVED IN P2 (Backend & Kinematics Ready; Game Loop Integration in P4)**
- **Evidence:** Trong `src/hardware/robot_VIP.py`, các hàm `move_safe_pose()`, `movel_pose()`, `movej_joint()` chỉ in ra terminal `[ROBOT] DRY Move...` và `time.sleep(0.2)` mà không gọi `TelemetryPublisher.animate_to_pose()`. Đặc biệt, trong `main.py` (dòng 172), khi `config.DRY_RUN = True`, toàn bộ khối gọi `hw.robot.move_piece()` bị bỏ qua hoàn toàn.
- **Impact:** Khi chạy dry-run, cánh tay robot 3D trên trình duyệt đứng yên hoàn toàn, không có bất kỳ chuyển động nào được mô phỏng.
- **Resolution in P2:** Xây dựng trừu tượng `RobotBackend` (`src/hardware/backends/base.py`) và triển khai `VirtualFR3Backend` (`src/simulation/virtual_fr3_backend.py`) với đầy đủ khả năng nội suy khớp `move_joint()` và tuyến tính Cartesian `move_cartesian()`, phát telemetry trực tiếp 30 FPS. Kiểm chứng độc lập qua `tools/simulation/demo_virtual_fr3.py`. Tích hợp hoàn toàn vào game loop của `main.py` và refactor `robot_VIP.py` sẽ thực hiện trong **Phase P4**.

---

### SIM-GAP-004: Mâu Thuẫn và Trùng Lặp Khai Báo Kích Thước Hình Học Bàn Cờ & Vị Trí Robot-Bàn
- **Severity:** **HIGH**
- **Status:** **RESOLVED IN P1 & P2**
- **Evidence:** Kích thước bàn cờ và bước lưới từng bị phân tán và tính toán sai lệch giữa Python, JS, và teaching points.
- **Impact:** Sai số tích lũy giữa các module khiến vị trí gắp đặt ảo không khớp chính xác với tâm giao điểm bàn cờ 3D.
- **Resolution in P1 & P2:** 
  - **Đã giải quyết trong P1 (Hình học nội tại):** Xác lập `shared/physical_geometry.json` làm nguồn chân lý duy nhất cho kích thước vật lý ($367 \times 410\text{ mm}$, ô $40 \times 40\text{ mm}$, quân $\varnothing 22.5 \times 9.43\text{ mm}$). `src/domain/geometry.py` tính toán các giá trị phái sinh ($320 \times 360\text{ mm}$, lề $23.5\text{ mm}$ và $25.0\text{ mm}$).
  - **Đã giải quyết trong P2 (Vị trí ngoại tại trong Simulation):** Xác lập `shared/virtual_fr3_scene.json` định nghĩa ma trận chuyển đổi chặt chẽ giữa `robot_base` và `3d_world` ($X_{world} = Y_{robot}$, $Y_{world} = Z_{robot}$, $Z_{world} = -X_{robot}$), đặt tâm bàn cờ tại $(X=-0.36, Y=0.0, Z=0.05)\text{ m}$ trong hệ robot. Đạt 100% (90/90) điểm giao reachable.

---

### SIM-GAP-005: 3D Viewer Từ Chối Kết Nối Khi Chọn Model FR3
- **Severity:** **HIGH**
- **Status:** **RESOLVED IN P2**
- **Evidence:** Trong `robot-3d-viewer/live_state.mjs` (dòng 5–7), hàm `validateLivePacket` kiểm tra `payload.robot_model !== expectedModel`. Nếu người dùng chọn FR3 trên dropdown, `expectedModel` là `"FR3"`. Tuy nhiên Python backend luôn gửi `"FR5"`.
- **Impact:** Gói tin bị từ chối với thông báo `Live packet rejected: expected robot_model FR3` và robot 3D không cập nhật.
- **Resolution in P2:**
  - Cập nhật `TelemetryPublisher` hỗ trợ `robot_model="FR3"` (mặc định) và nhận `RobotStateSnapshot`.
  - Cập nhật `robot-3d-viewer/index.html` mặc định lựa chọn model FR3.
  - Cập nhật `robot-3d-viewer/serve.mjs` cho phép nạp `fr3.json` và `virtual_fr3_scene.json`.
  - Viewer Three.js nạp và cập nhật trực tiếp mô hình FR3 từ telemetry 30 FPS.

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
- **Status:** **RESOLVED IN P3**
- **Evidence:** Trong `robot-3d-viewer/main.mjs`, quân cờ từng chỉ được vẽ một lần qua `buildPieces()`. Hàm `movePieceTo()` trong `board.mjs` chỉ dịch chuyển tức thời tọa độ XZ mà không có chuyển động nâng hạ, không có liên kết với đầu gắp, và không được kết nối với luồng WebSocket.
- **Impact:** Robot ảo chuyển động nhưng quân cờ trên bàn 3D hoàn toàn đứng yên.
- **Resolution in P3:**
  - Triển khai `VirtualPhysicalWorld` (`src/simulation/physics/world.py`) với PyBullet rigid-body engine (`p.DIRECT`).
  - Khởi tạo 32 quân cờ với khối trụ va chạm (`GEOM_CYLINDER`), khối lượng 20g, ma sát trượt/lăn/xoay và hệ số nảy.
  - Quản lý gắp nhả qua `VirtualGripper` với capture volume và liên kết bất biến biến đổi tương đối ($T_{\text{flange\_piece}} = T_{\text{flange}}^{-1} \cdot T_{\text{piece}}$).
  - Phát gói tin `world_state` (vị trí X,Y,Z và quaternion của 32 quân cờ) qua WebSocket 30 FPS.
  - Cập nhật `robot-3d-viewer/board.mjs` với `updatePiecesFromWorldState()` đồng bộ trực tiếp vị trí và góc nghiêng quân cờ theo thời gian thực.

---

### SIM-GAP-008: 3D Viewer Chưa Render Mesh Đầu Gắp (Gripper)
- **Severity:** **MEDIUM**
- **Status:** **RESOLVED IN P3**
- **Evidence:** Trong `telemetry_publisher.py`, gói tin có chứa trường `"gripper": true/false`. Tuy nhiên trong `main.mjs` không có bất kỳ code nào tạo mesh đầu kẹp gắn vào `wrist3_link` và không đọc giá trị `payload.gripper`.
- **Impact:** Người dùng không quan sát được trạng thái đóng/mở của ngàm hút/kẹp trên Digital Twin.
- **Resolution in P3:**
  - Định nghĩa thông số hình học ngàm gắp trong `shared/virtual_gripper_profile.json` (base adapter, body cylinder, 2 ngàm trượt đối xứng).
  - Xây dựng hàm `buildProceduralGripper()` trong `robot-3d-viewer/main.mjs` tạo mesh Three.js gắn vào `flange` link của robot FR3.
  - Cập nhật ngàm gắp theo giá trị `payload.gripper` và `jaw_opening_m` từ luồng telemetry `robot_state` và `world_state` với hiệu ứng chuyển động mượt mà.

---

### SIM-GAP-009: 80% File Test Trong Repo Có Nguy Cơ Kích Hoạt Phần Cứng Thật
- **Severity:** **CRITICAL SAFETY RISK**
- **Status:** **RESOLVED IN P1**
- **Evidence:** Các file trong `tests/` (`test_4_rooks.py`, `test_corners.py`, `test_goto_xe_den.py`, `test_move_to_pos.py`, `test_tool_do0.py`) và trong `tools/hardware_tests/` (`run_gripper_test.py`, `test_gripper_diagnose.py`) đều kết nối trực tiếp IP `192.168.58.2` và phát lệnh `MoveCart`, `MoveJ`, `SetToolDO`.
- **Impact:** Nếu vô tình chạy tự động các file này trong môi trường có kết nối mạng tới robot thật, tay máy sẽ lập tức chuyển động vật lý, vi phạm nghiêm trọng quy chuẩn an toàn.
- **Resolution in P1:** Di chuyển toàn bộ script gọi robot thật vào `tools/hardware_tests/`. Thiết lập thư mục cô lập an toàn `tests/unit/` chỉ chứa unit tests thuần túy. Cấu hình `pytest.ini` với `testpaths = tests/unit` và `norecursedirs = tools/hardware_tests`, đảm bảo lệnh `pytest` tự động KHÔNG BAO GIỜ chạm vào robot thật.

---

### SIM-GAP-010: Thiếu Va Chạm Vật Lý Đầu Gắp Trong PyBullet & Thả Rơi Giữa Chừng Chưa Thật Sự Mid-Motion
- **Severity:** **CRITICAL**
- **Status:** **RESOLVED IN P3.1**
- **Evidence:** 
  1. Trong P3, đầu gắp chỉ là một biến đổi hình học thuần túy (`set_tcp_pose()`), không tạo các rigid bodies va chạm trong PyBullet world. Quân cờ không thể va quệt vật lý với các ngàm kẹp khi rơi hoặc di chuyển.
  2. Kịch bản thả rơi quân cờ (drop) trong P3 trước đó thực hiện sau khi robot đã dừng lại (`RESTING`), dẫn đến vận tốc nhả $\approx 0$, không phản ánh đúng động học ném/văng quán tính khi mất điện kẹp giữa hành trình.
  3. Viewer Three.js còn hardcode mảng `START_LAYOUT` và kích thước ngàm kẹp thủ tục, tách rời nguồn chân lý JSON.
- **Impact:** Thiếu độ chân thực vật lý của Digital Twin, tiềm ẩn nguy cơ sai lệch trạng thái kẹp và phân rã các nguồn cấu hình chuẩn.
- **Resolution in P3.1:**
  - **PyBullet Gripper Proxies:** Tạo 3 kinematic collision bodies trong PyBullet (palm plate, left jaw, right jaw) với kích thước từ `shared/virtual_gripper_profile.json`. Ngàm di chuyển trượt dọc theo trục `travel_axis` (mặc định X) theo trạng thái đóng/mở. Quản lý `p.setCollisionFilterPair` linh hoạt: tắt va chạm ngàm-quân khi đang kẹp, tự động bật lại va chạm vật lý ngay khi nhả/rơi.
  - **True Mid-Motion Drop:** Triển khai `schedule_force_drop()` trong `SimulationRuntime` kích hoạt chính xác tại thời điểm robot đang chuyển động tốc độ cao (`motion_state == "MOVING"`). Kế thừa vận tốc tuyến tính $> 0.02\text{ m/s}$, ghi nhận đầy đủ chẩn đoán trong `DropEvent` (tọa độ, vận tốc, trạng thái robot, thời gian bay, vị trí ổn định cuối cùng), trong khi robot tiếp tục hoàn tất quỹ đạo độc lập.
  - **Single Sources of Truth:**
    - Viewer nạp động `layout.mjs` từ `/shared/xiangqi_start_layout.json` (32 quân cờ chuẩn tắc).
    - Tạo `gripper_profile.mjs` nạp động `/shared/virtual_gripper_profile.json` cho Three.js viewer.
    - `transforms.py` nạp ma trận chân đế robot từ `/shared/virtual_fr3_scene.json` kèm kiểm tra trực giao ($R^T R = I$) và định thức chirality ($\det(R) \approx +1.0$).
  - **Concurrency & Validation:** Đổi lock backend sang `threading.RLock()` triệt tiêu hoàn toàn nguy cơ deadlock reentrant khi listener kích hoạt `set_gripper(False)`. Bổ sung module `validation.py` kiểm tra cấu hình nghiêm ngặt với cơ chế giải phóng tài nguyên PyBullet an toàn khi có ngoại lệ.

---

### SIM-GAP-011: Lỗi Scoping Runtime Three.js Viewer, Fallback Geometry & Bộ Nhớ Đệm Scene Transform
- **Severity:** **BLOCKER / HIGH**
- **Status:** **RESOLVED IN P3.2**
- **Evidence:** 
  1. Trong `robot-3d-viewer/main.mjs`, `buildRobotArm` gọi `buildProceduralGripper(gripperProfile)` nhưng `gripperProfile` không nằm trong danh sách tham số của `buildRobotArm`, gây ra `ReferenceError: gripperProfile is not defined` khi khởi chạy ứng dụng 3D.
  2. `buildProceduralGripper` còn chứa các giá trị kích thước hình học và màu sắc fallback hardcode (`[0.060, 0.040, 0.030]`, `0.040`, `0.020`...).
  3. Trong `transforms.py`, biến `_CACHED_SCENE_TRANSFORM` không bao giờ được gán do điều kiện `if scene_config_path is None:` bị vô hiệu hóa sau khi gán đường dẫn mặc định, dẫn đến mỗi snapshot đọc lại file đĩa 64 lần.
  4. Bộ lọc `validateWorldStatePacket` sử dụng `Boolean(...)` chấp nhận chuỗi `"false"` hoặc số `1` không đúng chuẩn dữ liệu.
- **Impact:** Ứng dụng web 3D viewer có nguy cơ sập khi load, snapshot bị giảm hiệu năng do đọc file lặp lại, và dữ liệu telemetry thiếu tính chặt chẽ.
- **Resolution in P3.2:**
  - Sửa `buildRobotArm(profile, gripperProfile)` nhận tham số rõ ràng và ném ngoại lệ nếu thiếu profile; xóa sạch toàn bộ fallback hardcode trong `buildProceduralGripper`.
  - Hỗ trợ đầy đủ `travel_axis` ("X", "Y", "Z") cho cả vị trí ban đầu và hoạt họa trượt của ngàm.
  - Sửa logic gán cache với cờ `use_default_path`, bảo đảm cache hoạt động thực sự và cô lập an toàn với các file tùy biến.
  - Thắt chặt validation JavaScript cho cả `gripper_profile.mjs` và `live_state.mjs` (bắt buộc boolean thuần túy, kiểm tra quaternion non-zero).
  - Bổ sung assertion kiểm chứng tính độc lập quỹ đạo sau khi thả rơi trong `test_runtime_mid_motion_drop.py`.

---

### SIM-GAP-012: Bất Đồng Bộ Tool-Frame, Tâm Gắp và Độ Dày Bàn Cờ Giữa Backend, Viewer và PyBullet
- **Severity:** **CRITICAL**
- **Status:** **RESOLVED IN PHASE 3 FINAL CLOSURE**
- **Evidence:** 
  1. Độ dày bàn cờ từng có mâu thuẫn giữa $40\text{ mm}$ (trong một số cấu hình vật lý cũ) và $10.5\text{ mm}$ (đo đạc thực tế trên `physical_geometry.json`).
  2. TCP và tâm gắp từng bị phân tách với offset giả định $35\text{ mm}$, trong khi ngàm kẹp song song kẹp trực tiếp bằng đầu ngón tay ($0.218\text{ m}$ từ flange J6).
  3. Backend giải IK từ Flange nhưng không có bất biến cứng $\|p_{\text{flange}} - p_{\text{tcp}}\| \equiv 0.218\text{ m}$ bảo đảm ràng buộc dụng cụ.
- **Impact:** Nguy cơ sai lệch vị trí đầu gắp khi hạ kẹp, ngàm kẹp đâm vào mặt bàn hoặc kẹp hụt quân cờ.
- **Resolution in Phase 3 Final Closure:**
  - Đồng bộ độ dày bàn cờ $10.5\text{ mm}$ ($0.0105\text{ m}$) trên toàn hệ thống (`physical_geometry.json`, `virtual_physics.json`, `geometry.py`, `geometry.mjs`). Bề mặt bàn cờ cố định tại $Z_{\text{robot}} = +0.0105\text{ m}$.
  - Xác lập TCP tại chính giữa hai đầu ngón kẹp với vector $T_{\text{flange\_tcp}} = [0, 0, 0.218]\text{ m}$. Tâm gắp trùng khít TCP (`tcp_to_grasp_center_m = [0.0, 0.0, 0.0]`).
  - Thiết lập bất biến hình học cứng $\|p_{\text{flange}} - p_{\text{tcp}}\| \equiv 0.218\text{ m}$ trong `VirtualFR3Backend` và giải IK từ pose TCP mục tiêu.

---

### SIM-GAP-013: Thiếu Kiểm Tra Va Chạm Articulated Robot Toàn Diện Trong PyBullet và Trajectory Chưa Authoritative
- **Severity:** **CRITICAL**
- **Status:** **RESOLVED IN PHASE 3 FINAL CLOSURE**
- **Evidence:** 
  1. PyBullet trước đây chỉ chứa 3 khối va chạm proxy của gripper, hoàn toàn thiếu mô hình động học articulated của cánh tay FR3. Các va chạm giữa các link của robot với bàn cờ, quân cờ hoặc tự va chạm không được phát hiện.
  2. Quỹ đạo 3 giai đoạn (Lift -> Transit -> Land) từng bị viewer Three.js nội suy client-side thay vì được kiểm soát độc quyền bởi Python backend runtime.
  3. Viewer hiển thị nhãn tiếp thị "AN TOÀN 100%" mà không có bằng chứng va chạm PyBullet.
- **Impact:** Robot có thể chuyển động xuyên thấu bàn cờ hoặc tự va chạm ở các góc gập sâu mà không bị chặn; viewer thiếu tính trung thực kỹ thuật.
- **Resolution in Phase 3 Final Closure:**
  - Nạp URDF cánh tay FR3 vào PyBullet thông qua `src/simulation/physics/urdf_resolver.py` với điều khiển vị trí giữ cứng tư thế.
  - Xây dựng `FR3CollisionGuard` (`src/simulation/physics/collision_guard.py`) kiểm tra va chạm toàn thân: link-bàn, link-quân, kẹp-bàn, kẹp-quân và tự va chạm giữa các link. Pre-validate toàn bộ quỹ đạo trong `move_cartesian()`.
  - Tái tạo `cell_reachability_dataset.json` bảo đảm 90/90 ô cờ 100% reachable và 100% collision-free trong PyBullet.
  - `SimulationRuntime` chịu trách nhiệm độc quyền thực thi quỹ đạo Lift -> Transit -> Land.
  - Xóa bỏ nhãn tiếp thị trên viewer, chuyển thành telemetry kỹ thuật (`COLLISION-FREE`, `TRAJECTORY COMPLETE`).




