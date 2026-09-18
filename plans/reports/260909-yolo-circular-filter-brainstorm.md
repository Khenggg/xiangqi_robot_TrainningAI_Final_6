# Brainstorm: Lọc vật thể tròn nhận diện nhầm trong YOLO11

**Date:** 2026-09-09

## Ideas Explored
1. **Lọc theo vùng hình học bàn cờ (Spatial & Grid Distance Masking):** Bỏ qua vật thể nằm ngoài bàn cờ hoặc nằm ngoài ngưỡng khoảng cách tới giao điểm bàn cờ ($\Delta \le 0.30$).
2. **Lọc kích thước & Tỷ lệ vật lý (Size & Scale Consistency Filter):** Kiểm tra aspect ratio $w/h \approx 1.0 \pm \epsilon$ và diện tích bbox so với chuẩn vật lý ô cờ.
3. **Xác thực thứ cấp bằng OpenCV (Color / Edge / Contrast Verification):** Dùng HSV / template / chữ khắc kiểm tra chất liệu và màu sắc quân cờ.
4. **Khai thác Logic Game làm bộ lọc (State-Aware Prior Filtering):** Chỉ cho phép quân cờ xuất hiện tại vị trí là nước đi hợp lệ từ FEN hiện tại.
5. **Nâng ngưỡng Confidence & Retrain với Negative Samples:** Tăng `conf` lên 0.45-0.50 và bổ sung mẫu âm ngoại cảnh để huấn luyện lại YOLO11.

## User's Direction
Người dùng chọn thực hiện phương án cải thiện bằng Code trước (**Phương án A: Dual Geometry & Distance Gate**, kết hợp tăng nhẹ ngưỡng confidence và aspect ratio), đồng thời giữ phương án finetune model làm giải pháp bổ sung nếu cần.

## Open Questions
1. Ngưỡng dung sai khoảng cách $\Delta$ tối ưu: Dự kiến thiết lập mặc định $\Delta \le 0.32$ đơn vị ô cờ (~$1.3\text{ cm}$) để người chơi đặt hơi lệch tay vẫn nhận diện tốt.
2. Ngưỡng Confidence: Tăng từ 0.35 lên 0.45 - 0.50 để lọc bớt các false-positive thấp tin cậy mà không làm miss quân cờ thật.

## Risks
1. Nếu người chơi đặt quân quá vội và lệch tâm $> 0.35$ ô cờ, bộ lọc có thể bỏ sót quân (tuy nhiên có thể điều chỉnh threshold hoặc dùng cơ chế Manual Override).
2. Tăng `conf` quá cao có thể miss quân khi điều kiện ánh sáng yếu (khắc phục: để ở mức an toàn 0.45 - 0.50).

