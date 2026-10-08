# Chọn logic lấy tâm quân

Hai dòng mới trong `config.py`:

```python
VISUAL_RING_PICK_ENABLED = False
VISUAL_CURRENT_PICK_ENABLED = True
```

| Ring | Current | Luồng chạy |
| --- | --- | --- |
| False | True | Luồng hiện tại, giữ nguyên bbox/height/top-face theo các cờ cũ |
| True | False | Luồng vòng màu mới |
| True | True | Ưu tiên luồng vòng màu mới; không fallback khi thất bại |
| False | False | Chặn gắp; không tự chọn tâm bbox hoặc tâm ô |

Luồng mới chỉ dùng bbox của `best.pt` để lấy ROI. Các điểm viền được
khử méo lens và giao tia với mặt phẳng ở độ cao quân, rồi fit đường tròn
trong đơn vị mm. Tâm vòng tròn thành XY bàn, grid số thực và được luồng
robot hiện có nội suy qua R1–R4/TCP. Không lấy tâm ellipse trên ảnh làm XY.

Vòng phải có mực đỏ/tím/xanh và mặt trắng ở cả hai phía. Chỉ thân trắng,
nét chữ, vòng thiếu/che khuất, tâm cạnh tranh hoặc ảnh sai resolution
không được dùng làm điểm gắp. Các quan sát mới phải đạt consensus theo mm,
bao gồm quan sát cuối cùng; hết thời gian hoặc thiếu vòng không đổi sang
bbox/foot/tâm ô. Capture refresh, retry và các kiểm tra FEN vẫn dùng luồng cũ.

Module mới dùng `camera_intrinsics.json` và `perspective.npy` hiện tại;
pose được dựng lại mỗi chu kỳ gắp. Không yêu cầu profile commissioning
`pick_geometry.json` của chế độ top-face cũ. Camera, resolution, crop, focus
phải khớp intrinsics; homography phải tương ứng camera/bàn hiện tại.

Dùng các giá trị đang có `VISUAL_HEIGHT_BOARD_MM`, `VISUAL_HEIGHT_PIECE_MM`
và giới hạn `VISUAL_TOP_*`, không tự thay đổi chúng. Chiều cao hiện tại là
7 mm (giá trị thử cho bbox); khi đánh giá vòng mặt trên cần đối chiếu với
chiều cao mặt quân đo thật. Không thêm bù hướng tâm lần hai vào geometry.

Mặc định luồng mới tắt để giữ hành vi hiện tại. Khi thử, đặt Ring=True,
Current=False, xem ảnh diagnostic `COLORED RING PICK` và dùng hover/test
hiện có trước khi đo gắp. Unit test/phối cảnh tổng hợp chỉ xác nhận phần mềm;
sai số mm và tỷ lệ gắp thật cần đo trên robot ở giữa, mép và góc bàn.
