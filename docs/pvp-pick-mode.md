# Điểm gắp v3 theo luồng PvP

Nhánh này dựa trên `feature/visual-correction-v2` tại `fb0598d`.
`VISUAL_PVP_PICK_ENABLED = True` trong `config.py` chọn đúng hàm đo điểm
gắp mà PvP tại `93fef3a` gọi: `get_visual_pick_targets()`.

Ảnh mới qua `get_fresh_snapshot()` (gồm chuyển BGR sang RGB và bộ lọc bàn
cũ) → `best.pt` → điểm `(center_x, y1 + 0.85 * bbox_height)` → homography
mặt bàn → median các mẫu → grid float → robot. Không dùng intrinsics,
chiều cao quân hoặc fit vòng tròn để tạo target của chế độ này.

Cờ PvP ưu tiên hơn ring/top-face/height/current. Tắt cờ này để phục hồi
router v2 và các chế độ cấu hình cũ. Chiều cao Z, TCP, R1–R4, offset,
model và file calibration không được thay đổi bởi bản chuyển luồng.

Nếu thiếu mẫu hợp lệ, giống PvP, robot nhận `visual_target=None` và gắp
theo tâm ô đã hiệu chỉnh. Đây là fallback, không phải phép đo tâm thực tế.
Ở R2/R3/R4, fallback dùng trực tiếp teaching point qua `board_to_pose()`;
target đo được dùng nội suy bilinear có offset. Xem log `[PVP PICK]`,
`[VISUAL PICK] Fallback` và `[CENTER XY]` để phân biệt.

AI và chế độ T dùng cùng router. Hover chỉ nhận target đo được; thiếu
target thì dừng hover, không dựng target giả vì nó có thể khác XY của
fallback tại góc bàn. Luồng ăn quân vẫn xác minh ô đích đã trống rồi đo
lại quân nguồn; xác minh sau motion và các guard pending/FEN vẫn giữ lại.

Kiểm thử offline xác nhận routing, fallback, capture refresh và giữ FEN
khi xác minh thất bại. Chưa chứng minh độ chính xác gắp thật tại R2/R4;
cần nghiệm thu trên camera/controller và bàn thật.
