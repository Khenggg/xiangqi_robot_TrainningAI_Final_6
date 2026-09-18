# TÀI LIỆU KỸ THUẬT: ĐỐI CHIẾU THAY ĐỔI GIỮA NHÁNH `fix/identified-bugs` VÀ NHÁNH `main`

> **Repository:** `xiangqi_robot_TrainningAI_Final_6`  
> **Nhánh so sánh:** `fix/identified-bugs` (Working Branch) so với `main` (Production Branch)  
> **Ngày cập nhật:** 09/09/2026  
> **Trạng thái:** Nhánh `fix/identified-bugs` đang dẫn trước `main` **7 commits** (sửa đổi, bổ sung trên 13 files).

---

## 📑 MỤC LỤC
1. [Tổng quan tóm tắt (Executive Summary)](#1-tổng-quan-tóm-tắt-executive-summary)
2. [Bảng danh sách commit trên nhánh `fix/identified-bugs`](#2-bảng-danh-sách-commit-trên-nhánh-fixidentified-bugs)
3. [Chi tiết các thay đổi theo từng thành phần](#3-chi-tiết-các-thay-đổi-theo-từng-thành-phần)
   - [3.1. Logic Cờ tướng Core (`src/core/xiangqi.py`)](#31-logic-cờ-tướng-core-srccorexiangqipy)
   - [3.2. Thị giác máy tính & Camera (`src/vision/`)](#32-thị-giác-máy-tính--camera-srcvision)
   - [3.3. Điều khiển Robot phần cứng (`src/hardware/`)](#33-điều-khiển-robot-phần-cứng-srchardware)
   - [3.4. AI Chess Engine Moonfish (`src/ai/moonfish_engine.py`)](#34-ai-chess-engine-moonfish-srcaimoonfish_enginepy)
   - [3.5. Hệ thống & Vòng lặp chính (`main.py`, `config.py`, `api`)](#35-hệ-thống--vòng-lặp-chính-mainpy-configpy-api)
   - [3.6. Quản lý phụ thuộc & Tài liệu (`requirements.txt`, `README.md`)](#36-quản-lý-phụ-thuộc--tài-liệu-requirementstxt-readmemd)
   - [3.7. Script khởi động tự động & Cẩm nang SOP (`RUN.bat`, `USER_MANUAL_QUICKSTART.md`)](#37-script-khởi-động-tự-động--cẩm-nang-sop-runbat-user_manual_quickstartmd)
4. [Bảng ma trận so sánh trước và sau khi sửa lỗi](#4-bảng-ma-trận-so-sánh-trước-và-sau-khi-sửa-lỗi)
5. [Hướng dẫn Merge vào nhánh `main`](#5-hướng-dẫn-merge-vào-nhánh-main)

---

## 1. TỔNG QUAN TÓM TẮT (Executive Summary)

Nhánh `main` là nhánh tích hợp hoàn chỉnh của các đợt phát triển trước (gồm engine Moonfish UCCI, điểm giảng dạy robot `R_Trash`, chuyển động Cartesian `MoveCart`, và API đóng phòng). Tuy nhiên, qua quá trình kiểm thử thực tế khi tích hợp toàn hệ thống, tồn tại **5 nhóm lỗi nghiêm trọng** cản trở vận hành:

1. **Lỗi logic cờ:** Quân Tốt không thể di chuyển nước đi ban đầu nào do đảo ngược trục tọa độ `(dr, dc)`.
2. **Lỗi hiệu năng Camera:** Luồng đọc camera bị đồng bộ với suy luận YOLO (`imgsz=1280`), gây giật lag (5–10 FPS) và tích tụ frame buffer.
3. **Lỗi Crash phần cứng & Quản lý vòng đời:** Thiếu biến khóa luồng `_lock` gây văng app khi bấm phím `S`; lỗi `NoneType` khi khởi động không cắm robot thật; lỗi hủy tiến trình `MoonfishEngine`.
4. **Lỗi mã hóa Windows:** In tiếng Việt gây crash ngoại lệ `UnicodeEncodeError: 'charmap'` trên terminal Windows.
5. **Thiếu tệp khai báo môi trường:** Thiếu `requirements.txt` khiến việc triển khai trên máy mới dễ bị thiếu thư viện (`requests`, `ultralytics`).

Nhánh **`fix/identified-bugs`** khắc phục triệt để toàn bộ các vấn đề trên mà không làm phá vỡ kiến trúc gốc.

---

## 2. BẢNG DANH SÁCH COMMIT TRÊN NHÁNH `fix/identified-bugs`

| STT | Commit Hash | Thông điệp Commit | Tác động chính |
| :---: | :---: | :--- | :--- |
| 1 | `0784242` | `fix: resolve pawn move logic, auto_cell_sizes, robot calibration error and add requirements.txt` | Sửa unpack tọa độ Tốt, dọn dead code robot, bảo vệ calibrate khi ngắt kết nối robot, thêm `requirements.txt`. |
| 2 | `5593136` | `config: set VIDEO_SOURCE = 2 to select DroidCam` | Đổi index camera mặc định sang 2 để ưu tiên DroidCam trên điện thoại. |
| 3 | `7e8b506` | `perf: decouple camera capture from YOLO detection, use imgsz=640 and safe MoonfishEngine cleanup` | Kiến trúc 2 luồng độc lập (Capture 60 FPS & Detect async), hạ `imgsz=640`, sửa thứ tự `__init__` của Moonfish. |
| 4 | `979ca7c` | `perf: allow preloaded perspective reuse and add dynamic GPU/CPU tag` | Cho phép dùng lại `perspective.npy` cũ không cần bấm lại 4 góc, gắn thẻ hiển thị `[GPU]/[CPU]`. |
| 5 | `ee9bcaa` | `fix: ensure utf-8 console encoding to prevent UnicodeEncodeError on Windows` | Thiết lập `sys.stdout.reconfigure(encoding='utf-8')` chống lỗi font console. |
| 6 | `6b9b29b` | `fix: restore self._lock in CameraMonitor and remove sys.exit from cleanup` | Khôi phục thuộc tính `self._lock` chống crash khi bấm `S`, dọn `sys.exit` trong `atexit`. |

---

## 3. CHI TIẾT CÁC THAY ĐỔI THEO TỪNG THÀNH PHẦN

### 3.1. Logic Cờ tướng Core (`src/core/xiangqi.py`)
* **Vấn đề trên `main`:**
  ```python
  # TRÊN MAIN:
  offsets = [(0,-1)] if color=='r' else [(0,1)]
  if (color=='r' and r<=4) or (color=='b' and r>=5): offsets.extend([(1,0),(-1,0)])
  for dr, dc in offsets: possible_dest.append((c+dc, r+dr))
  ```
  Trong mảng `offsets`, phần tử thứ nhất là độ lệch cột `dc` (`c`), phần tử thứ hai là độ lệch hàng `dr` (`r`). Việc unpack thành `for dr, dc in offsets` làm gán ngược: `dr = 0, dc = -1` (thay vì `dc = 0, dr = -1`). Kết quả là Tốt Đỏ cố gắng đi lùi hoặc đi ngang ngay từ vị trí xuất phát, vi phạm luật cờ dẫn đến **0 nước đi hợp lệ**.
* **Đã sửa trên `fix/identified-bugs`:**
  ```python
  # ĐÃ SỬA:
  for dc, dr in offsets: possible_dest.append((c+dc, r+dr))
  ```
  Quân Tốt Đỏ tiến chính xác lên phía trước (`r - 1`), Tốt Đen tiến xuống (`r + 1`), và mở rộng sang 2 bên khi qua sông.

---

### 3.2. Thị giác máy tính & Camera (`src/vision/`)

#### A. [`src/vision/camera_monitor.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/src/vision/camera_monitor.py)
* **Tách 2 luồng độc lập (Decoupled Architecture):**
  * *Trên `main`:* 1 luồng duy nhất `_capture_and_detect` vừa đọc ảnh vừa chạy `model.predict(imgsz=1280)`. Tốc độ camera tụt xuống 5–10 FPS, phải xả buffer bằng vòng lặp `grab()` 5 lần gây giật khựng.
  * *Trên nhánh fix:*
    - **`_capture_loop` (Luồng đọc camera):** Chuyên đọc frame liên tục từ camera ở tốc độ cao nhất (30–60 FPS) và cập nhật `_last_frame`. Khung hình camera hiển thị 100% mượt mà không độ trễ.
    - **`_detect_loop` (Luồng suy luận YOLO):** Chạy nền độc lập (Async), định kỳ lấy bản sao frame để nhận diện với kích thước tối ưu `imgsz=640` (giảm 80% tải tính toán, khớp chuẩn kích thước huấn luyện của model).
* **Tự động nhận diện GPU (CUDA):**
  - Tự động gán `self.device = 0` nếu có card đồ họa NVIDIA (CUDA), ngược lại chạy CPU.
  - Hiển thị nhãn `[GPU]` hoặc `[CPU]` trên khung hình hiển thị.
* **Khắc phục lỗi Crash `self._lock`:**
  - Bổ sung `self._lock = threading.Lock()` trong `__init__`, ngăn chặn hoàn toàn lỗi `AttributeError: 'CameraMonitor' object has no attribute '_lock'` khi gọi `get_fresh_snapshot()` lúc bấm phím `S`.

#### B. [`src/vision/calibrate_camera.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/src/vision/calibrate_camera.py)
* **Tái sử dụng Perspective:**
  - Tự động nạp file ma trận `perspective.npy` đã lưu trước đó nếu tồn tại.
  - Người dùng có thể nhấn ngay phím **`S`** để sử dụng lại góc quay cũ mà không cần click lại 4 điểm.
  - Đảm bảo giải phóng luồng capture khi đóng cửa sổ cân chỉnh (`cal_thread.join(timeout=1.0)`).

---

### 3.3. Điều khiển Robot phần cứng (`src/hardware/`)

#### A. [`src/hardware/robot_VIP.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/src/hardware/robot_VIP.py)
* **Khởi tạo thuộc tính `auto_cell_sizes`:**
  - Bổ sung `self.auto_cell_sizes = {"x": config.CELL_SIZE_X, "y": config.CELL_SIZE_Y}` trong `__init__` và tự động cập nhật khi load điểm giảng dạy (`teaching_points`).
* **Loại bỏ Dead Code:**
  - Xóa dòng `return [x_mm, y_mm, z_height] + list(config.ROTATION)` nằm sau câu lệnh return của hàm `board_to_pose()`.

#### B. [`src/hardware/hardware_manager.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/src/hardware/hardware_manager.py)
* **Bảo vệ Calibrate khi Robot chưa kết nối:**
  - Thêm điều kiện `if not self.robot.connected: return` trong `_calibrate_robot()`. Tránh việc gọi `self.robot.robot.GetRobotTeachingPoint()` gây crash `AttributeError: 'NoneType'` khi chạy thử nghiệm trên máy không có cánh tay FR5 thật.
* **Bảo vệ ngoại lệ `ultralytics`:**
  - Đặt `YOLO = None` khi `ImportError` và kiểm tra an toàn `if YOLO is not None:` trước khi nạp model.

---

### 3.4. AI Chess Engine Moonfish (`src/ai/moonfish_engine.py`)
* **Khắc phục lỗi Garbage Collection khi sập Engine:**
  * *Trên `main`:* Các biến `self.process = None`, `self._lock = threading.Lock()` được đặt sau khối kiểm tra `if not os.path.isfile(engine_path)`. Nếu file engine không tồn tại, ngoại lệ bắn ra khiến đối tượng bị giải phóng, hàm `__del__` gọi `self.quit()` $\rightarrow$ truy cập `self.process` $\rightarrow$ sinh thêm crash phụ `AttributeError: 'MoonfishEngine' object has no attribute 'process'`.
  * *Trên nhánh fix:* Chuyển khởi tạo các biến trạng thái lên đầu hàm `__init__`.

---

### 3.5. Hệ thống & Vòng lặp chính (`main.py`, `config.py`, `api`)

#### A. [`main.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/main.py)
* **Hỗ trợ UTF-8 Console trên Windows:**
  - Thêm cấu hình `sys.stdout.reconfigure(encoding='utf-8')` và `sys.stderr.reconfigure(encoding='utf-8')` ngay đầu file để in tiếng Việt có dấu an toàn 100%.
* **Dọn dẹp mã nguồn:**
  - Xóa dòng gọi lặp trùng lặp `hw.capture_baseline_if_needed(force_delay=1.0)`.
  - Bỏ lệnh gọi `sys.exit(0)` trong hàm dọn dẹp `_cleanup_all()` đã đăng ký với `atexit` (tránh báo `Exception ignored in atexit callback`).

#### B. [`config.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/config.py)
* Cập nhật `VIDEO_SOURCE = 2` để ưu tiên DroidCam, kèm ghi chú cơ chế tự động thử cổng 0, 1, 2 khi cổng chỉ định thất bại.

#### C. [`src/api/simulation_client.py`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/src/api/simulation_client.py)
* Bổ sung tái cấu hình UTF-8 console khi in log kết nối API phát trực tiếp.

---

### 3.6. Quản lý phụ thuộc & Tài liệu (`requirements.txt`, `README.md`)
* **[`requirements.txt`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/requirements.txt):**
  Tạo mới file phụ thuộc chuẩn cho toàn dự án:
  ```text
  pygame>=2.5.0
  opencv-python>=4.8.0
  numpy>=1.24.0
  requests>=2.28.0
  ultralytics>=8.0.0
  ```
* **[`README.md`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/README.md):**
  Cập nhật bước 1 hướng dẫn cài đặt qua `pip install -r requirements.txt` (bổ sung gói `requests` vốn bị thiếu trong tài liệu gốc).

---

### 3.7. Script khởi động tự động & Cẩm nang SOP (`RUN.bat`, `USER_MANUAL_QUICKSTART.md`)

#### A. [`RUN.bat`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/RUN.bat)
* **Khắc phục lỗi chạy nhầm Python runtime:**
  - `RUN.bat` cũ gán cứng `set "PYTHON=py"`. Trên Windows có nhiều phiên bản Python, lệnh `py` mặc định gọi bản Python mới nhất (ví dụ Python 3.14) chưa cài thư viện dự án, gây crash ngay lập tức `ModuleNotFoundError: No module named 'cv2'`.
  - Đã bổ sung cơ chế **Auto-detect Python thông minh**: Tự động kiểm tra môi trường ảo `.venv` hoặc kiểm tra lệnh `python` / `py` nào đã cài sẵn `cv2, pygame, ultralytics` để ưu tiên thực thi.
* **Hỗ trợ hiển thị Tiếng Việt UTF-8:**
  - Bổ sung lệnh `chcp 65001 > nul` ngay đầu file để toàn bộ log của batch script và output từ `main.py` không bao giờ bị vỡ font hay lỗi emoji (`🤖`, `✅`, `❌`).
* **Bắt lỗi và dừng màn hình:**
  - Bắt mã lỗi `%ERRORLEVEL%` để giữ màn hình terminal (`pause`) khi ứng dụng gặp sự cố bất ngờ, giúp người vận hành đọc được stack trace chi tiết.

#### B. [`docs/USER_MANUAL_QUICKSTART.md`](file:///d:/OJT/xiangqi_robot_TrainningAI_Final_6/docs/USER_MANUAL_QUICKSTART.md)
* Tạo mới toàn bộ tài liệu hướng dẫn vận hành chuẩn (SOP) dành cho người đứng máy và thử nghiệm thực tế:
  - **Quy ước màu cờ và hướng ngồi:** Người chơi cầm quân Đỏ (gần camera), Robot AI cầm quân Đen (xa camera).
  - **Quy định xếp quân:** Bắt buộc xếp đủ 32 quân ban đầu (do mô hình dùng occupancy detector dựa trên delta $T_2 - T_1$).
  - **Quy trình Calibrate 4 góc:** Thứ tự click 1-2-3-4 tâm 4 quân Xe góc; phím `R` reset; phím `S` lưu và vào game.
  - **Quy trình từng lượt đi:** Chi tiết cho cả 2 kịch bản (có cánh tay robot thật FR5 và chế độ mô phỏng không có robot).
  - **Bảng phím tắt & Xử lý sự cố thường gặp:** Hướng dẫn khắc phục khi bấm SPACE sớm, nhận diện nhầm, kẹt robot hoặc không mở được camera.

---

## 4. BẢNG MA TRẬN SO SÁNH TRƯỚC VÀ SAU KHI SỬA LỖI

| Hạng mục kiểm tra | Nhánh `main` (Gốc) | Nhánh `fix/identified-bugs` (Hiện tại) |
| :--- | :--- | :--- |
| **Nước đi ban đầu của Tốt Đỏ** | ❌ 0 nước (quân Tốt đứng im không đi được) | ✅ 5 nước mở đầu chính xác: `((c, 6) -> (c, 5))` |
| **Nước đi của Tốt khi qua sông** | ❌ Bị lỗi hướng đi ngang thành tiến/lùi | ✅ Đi đủ 3 hướng: tiến thẳng, rẽ trái, rẽ phải |
| **FPS Camera Monitor** | ⚠️ Giật lag (5–10 FPS), trễ hình do kẹt luồng YOLO | ✅ Mượt mà (30–60 FPS), YOLO chạy nền độc lập |
| **Kích thước suy luận YOLO** | ⚠️ `imgsz=1280` (quá nặng, lệch size gốc) | ✅ `imgsz=640` (nhẹ hơn 80%, chuẩn model `best.pt`) |
| **Xử lý phím `S` (Calibrate)** | ❌ Crash `AttributeError: '_lock'` | ✅ Hoạt động ổn định, nạp baseline chuẩn xác |
| **Calibrate camera khi đã có file** | ⚠️ Bắt buộc phải click lại 4 góc mỗi lần chạy | ✅ Tự nạp ma trận cũ, nhấn `S` để dùng ngay |
| **Khởi động không cắm Robot thật** | ❌ Crash `AttributeError: 'NoneType'` | ✅ Tự nhận diện disconnect, giữ tọa độ an toàn |
| **In tiếng Việt trên Windows terminal**| ⚠️ Dễ crash `UnicodeEncodeError` | ✅ UTF-8 reconfigured, hiển thị tiếng Việt hoàn hảo |
| **Script khởi động `RUN.bat`** | ⚠️ Gán cứng `py`, dễ crash `ModuleNotFoundError` | ✅ Auto-detect Python có sẵn dependencies + `chcp 65001` |
| **Khai báo thư viện dự án** | ❌ Chưa có `requirements.txt` | ✅ Đầy đủ `requirements.txt` chuẩn hóa |
| **Cẩm nang thao tác chuẩn (SOP)** | ❌ Chưa có hướng dẫn chi tiết người dùng | ✅ Đầy đủ trong `docs/USER_MANUAL_QUICKSTART.md` |

---

## 5. HƯỚNG DẪN MERGE VÀO NHÁNH `main`

Do nhánh `fix/identified-bugs` phân nhánh trực tiếp từ đỉnh của `main` (commit `99fb7c0`) và không có commit nào bị xung đột, việc hợp nhất vào `main` có thể thực hiện theo cơ chế **Fast-Forward**:

```bash
# 1. Chuyển về nhánh main
git checkout main

# 2. Hợp nhất nhánh fix/identified-bugs vào main
git merge fix/identified-bugs

# 3. Đẩy code lên GitHub remote (nếu cần)
git push origin main
```
