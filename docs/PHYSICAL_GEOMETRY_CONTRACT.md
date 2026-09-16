# PHYSICAL GEOMETRY & COORDINATE CONTRACT

**Repository:** `Khenggg/xiangqi_robot_TrainningAI_Final_6`  
**Branch:** `feature/virtual-robot-3d-simulator`  
**Phase:** P1  
**Status:** Approved Canonical Specification  
**Date:** 2026-09-15  

---

## 1. MỤC ĐÍCH & TẦM NHÌN

Tài liệu này xác lập **Hợp đồng Hình học Vật lý & Chuỗi Hệ Tọa độ Chuẩn hóa** (Canonical Physical Geometry & Coordinate Contract) cho dự án Xiangqi Robot.

Mục tiêu giải quyết dứt điểm các vấn đề nền tảng từ Phase P0:
1. **Loại bỏ phân tán và trùng lặp hằng số:** Toàn bộ kích thước vật lý bàn cờ và quân cờ được định nghĩa tại một nguồn chân lý duy nhất (Single Source of Truth) trung lập về ngôn ngữ.
2. **Khắc phục lỗi đảo ngược phe cờ:** Chuẩn hóa quy ước hàng cờ và vị trí quân giữa backend Python, AI, và Three.js 3D Viewer (Black ở `row=0..4`, Red ở `row=5..9`).
3. **Phân biệt rạch ròi hình học nội tại và vị trí ngoại tại:** Kích thước bàn cờ nội tại không bị phụ thuộc vào điểm dạy (teaching points) hay vị trí hiển thị 3D.
4. **Hiệu chỉnh sai số tính toán P0:** Làm rõ tính đồng nhất $40.0\text{ mm} \times 40.0\text{ mm}$ của bước lưới ô cờ.
5. **Thiết lập rào chắn an toàn kiểm thử (Hardware Safety Boundary):** Phân tách tuyệt đối giữa bộ unit test tự động an toàn và các công cụ kiểm thử phần cứng thật.

---

## 2. NGUỒN CHÂN LÝ HÌNH HỌC (`shared/physical_geometry.json`)

Nguồn chân lý duy nhất cho toàn bộ kích thước vật lý là file `shared/physical_geometry.json`. Định dạng JSON chuẩn ISO cho phép cả Python và JavaScript tiêu thụ trực tiếp mà không cần duplicate code.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "XiangqiRobotPhysicalGeometry",
  "description": "Language-neutral canonical single source of truth for measured physical geometry of board and pieces.",
  "schema_version": 1,
  "unit": "mm",
  "board": {
    "outer_width": 367.0,
    "outer_length": 410.0,
    "columns": 9,
    "rows": 10,
    "column_spacing": 40.0,
    "row_spacing": 40.0
  },
  "piece": {
    "diameter": 22.5,
    "height": 9.43
  },
  "board_convention": {
    "black_home_row": 0,
    "red_home_row": 9,
    "col_min": 0,
    "col_max": 8,
    "row_min": 0,
    "row_max": 9
  }
}
```

### 2.1. Kích Thước Đo Đạc Vật Lý (Measured Physical Values):
- **Bàn cờ:**
  - Chiều ngang phủ bì (`outer_width`): $367.0\text{ mm}$
  - Chiều dọc phủ bì (`outer_length`): $410.0\text{ mm}$
  - Số cột lưới (`columns`): $9$ cột (tương ứng các đường dọc $col \in [0, 8]$)
  - Số hàng lưới (`rows`): $10$ hàng (tương ứng các đường ngang $row \in [0, 9]$)
  - Bước lưới ngang (`column_spacing`): $40.0\text{ mm}$
  - Bước lưới dọc (`row_spacing`): $40.0\text{ mm}$
- **Quân cờ:**
  - Đường kính (`diameter`): $22.5\text{ mm}$ (Bán kính $R = 11.25\text{ mm}$)
  - Chiều cao (`height`): $9.43\text{ mm}$

### 2.2. Kích Thước Phái Sinh Hình Học (Derived Dimensions):
- **Vùng chơi thực tế (Playable Grid Area):**
  - Chiều ngang vùng chơi giữa cột 0 và cột 8: $(9 - 1) \times 40.0\text{ mm} = 320.0\text{ mm}$.
  - Chiều dọc vùng chơi giữa hàng 0 và hàng 9: $(10 - 1) \times 40.0\text{ mm} = 360.0\text{ mm}$.
- **Độ rộng lề bàn cờ (Border Margins):**
  - Lề ngang trái/phải (`margin_x`): $(367.0 - 320.0) / 2 = 23.5\text{ mm}$.
  - Lề dọc trên/dưới (`margin_y`): $(410.0 - 360.0) / 2 = 25.0\text{ mm}$.

---

## 3. HIỆU CHỈNH TOÁN HỌC P0 (P0 ARITHMETIC RECTIFICATION)

> [!NOTE]
> Trong báo cáo Phase P0, một ghi nhận mâu thuẫn hình học đã được nêu:
> *"Grid Spacing Y: config.py là 40.0mm nhưng Three.js canvas là 410/9 ≈ 45.5mm"*.
>
> **Xác minh kỹ thuật tại Phase P1:**
> - Bàn cờ Cờ Tướng có phần gỗ lề bao quanh lưới kẻ.
> - Chiều dài phủ bì $410.0\text{ mm}$ bao gồm lề trên $25.0\text{ mm}$ và lề dưới $25.0\text{ mm}$.
> - Khoảng cách thực tế giữa hàng 0 và hàng 9 là $410.0 - 25.0 - 25.0 = 360.0\text{ mm}$.
> - Với 9 khoảng cách hàng, bước lưới dọc chính xác là:
>   $$\Delta Y = \frac{360.0\text{ mm}}{9} = 40.0\text{ mm}$$
> - Hoàn toàn khớp với bước lưới ngang giữa 8 khoảng cách cột:
>   $$\Delta X = \frac{367.0 - 23.5 - 23.5}{8} = \frac{320.0\text{ mm}}{8} = 40.0\text{ mm}$$
> 
> Do đó, lưới ô cờ vật lý hoàn toàn vuông vức $40.0\text{ mm} \times 40.0\text{ mm}$. Việc canvas Three.js cũ chia đều $410 / 9$ là cách vẽ phác thảo texture cũ không trừ lề, đã được sửa đổi triệt để trong `robot-3d-viewer/board.mjs`.

---

## 4. CHUỖI HỆ TỌA ĐỘ (COORDINATE FRAME CHAIN)

Hệ thống vận hành theo chuỗi biến đổi tọa độ phân cấp rõ ràng:

```
[image_px] (Pixel 1280x720)
    │
    ▼  Homography (perspective.npy)
[board_grid] (col: 0.0..8.0, row: 0.0..9.0 - Continuous Float)
    │
    ▼  grid_to_metric_mm (40.0 mm pitch, Origin at col=0, row=0)
[board_metric_mm] (u_mm: 0..320, v_mm: 0..360)
    │
    ├─► Extrinsic Bilinear Interpolation (Teaching Points R1-R4) ──► [robot_base] (FR3/FR5 mm)
    │                                                                     │
    │                                                                     ▼ Kinematics
    │                                                               [tool / TCP]
    ▼
[3d_world] (Three.js meters, origin at Virtual Robot Base; Board Center at [0.48, 0.0], Grid Origin at [0.32, -0.18])
```

### 4.1. Chi tiết các Coordinate Frames:
1. **`board_grid`:**
   - Đơn vị: Chỉ số lưới liên tục (`col`, `row` dạng `float`).
   - Gốc: $(0.0, 0.0)$ tại giao điểm Xe Đen Trái.
   - Hướng trục: `col` tăng sang phải ($0 \to 8$), `row` tăng về phía người chơi Đỏ ($0 \to 9$).
2. **`board_metric_mm`:**
   - Đơn vị: Milimét ($mm$).
   - Gốc: $(0.0, 0.0)\text{ mm}$ tại điểm giao $(col=0, row=0)$ trên mặt bàn cờ.
   - Công thức biến đổi:
     $$u_{mm} = col \times 40.0\text{ mm}$$
     $$v_{mm} = row \times 40.0\text{ mm}$$
3. **`robot_base`:**
   - Đơn vị: Milimét ($mm$).
   - Gốc: Tâm đáy chân đế tay máy công nghiệp.
   - Quy ước: Hàng (`row`) tăng dần dọc theo chiều âm trục $X$ robot ($-X_{robot}$), cột (`col`) tăng dần dọc theo chiều dương trục $Y$ robot ($+Y_{robot}$), trục $Z$ hướng thẳng đứng lên trên ($+Z_{robot}$).
4. **`3d_world` (Three.js Virtual Simulation):**
   - Đơn vị: Mét ($m$).
   - Gốc: $(0, 0, 0)$ tại chân đế robot ảo Three.js. Trục $X$ sang ngang bên phải robot, trục $Y$ hướng lên trên (Up-vector), trục $Z$ hướng về phía trước (bàn cờ).
   - **Ma trận biến đổi từ robot base sang 3D world (Extrinsics Transform):**
     $$R = \begin{bmatrix} 0 & -1 & 0 \\ 0 & 0 & 1 \\ -1 & 0 & 0 \end{bmatrix}, \quad \det(R) = +1.0, \quad \mathbf{t} = [0, 0, 0]^T$$
     Ánh xạ trục: $X_{world} = -Y_{robot}$, $Y_{world} = +Z_{robot}$, $Z_{world} = -X_{robot}$.
   - **Tâm bàn cờ ảo (Board Center in 3D World):**
     - Nguồn chân lý: `shared/virtual_fr3_scene.json` (`board_center_in_3d_world_m`)
     - $X = 0.00\text{ m}$, $Y = 0.05\text{ m}$, $Z = 0.36\text{ m}$
     - Tương ứng trong `robot_base`: $X = -0.36\text{ m}$, $Y = 0.00\text{ m}$, $Z = 0.05\text{ m}$.
   - **Tọa độ của gốc lưới cờ $(col=0, row=0)$ trong `3d_world`:**
     Vùng chơi có độ rộng playable $0.320\text{ m}$ (nửa rộng $0.160\text{ m}$) và chiều dài playable $0.360\text{ m}$ (nửa dài $0.180\text{ m}$). Tọa độ bất kỳ ô $(col, row)$ được tính bởi hàm chuẩn `boardPointToXYZ(col, row)` trong `robot-3d-viewer/board.mjs`:
     $$X_{3d}(col) = \text{boardCenterX} + \frac{playableWidthM}{2} - col \times cellM = 0.00 + 0.16 - col \times 0.04$$
     $$Z_{3d}(row) = \text{boardCenterZ} - \frac{playableDepthM}{2} + row \times rowSpacingM = 0.36 - 0.18 + row \times 0.04$$
     $$Y_{3d} = \text{boardSurfaceY} = 0.05\text{ m}$$
     Tọa độ 4 góc bàn cờ trong `3d_world` (khớp tuyệt đối với $R \cdot \mathbf{p}_{robot} + \mathbf{t}$):
     - $(col=0, row=0)$ (Xe Đen Trái / Black Left Rook): $(X = +0.16\text{ m}, Y = 0.05\text{ m}, Z = +0.18\text{ m})$
     - $(col=8, row=0)$ (Xe Đen Phải / Black Right Rook): $(X = -0.16\text{ m}, Y = 0.05\text{ m}, Z = +0.18\text{ m})$
     - $(col=0, row=9)$ (Xe Đỏ Trái / Red Left Rook): $(X = +0.16\text{ m}, Y = 0.05\text{ m}, Z = +0.54\text{ m})$
     - $(col=8, row=9)$ (Xe Đỏ Phải / Red Right Rook): $(X = -0.16\text{ m}, Y = 0.05\text{ m}, Z = +0.54\text{ m})$

### 4.2. Làm Rõ Về Tọa Độ Gốc và Tâm Bàn Cờ (Origin vs. Center Clarification):
> [!IMPORTANT]
> Cần phân biệt rõ ràng giữa **Tâm bàn cờ (Board Center)** và **Gốc lưới cờ (Grid Origin)**:
> 1. Trong `shared/virtual_fr3_scene.json` và `robot-3d-viewer/board.mjs`, tâm bàn cờ ảo được đặt tại $(X = 0.00\text{ m}, Y = 0.05\text{ m}, Z = 0.36\text{ m})$.
> 2. Điểm $(X = +0.16\text{ m}, Y = 0.05\text{ m}, Z = +0.18\text{ m})$ là **tọa độ của gốc lưới $(col=0, row=0)$** trong không gian 3D, hoàn toàn không phải là tâm bàn cờ.
> 3. Trong `config.py` ($X=200, Y=-100$) và điểm dạy robot thật R1 ($X=350.2, Y=-180.5$), đây là các tọa độ ngoại tại (extrinsic mounting pose) của gốc $(col=0, row=0)$ trong hệ trục của chân đế robot thật (`robot_base`), tách rời hoàn toàn khỏi hình học nội tại.


---

## 5. CHÍNH SÁCH BIẾN ĐỔI TỌA ĐỘ & BIÊN (BOUNDARY POLICY)

Hàm chuyển đổi tọa độ trong `src/domain/geometry.py`:
- `grid_to_metric_mm(col, row, strict=False) -> (u_mm, v_mm)`
- `metric_to_grid(u_mm, v_mm, strict=False) -> (col, row)`

### Nguyên tắc vận hành:
1. **Hỗ trợ tọa độ thực liên tục (Continuous Floating-Point):**  
   Hỗ trợ đầy đủ các tọa độ float sub-cell (như $col=4.13, row=5.08$) phục vụ thuật toán bù vị trí gắp thị giác (`VisualPickEstimator`) hoặc quân cờ xô lệch nhẹ trên thực tế.
2. **Không ép biên ngầm (NO SILENT CLAMPING):**  
   Tuyệt đối không sử dụng `max(0, min(8, col))` âm thầm ép các vật thể nằm ngoài bàn cờ vào ô biên (như lỗi cũ trong detector từng gặp).
3. **Chế độ kiểm tra nghiêm ngặt (`strict=True`):**  
   Khi bật `strict=True`, nếu tọa độ vượt ra ngoài phạm vi $[col_{min}, col_{max}]$ hoặc $[row_{min}, row_{max}]$, hàm lập tức ném ngoại lệ `ValueError`.
4. **Chế độ mở rộng (`strict=False`):**  
   Khi `strict=False`, hàm tính toán ngoại suy tuyến tính tự do mà không cắt gọt giá trị, cho phép tính toán vị trí quân cờ ngoài bàn hoặc bãi chứa quân bị ăn.

---

## 6. QUY ƯỚC BÀN CỜ 3D VIEWER (`layout.mjs`)

Đã sửa chữa dứt điểm lỗi đảo ngược phe cờ (Red/Black Inversion Bug) trong Three.js:
- **Phe Đen (Robot AI / Black):**
  - Chiếm giữ hàng: `row = 0..4`
  - Hàng tướng / sĩ / tượng / mã / xe: `row = 0`
  - Vị trí Tướng Đen (King Black): $(col=4, row=0)$
  - Hàng pháo: `row = 2` ($col \in \{1, 7\}$)
  - Hàng tốt: `row = 3` ($col \in \{0, 2, 4, 6, 8\}$)
- **Phe Đỏ (Người chơi / Red):**
  - Chiếm giữ hàng: `row = 5..9`
  - Hàng tướng / sĩ / tượng / mã / xe: `row = 9`
  - Vị trí Tướng Đỏ (King Red): $(col=4, row=9)$
  - Hàng pháo: `row = 7` ($col \in \{1, 7\}$)
  - Hàng tốt: `row = 6` ($col \in \{0, 2, 4, 6, 8\}$)
- Tổng số quân cờ khởi tạo: đúng $32$ quân ($16$ Đỏ, $16$ Đen).

---

## 7. BẢO MẬT & PHÂN PHỐI DỮ LIỆU TĨNH (`serve.mjs`)

Để Three.js viewer truy cập được file JSON gốc mà không duplicate dữ liệu:
- Static HTTP Server trong `robot-3d-viewer/serve.mjs` mở một endpoint được cấp phép tường minh (whitelist):
  $$\text{GET } /shared/physical_geometry.json \longrightarrow \text{200 OK}$$
- **Cơ chế chống Path Traversal nghiêm ngặt:**
  - Chuẩn hóa đường dẫn bằng `path.normalize()`.
  - Từ chối mọi yêu cầu chứa `..` ra ngoài thư mục cho phép.
  - Chặn toàn bộ truy cập vào mã nguồn Python, config (`config.py`), hoặc file hệ thống khác (trả về `403 Forbidden` hoặc `404 Not Found`).

---

## 8. CẤU TRÚC KIỂM THỬ AN TOÀN (TEST SAFETY BOUNDARY)

Dự án thiết lập rào chắn cô lập kiểm thử an toàn phần cứng:
- **`tests/unit/` (Safe Automated Tests):**  
  Chỉ chứa các unit test thuần túy không phụ thuộc socket hay hardware:
  - `test_physical_geometry.py`: Kiểm thử đo đạc, phái sinh, chuyển đổi tọa độ, immutability, và config aliases.
  - `test_board_layout.py`: Kiểm thử quy ước 32 quân cờ và vị trí tướng trong viewer qua Node.js ESM loader.
  - `test_occupancy_filter.py`: Kiểm thử bộ lọc thị giác 2 lớp (Dual Geometry & Distance Gate).
  - `test_visual_pick_estimator.py`: Kiểm thử bù gắp thị giác và tọa độ Cartesian.
- **`tools/hardware_tests/` (Hardware Commissioning Scripts):**  
  Tất cả các script giao tiếp phần cứng thật (`test_4_rooks.py`, `test_corners.py`, `test_move_to_pos.py`, `test_tool_do0.py`,...) được chuyển vào đây.
- **Cấu hình `pytest.ini`:**
  ```ini
  [pytest]
  testpaths = tests/unit
  python_files = test_*.py
  norecursedirs = tools/hardware_tests .git __pycache__ node_modules
  ```
  Lệnh `pytest` mặc định sẽ **CHỈ** quét thư mục `tests/unit/`, đảm bảo an toàn tuyệt đối, không bao giờ vô tình kích hoạt chuyển động trên cánh tay robot thật.
