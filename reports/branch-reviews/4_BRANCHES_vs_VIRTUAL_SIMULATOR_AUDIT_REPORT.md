# BÁO CÁO KIỂM TRA & ĐÁNH GIÁ 4 BRANCH SO VỚI BRANCH VIRTUAL
**Repository:** `xiangqi_robot_TrainningAI_Final_6`  
**Nhánh đối chiếu (Target Branch):** `feature/virtual-robot-3d-simulator` (HEAD: `aef953a`)  
**Thời điểm thực hiện:** 2026-09-22  
**Quy chuẩn áp dụng:** `AGENTS.md` & `.agents/skills/deep-pr-review/` (Branch Review Mode, Evidence-First)

---

## 1. TỔNG QUAN SNAPSHOT VÀ CÂY PHÂN NHÁNH (LINEAGE MATRIX)

Cả 4 branch và branch `virtual` đều xuất phát từ cùng một commit tổ tiên chung (**Common Merge-Base**):
* **Common Merge-Base SHA:** `d29b12b7281885b335692f3fda527ab84a9c681d` (*"Merge branch 'origin/integration/vision-occupancy-filter' into main with defensive visual pick wrapper"*).

```text
                                        ┌── [function/new-gripper-controls] (63f90c9)
                                        │        │ (PR #7)
                                        │        ▼
                    ┌── [AutoCali PR#4,5,6] ── [main] (bf1fb73)
                    │                            │
                    │                            ▼
                    │                  [feature/visual-correction-v2] (d4b9f9a)
                    │                            │
[d29b12b] (Base) ───┤                            ├──────────────────────────┐
                    │                            │                          │ (Merge)
                    │                            ▼                          ▼
                    │                   [integration/... UI] ───► [test/merging-newest] (9dad851)
                    │
                    └───────────────────────────────────────────► [feature/virtual-robot-3d-simulator] (aef953a)
                                                                  (71 commits ahead, Phase 3 Simulator)
```

### Bảng đối chiếu số liệu Git (Snapshot Data)

| Tên Branch | Remote HEAD SHA | Commits Ahead (so với base) | Commits Behind (so với virtual) | Trạng thái tích hợp nội bộ |
| :--- | :--- | :---: | :---: | :--- |
| **`feature/virtual-robot-3d-simulator`** *(của bạn)* | `aef953a` | **+71** | 0 | Chứa toàn bộ kiến trúc Phase 3 (Simulator, PyBullet, Three.js, Kinematics) |
| **`function/new-gripper-controls`** | `63f90c9` | **+13** | -71 | Đã được merge hoàn toàn vào `main` qua PR #7 |
| **`main`** | `bf1fb73` | **+17** | -71 | Nhánh chính production, chứa AutoCali (RTMPose) + Gripper mới + Tweak config |
| **`feature/visual-correction-v2`** | `d4b9f9a` | **+20** | -71 | Kế thừa `main`, bổ sung Visual Pick Median Filter + Auto-confirm khi rút tay |
| **`test/merging-newest`** | `9dad851` | **+31** | -71 | Nhánh tích hợp thử nghiệm: gộp `visual-correction-v2` + Menu UI / Debug Dashboard |

---

## 2. KẾT QUẢ MÔ PHỎNG MERGE PHI PHÁ HOẠI (`git merge-tree`)

Kết quả chạy mô phỏng merge từng branch vào `feature/virtual-robot-3d-simulator`:

| Branch | Xung đột văn bản (Textual Conflict) | File tự động gộp (Auto-merged) | Xung đột ngữ nghĩa (Semantic Conflict) |
| :--- | :--- | :--- | :--- |
| **`function/new-gripper-controls`** | `PROJECT_CONTEXT.md`<br>`tests/unit/test_visual_pick_estimator.py` | `config.py`<br>`src/hardware/robot_VIP.py` | Rất thấp. Logic kẹp 2 chiều (`Tool DO0`/`DO1`) đã hỗ trợ DRY RUN an toàn. |
| **`main`** | `PROJECT_CONTEXT.md`<br>`tests/unit/test_visual_pick_estimator.py` | `config.py`<br>`src/hardware/robot_VIP.py`<br>`src/ui/input_handler.py` | Trung bình. Thay thế model YOLO-Pose bằng RTMPose ONNX; thay đổi Z-height thực tế. |
| **`feature/visual-correction-v2`** | `PROJECT_CONTEXT.md`<br>`src/ui/input_handler.py`<br>`tests/unit/test_visual_pick_estimator.py` | `config.py`<br>`src/hardware/robot_VIP.py`<br>`tests/unit/test_occupancy_filter.py` | Thấp - Trung bình. Xung đột tại `input_handler.py` do cả 2 bên cùng thêm hàm/phím tắt quanh `_handle_space_key`. |
| **`test/merging-newest`** | `PROJECT_CONTEXT.md`<br>`src/ui/input_handler.py`<br>`tests/unit/test_visual_pick_estimator.py` | `config.py`<br>`src/hardware/robot_VIP.py`<br>`tests/unit/test_occupancy_filter.py` | Cao hơn. Chứa các commit UI và debug dashboard chưa qua kiểm thử thực tế ("not tested"). |

---

## 3. CHI TIẾT TỪNG BRANCH & ĐÁNH GIÁ NGUY CƠ KỸ THUẬT

### 3.1. Branch `function/new-gripper-controls` (Commit: `63f90c9`)
* **Mục đích:** Thay đổi cơ chế điều khiển kẹp từ 1 cổng DO (van đảo chiều) sang kẹp motor 2 chiều:
  * `Tool DO1` (Active 1): Mở kẹp (Open pulse: `0.3s`, Settle: `0.25s`).
  * `Tool DO0` (Active 1): Đóng kẹp (Close pulse: `0.3s`, Settle: `0.25s`).
  * Deadtime đảo chiều: `0.10s`. Cả 2 cổng luôn được hạ LOW (`0`) ở trạng thái nghỉ (`_set_gripper_safe_idle`).
* **Đánh giá tương thích với `virtual`:**
  * **An toàn:** Code trong `_set_tool_do` có sẵn `if self.dry: print(...); return 0`, hoàn toàn an toàn khi chạy chế độ mô phỏng / dry run.
  * **Trạng thái:** Branch này **đã nằm trọn trong `main`** (được merge tại commit `1cf0365`). Do đó, bạn không cần merge riêng branch này mà sẽ nhận nó khi merge `main` hoặc các branch con của `main`.

---

### 3.2. Branch `main` (Commit: `bf1fb73`)
* **Nội dung mới so với `virtual`:**
  1. **Tích hợp RTMPose & Swin Transformer (Auto-Calibration):**
     * Thay thế model `board_pose.pt` (YOLO-Pose) bằng `models/cchess/pose_4_v6.onnx` (RTMPose) trong `src/vision/auto_calibrate.py`.
     * Tích hợp `src/vision/cchess_recognizer.py` nhận diện quân cờ bằng ONNX Swin Transformer (`models/cchess/layout_nano_v3.onnx`).
     * Thêm script tải model: `download_cchess_models.py`.
  2. **Toàn bộ tính năng Gripper 2 chiều** từ PR #7.
  3. **Hiệu chỉnh thông số phần cứng thực tế (Physical Tuning):**
     * `PICK_Z = 178.0`, `PLACE_Z = 178.0`, `SAFE_Z = 210.0` (giảm độ cao an toàn để di chuyển nhanh hơn).
     * Tọa độ home camera: `IDLE_X = -104.274, IDLE_Y = 149.608, IDLE_Z = 348.199`.
* **Xung đột & Điểm cần lưu ý khi merge vào `virtual`:**
  * **File `PROJECT_CONTEXT.md`:** Branch `virtual` đã viết lại file này làm Hiến chương Kiến trúc Phase 3 (đặc tả Virtual FR3, PyBullet, Digital Twin, Authority Boundaries). Khi merge, **bắt buộc giữ nội dung của `virtual`**, chỉ cập nhật thêm mục thông số Gripper Tool DO0/DO1 vào bảng phần cứng thực tế.
  * **File `tests/unit/test_visual_pick_estimator.py`:** Trên branch `virtual`, file đã được chuyển vào thư mục `tests/unit/` và thêm class `PhysicalPoseTests`. Trên `main`, file vẫn ở `tests/` với 1 dòng `sys.path.insert`. Giải quyết bằng cách giữ file ở `tests/unit/`.
  * **Semantic (Kích thước ô cờ trong `config.py`):**
    * Branch `virtual` lấy kích thước chuẩn từ `src.domain.geometry.get_physical_geometry()` (`column_spacing = 40.0mm`, `row_spacing = 40.0mm`).
    * Branch `main` dùng hằng số cứng cũ (`CELL_SIZE_X = 40.75`, `CELL_SIZE_Y = 41.00`). Khi merge cần kiểm tra xem phần cứng thực tế hiện tại dùng bàn cờ nào để không làm lệch tọa độ robot thật.

---

### 3.3. Branch `feature/visual-correction-v2` (Commit: `d4b9f9a`)
* **Nội dung mới (kế thừa từ `main` + 4 commits):**
  1. **Bộ lọc trung vị ổn định vị trí gắp (`VisualPickEstimator.aggregate_targets`):**
     * Lấy mẫu `VISUAL_PICK_SAMPLE_COUNT = 3` snapshot liên tiếp và tính trung vị (median) của `(col, row)` nhằm chống nhiễu hạt camera làm lệch tay gắp.
  2. **Tự động xác nhận nước đi sau khi người chơi rút tay khỏi bàn cờ:**
     * Thêm module `src/vision/turn_completion_monitor.py`: Theo dõi bàn tay bằng model EgoHands (`models/hand_best_egohands.pt`). Khi bàn tay xuất hiện trên bàn cờ rồi rời đi quá `HAND_ABSENCE_SECONDS = 0.8s`, hệ thống tự động kích hoạt `try_auto_confirm_move()` để chụp snapshot kiểm tra luật cờ mà người chơi **không cần phải bấm phím SPACE thủ công**.
  3. **Tùy chỉnh thông số:**
     * `MOVE_SPEED = 60` (tăng tốc độ robot lên 60%).
     * `IDLE_X = -95.439, IDLE_Y = 114.829, IDLE_Z = 219.976`.
* **Xung đột với `virtual`:**
  * Xung đột tại `src/ui/input_handler.py`:
    * Nhánh `virtual` thêm phím tắt: `G` (test kẹp DO0), `H` (test kẹp DO1), `I` (lấy info robot FR3).
    * Nhánh `visual-correction-v2` thêm logic `auto_retry` cho `_handle_space_key` và hàm `try_auto_confirm_move`.
    * **Xử lý:** Gộp cả hai rất dễ dàng vì các đoạn code nằm ở các nhánh `if key == ...` và các hàm bổ trợ riêng biệt.

---

### 3.4. Branch `test/merging-newest` (Commit: `9dad851`)
* **Nội dung mới:**
  * Kế thừa toàn bộ `feature/visual-correction-v2`.
  * Gộp thêm nhánh UI/Debug từ `integration/vision-occupancy-filter`:
    * Thêm `src/ui/debug_dashboard.py` (menu debug hiển thị FPS, độ trễ, tham số trạng thái robot).
    * Thêm giao diện trang chủ, nút Settings, banner thông báo người thắng cuộc trên Pygame (`src/ui/board_renderer.py`).
    * Vòng lặp Menu khởi động sau khi chỉnh camera (`main.py`).
* **Đánh giá rủi ro:**
  * Các commit UI có ghi chú `(not tested)` ("Added extra parameters for the robot's state (not tested)").
  * Tuy có thêm giao diện tiện ích cho người dùng cuối nhưng đây là nhánh **thử nghiệm tổng hợp** (test branch), có mức độ ổn định chưa bằng `feature/visual-correction-v2`.

---

## 4. BẢNG PHÂN TÍCH TỔNG QUAN & PHÁN QUYẾT TÍCH HỢP

| Tiêu chí | `function/new-gripper-controls` | `main` | `feature/visual-correction-v2` | `test/merging-newest` |
| :--- | :---: | :---: | :---: | :---: |
| **Mức độ hoàn thiện** | 100% (Đã vào main) | 100% (Production) | 95% (Tính năng hoàn chỉnh) | 80% (Đang thử nghiệm UI) |
| **Giá trị mang lại cho dự án** | Điều khiển kẹp mới | Auto-Cali RTMPose + Gripper | Auto-confirm nước cờ + Median pick | Giao diện Dashboard + UI Settings |
| **Độ phức tạp khi giải quyết xung đột** | Thấp (2 files) | Thấp (2 files) | Thấp - Trung bình (3 files) | Trung bình (3 files + UI refactor) |
| **Tác động tới Phase 3 Virtual Simulator** | Không ảnh hưởng (hỗ trợ Dry Run) | Không ảnh hưởng Core Simulator | Cần chú ý model Hand khi test offline | Cần chú ý vòng lặp Pygame trong `main.py` |
| **Khuyến nghị hành động** | **BỎ QUA** (Đã có trong main) | **NÊN MERGE** (Lấy nền tảng chuẩn) | **NÊN MERGE** (Tính năng giá trị cao) | **CHƯA NÊN MERGE** (Chờ test UI xong) |

---

## 5. LỘ TRÌNH MERGE ĐỀ XUẤT (RECOMMENDED INTEGRATION STRATEGY)

Để đảm bảo an toàn tuyệt đối cho kiến trúc Phase 3 Virtual Robot Simulator của bạn mà vẫn tiếp nhận đầy đủ các cải tiến thị giác và phần cứng mới nhất:

1. **Bước 1 — Không cần merge `function/new-gripper-controls`:** Vì nhánh này đã được tích hợp hoàn toàn trong `main`.
2. **Bước 2 — Merge `main` trước:**
   * Giúp đồng bộ nhánh của bạn với RTMPose ONNX và cơ chế kẹp mới.
   * Xử lý xung đột: Giữ nguyên `PROJECT_CONTEXT.md` của Phase 3; giữ file test tại `tests/unit/test_visual_pick_estimator.py`.
3. **Bước 3 — Merge `feature/visual-correction-v2`:**
   * Thu nạp tính năng tự động xác nhận nước cờ khi rút tay và bộ lọc trung vị điểm gắp.
   * Xử lý xung đột tại `src/ui/input_handler.py` bằng cách giữ cả hai: phím tắt test kẹp (`G`, `H`, `I`) của nhánh virtual và cơ chế `try_auto_confirm_move` của visual-correction.
4. **Bước 4 — Tạm hoãn `test/merging-newest`:**
   * Để nhóm phát triển UI hoàn thiện và kiểm thử các tính năng Menu/Debug Dashboard trước khi đưa vào codebase chính thức.
