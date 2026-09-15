# Xiangqi Robot · 3D Digital Twin Viewer (FR3 / FR5)

Giao diện mô phỏng 3D Web-based và Digital Twin Mirror cho cánh tay robot công nghiệp FAIRINO FR3 và FR5 trong hệ thống Robot Đánh Cờ Tướng (Xiangqi Robot).

---

## 1. Tính Năng Chính

- **Bàn Cờ & 32 Quân Cờ 3D Chuẩn Hóa:**
  - Hiển thị đầy đủ bàn cờ và 32 quân cờ với texture chữ Hán truyền thống (KaiTi/STKaiti).
  - Quy ước chuẩn hóa toàn dự án: Phe **Đen (Robot)** ở `row 0..4` (Tướng Đen tại `(col=4, row=0)`), Phe **Đỏ (Người chơi)** ở `row 5..9` (Tướng Đỏ tại `(col=4, row=9)`).
- **Tiêu Thụ Hình Học Vật Lý Chuẩn (Canonical Geometry):**
  - Tự động nạp động thông số hình học từ `/shared/physical_geometry.json` qua `geometry.mjs`.
  - Không trùng lặp hằng số vật lý; quy đổi chính xác từ milimét ($mm$) sang mét Three.js ($m$): bàn $367 \times 410\text{ mm}$, ô $40 \times 40\text{ mm}$, quân $\varnothing 22.5 \times 9.43\text{ mm}$.
- **Hỗ Trợ Đa Dòng Robot (Mặc định FR3 & tùy chọn FR5):**
  - Mặc định khởi tạo dòng robot **FAIRINO FR3** (sải tay $520\text{ mm}$), tương thích hoàn toàn với URDF kinematics và Digital Twin backend.
  - Nạp mesh STL chi tiết cho cả 2 dòng robot FAIRINO FR3 và FR5.
  - Cho phép chuyển đổi profile linh hoạt ngay trên giao diện web.
- **Tích Hợp Scene Extrinsics & Transform Tọa Độ:**
  - Nạp cấu hình vị trí bàn cờ và robot từ `/shared/virtual_fr3_scene.json`.
  - Thiết lập ma trận biến đổi tọa độ chân đế robot sang không gian Three.js ($X_{world}=Y_{robot}, Y_{world}=Z_{robot}, Z_{world}=-X_{robot}$), đảm bảo 100% tầm với bàn cờ.
- **WebSocket Live Mirroring:**
  - Đồng bộ góc khớp thời gian thực với robot thật hoặc Virtual FR3 Backend thông qua luồng WebSocket telemetry 30 FPS.
- **Máy Chủ Tĩnh Bảo Mật (`serve.mjs`):**
  - Chạy local không cần cài đặt nặng.
  - Endpoint whitelist kiểm soát chặt chẽ truy cập `/shared/physical_geometry.json`, `/shared/robot_profiles/fr3.json`, và `/shared/virtual_fr3_scene.json`, ngăn chặn hoàn toàn tấn công Directory Traversal.

---

## 2. Cấu Trúc Thư Mục

```
robot-3d-viewer/
├── index.html        # Giao diện chính: Canvas Three.js + bảng điều khiển kết nối/profile (mặc định FR3)
├── styles.css        # Giao diện tối hiện đại, responsive
├── main.mjs          # Entrypoint Three.js: Quản lý Scene, Lights, Loop, Robot kinematics, Scene extrinsics
├── geometry.mjs      # Module tải & validate hình học vật lý từ shared/physical_geometry.json
├── layout.mjs        # Khởi tạo vị trí ban đầu 32 quân cờ (Black row 0..4, Red row 5..9)
├── board.mjs         # Dựng mesh bàn cờ, lưới ô cờ, quân cờ và hàm map tọa độ boardPointToXYZ theo scene
├── live_state.mjs    # Bộ lọc và validate gói tin telemetry WebSocket
├── serve.mjs         # Static HTTP server local có bảo vệ traversal và whitelist
└── assets/
    ├── fr3_v6/       # Mesh STL và URDF của FAIRINO FR3
    └── fr5_v6/       # Mesh STL và URDF của FAIRINO FR5
```

---

## 3. Hướng Dẫn Khởi Chạy

### Yêu cầu:
- [Node.js](https://nodejs.org/) (phiên bản 18+).

### Chạy máy chủ:
```bash
node serve.mjs [port]
# Mặc định mở port 8080 nếu không chỉ định
```

Mở trình duyệt tại: `http://localhost:8080/`.

---

## 4. Kết Nối Live Telemetry

1. **Phía Python Backend:** Khởi chạy `TelemetryPublisher` (trong `src/hardware/telemetry_publisher.py`), server mở tại `ws://127.0.0.1:8765`.
2. **Phía Web 3D Viewer:** Nhập địa chỉ WebSocket vào ô input (mặc định `ws://127.0.0.1:8765`), bấm **Connect live**.
3. Khi kết nối thành công, badge chuyển sang màu xanh **LIVE** và robot 3D sẽ chuyển động theo góc khớp nhận được.

### Định dạng gói tin WebSocket:
```json
{
  "type": "robot_state",
  "robot_model": "FR3",
  "timestamp": 1699999999.123,
  "joints": [j1, j2, j3, j4, j5, j6],
  "tcp": [x, y, z, rx, ry, rz],
  "gripper": true
}
```
*Lưu ý: Trường `robot_model` phải khớp với profile robot đang được chọn trên giao diện.*
