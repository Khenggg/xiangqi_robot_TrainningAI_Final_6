# FR3/FR5 · 3D Live Mirror (project mới, độc lập)

Project tối giản chỉ làm đúng 1 việc: hiển thị mô hình 3D tay robot FR3/FR5
và **mirror theo robot thật** qua WebSocket telemetry. Không có IDE Python,
không Firebase, không cờ tướng — bạn tự thêm phần đó vào sau nếu cần.

## Cấu trúc

```
robot-3d-viewer/
├── index.html        # giao diện: canvas 3D + chọn robot + nút Connect live
├── styles.css
├── main.mjs           # toàn bộ logic: dựng robot STL, WebSocket, animation
├── live_state.mjs     # validate gói tin telemetry (copy từ project gốc)
├── serve.mjs          # static server chạy local
└── assets/
    ├── fr3_v6/        # mesh STL + urdf tham khảo của FR3
    └── fr5_v6/        # mesh STL + urdf tham khảo của FR5
```

## Chạy thử

```bash
node serve.mjs
```

Mở `http://localhost:8080/`. Bạn sẽ thấy tay robot FR5 (mặc định), có thể
đổi sang FR3 bằng dropdown.

## Kết nối mirror với robot thật

1. Bên code điều khiển robot của bạn: chạy `TelemetryPublisher` (module đã
   gửi ở tin nhắn trước, đặt trong `src/hardware/telemetry_publisher.py` của
   project `xiangqi_robot`) — nó mở `ws://<ip-máy-robot>:8765` và phát góc
   khớp thật liên tục.
2. Trong ô **WebSocket** trên giao diện, nhập đúng địa chỉ đó (mặc định
   `ws://127.0.0.1:8765` nếu cùng máy).
3. Bấm **Connect live**. Trạng thái chuyển sang `LIVE` (màu xanh) và tay
   robot 3D sẽ di chuyển đúng theo tay robot thật, bao gồm cả lúc gắp/thả
   quân cờ — vì gói tin chỉ chứa góc khớp, không quan tâm nó đang làm gì.

### Định dạng gói tin (đã cố định, đừng đổi phía app trừ khi đổi cả 2 bên)

```json
{
  "type": "robot_state",
  "robot_model": "FR5",
  "timestamp": 1699999999.123,
  "joints": [j1, j2, j3, j4, j5, j6],
  "tcp": [x, y, z, rx, ry, rz]
}
```

`robot_model` phải khớp với robot đang chọn trên dropdown ("FR3" hoặc "FR5"),
nếu không gói tin sẽ bị từ chối (xem console log của trình duyệt).

## Muốn thêm gì tiếp theo?

- **Hiển thị kẹp gắp đóng/mở theo thật**: thêm trường `"gripper": true/false`
  vào gói tin bên Python, rồi trong `main.mjs` đọc `payload.gripper` để
  bật/tắt một mesh kẹp đơn giản (hình hộp/trụ) gắn ở cuối `wrist3_link`.
- **Vẽ bàn cờ tướng 3D bên dưới robot**: thêm một `THREE.PlaneGeometry`/lưới
  đường kẻ 9x10 vào `scene`, không ảnh hưởng gì đến phần robot hiện có.
- **Camera preset (Front/Back/Left/Right)**: có thể copy `camera-view.mjs`
  từ project `frnsimulation-main` nếu muốn giống bản gốc, nhưng
  `OrbitControls` mặc định ở đây đã đủ dùng để xoay/zoom tự do.
