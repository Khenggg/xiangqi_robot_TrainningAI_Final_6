# Spec: Dual Geometry & Distance Filter for Chess Occupancy Detection

**Date:** 2026-09-09
**Status:** Ready

---

## Problem Statement
Mô hình YOLO11 (occupancy model) bị nhận diện nhầm các vật thể tròn ngoại cảnh (nắp chai, cốc, đồng hồ, vật thể ngoài bàn cờ hoặc giữa các ô cờ) thành quân cờ, khiến việc xác định biến động $T_1 / T_2$ bị sai lệch, dẫn tới nhận diện nước đi không chính xác và treo trạng thái game.

---

## User Stories

- **[P1]** Là hệ thống nhận diện, tôi muốn tự động loại bỏ các detection nằm ngoài phạm vi bàn cờ để không bị ảnh hưởng bởi đồ vật xung quanh.
  *Accepted when:* Bất kỳ vật thể nào có tâm chân quân cờ sau perspective transform nằm ngoài biên bàn cờ đều bị loại bỏ, không bị ép clamp vào cột 0 / hàng 0.

- **[P1]** Là hệ thống nhận diện, tôi muốn chỉ chấp nhận các detection nằm đủ gần các giao điểm hợp lệ của bàn cờ ($\text{dist} \le \Delta$) để loại bỏ các vật thể nằm lơ lửng giữa các ô cờ.
  *Accepted when:* Vật thể có tâm lệch quá $0.32$ đơn vị ô cờ so với giao điểm cờ gần nhất sẽ bị bỏ qua.

- **[P2]** Là hệ thống giám sát, tôi muốn tăng ngưỡng confidence và kiểm tra tỷ lệ khung hình ($w/h$) để loại bỏ các detection nhiễu mờ hoặc có hình dạng bất thường.
  *Accepted when:* Ngưỡng detection được nâng lên $0.45$, và bounding box có tỷ lệ $w/h \notin [0.55, 1.8]$ sẽ bị loại bỏ.

---

## Functional Requirements

1. **FR-01 (Strict Boundary Check):** Trong hàm `_build_occupancy()`, thay thế logic clamp cũ (`c = max(0, min(c, self.num_cols - 1))`) bằng kiểm tra biên thực tế: nếu $c_{raw} < -0.32$ hoặc $c_{raw} > 8.32$ hoặc $r_{raw} < -0.32$ hoặc $r_{raw} > 9.32$ thì hủy bỏ detection.
2. **FR-02 (Distance-to-Intersection Gating):** Tính khoảng cách Euclide $\text{dist} = \sqrt{(c_{raw} - c)^2 + (r_{raw} - r)^2}$ với $(c, r) = (\text{round}(c_{raw}), \text{round}(r_{raw}))$. Chỉ gán `grid[r][c] = True` nếu $\text{dist} \le 0.32$ (tương đương dung sai lệch tâm khoảng $13\text{ mm}$).
3. **FR-03 (Aspect Ratio & Confidence Filter):** Thêm bộ lọc tỷ lệ $0.55 \le \frac{x_2 - x_1}{y_2 - y_1} \le 1.80$ trước khi transform; nâng ngưỡng `conf` mặc định từ $0.35$ lên $0.45$ trong `camera_monitor.py`.

---

## Non-Functional Requirements

- **Performance:** Thời gian tính toán cho bộ lọc hình học thêm vào $\le 1\text{ ms}$ cho mỗi snapshot (không gây ảnh hưởng FPS).
- **Maintainability:** Tham số dung sai khoảng cách và confidence có thể tùy chỉnh hoặc định cấu hình linh hoạt.

---

## Success Criteria

- [ ] Các vật thể tròn ngoài bàn cờ không bao giờ bị map vào `grid[r][c]`.
- [ ] Các vật thể tròn nằm ở khoảng trống giữa các ô (khoảng cách $> 0.32$ ô) không bị nhận diện là quân cờ.
- [ ] Quân cờ thật đặt tại các giao điểm hợp lệ (kể cả hơi lệch tâm $\le 0.32$ ô) vẫn được nhận diện chính xác 100%.

---

## Out of Scope

- Huấn luyện lại model YOLO11 bằng dataset mới (sẽ thực hiện sau nếu các giải pháp code chưa đủ thỏa mãn trong môi trường đặc biệt).
- Can thiệp vào phần cứng hoặc camera driver.

