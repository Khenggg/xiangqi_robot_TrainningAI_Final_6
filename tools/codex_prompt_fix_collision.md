# GỬI BẠN KỸ SƯ / GPT-6-SOL: BÀI TOÁN VA CHẠM GRIPPER VÀ BÀN CỜ (XIANGQI ROBOT)

Chào bạn, tôi bàn giao lại cho bạn một bài toán khá hóc búa trong repo `xiangqi_robot_TrainningAI_Final_6` (hệ thống cánh tay robot FAIRINO FR3 kết hợp mô phỏng PyBullet).

Lỗi va chạm giữa ngàm kẹp (gripper) với mặt bàn cờ và quân cờ đã xuất hiện rất nhiều lần. Các bạn agent trước đây đã thử can thiệp nhiều đợt nhưng gần như toàn "chữa cháy triệu chứng" (ví dụ: thấy báo va chạm thì viết hàm tự nhấc tay 65mm né tạm, hạ ngưỡng an toàn, hoặc ép MoveCart dẫn đến lỗi kỳ dị động học code 112). 

Dưới đây, tôi chỉ đóng vai trò người rà soát sơ bộ: gom lại các hiện tượng thực tế, manh mối từ lịch sử Git và log chạy thử để bạn nắm bối cảnh. **Bạn đừng vội tin ngay các hướng giải trước đây của tôi hay các agent khác**, vì có thể góc nhìn đó vẫn còn phiến diện hoặc chưa bao quát hết bài toán vật lý 6-DOF. Bạn hãy dùng năng lực suy luận chuyên sâu độc lập của mình để phân tích lại từ đầu (first principles) và đưa ra giải pháp kiến trúc thực sự chuẩn xác nhé.

---

## 1. CÁC HIỆN TƯỢNG VÀ MANH MỐI GHI NHẬN ĐƯỢC

### Manh mối 1: Nghi vấn bất đồng bộ hình học và nuốt ngoại lệ âm thầm (Lệch ~18.3 mm)
- Trong cấu hình `shared/robot_profiles/fr3.json`, trường `"provenance": "MEASURED_PHYSICAL"` ghi khoảng cách flange-to-TCP là `0.1683` m (168.3 mm).
- Tuy nhiên, trong `src/domain/geometry.py`, enum `ProvenanceStatus` hình như chưa có giá trị `MEASURED_PHYSICAL`. Khối `try...except Exception:` ở hàm đọc geometry dường như đang âm thầm nuốt lỗi và trả về giá trị mặc định là `0.150` m (150 mm).
- Trong khi đó, `src/simulation/virtual_fr3_backend.py` lại đọc thẳng giá trị 168.3 mm từ `shared/virtual_fr3_scene.json`.
- *Hiện tượng*: Có sự lệch pha 18.3 mm giữa các module runtime. Nếu một bên nghĩ tool dài 150mm còn mô hình thực tế dài 168.3mm, khi hạ kẹp xuống nó sẽ bị cắm sâu hơn dự tính gần 2cm.

### Manh mối 2: Sự nhập nhằng giữa Tâm Gắp (Grasp Center) và Đầu Ngón Tay (Fingertips)
- Trong `src/simulation/physics/gripper.py`, ngón kẹp dài 25 mm, độ sâu gắp phôi (grasp depth) là 12 mm $\implies$ tâm kẹp nằm cao hơn đầu ngón tay 12 mm.
- Khi một bài test hoặc planner ra lệnh hạ kẹp xuống vị trí quân cờ tại $Z = 10.5\text{ mm}$ (nửa chiều cao quân cờ): nếu hiểu Z này là điểm đặt tâm kẹp thì đầu ngón tay sẽ tụt xuống $Z = 10.5 - 12 = -1.5\text{ mm}$, tức là đâm xuyên qua mặt bàn cờ ($Z = 0.0\text{ mm}$).
- Module `collision_guard.py` chặn khẩn cấp vì clearance $< 0.5\text{ mm}$.
- *Hiện tượng*: Các module trong hệ thống dường như đang dùng lẫn lộn giữa khái niệm "Tâm kẹp quân cờ" và "Điểm tiếp xúc mút ngón tay chặn va chạm bàn".

### Manh mối 3: Quỹ đạo MoveJ bị võng xuống ở tầm thấp
- Khi robot di chuyển ngang giữa các ô cờ ở độ cao thấp bằng phép nội suy không gian khớp (`MoveJ`), đường đi trong không gian 3D tạo thành một cung võng xuống $> 10\text{ mm}$, quẹt qua mặt bàn hoặc các quân cờ đang đứng.
- Agent trước từng thử chuyển sang `MoveCart` (MoveL) toàn bộ để đi thẳng, nhưng vì bàn cờ Xiangqi khá rộng, cánh tay robot khi vươn ra các ô biên lại rơi vào điểm kỳ dị động học (Kinematic Singularity - mã lỗi 112 của FAIRINO).
- *Hiện tượng*: Cần một chiến lược chuyển động (Motion Planning) rõ ràng: đi ngang ở độ cao an toàn (transit corridor) rồi mới hạ thẳng đứng (approach/land), thay vì nội suy khớp tự do sát mặt bàn.

### Manh mối 4: Thân Tool (đoạn nối J6 Flange tới Palm) và nhánh mồ côi `fix/simulator-tool-board-penetration`
- Trong lịch sử Git có một nhánh `fix/simulator-tool-board-penetration` (commit `3635667`, `8bd51b5`). Họ phát hiện collider của gripper trong PyBullet trước đây chỉ có Palm và 2 ngón kẹp (cao tổng cộng 65mm), để hở một khoảng trống gần 100mm từ J6 flange tới palm không hề có khối va chạm. Khi cổ tay nghiêng, đoạn kim loại này cắt xuyên bàn cờ mà PyBullet không biết.
- Họ đã viết thêm `tool_bridge` và test `test_simulator_tool_collision_envelope.py`, nhưng nhánh này chưa được merge vào nhánh chính vì khi thêm bridge lại bị va chạm giả với quân cờ lân cận lúc hạ kẹp. Bạn hãy xem xét và đánh giá lại phần này.

### Manh mối 5: Xung đột góc nhìn bàn cờ Yaw 0° vs Yaw 90°
- Trước đây hệ thống và tập dataset `shared/cell_reachability_dataset.json` được tính toán cho bàn cờ đặt tại góc **Yaw 90°** (tâm `[-0.36, 0.0, 0.0105]`).
- Gần đây có thay đổi đưa scene về **Yaw 0°** (`[0.0, 0.36, 0.0105]`) để người dùng nhìn viewer cho thuận mắt. Việc này khiến tập dataset seed góc khớp bị lệch pha (đem seed của 90° giải cho 0°), dẫn đến việc cổ tay bị vặn giật khi giải IK.

---

## 2. KỲ VỌNG Ở BẠN

Tôi không áp đặt bất kỳ cách sửa cụ thể nào. Tôi muốn nhờ bạn:
1. **Khảo sát độc lập**: Mở các file mã nguồn liên quan (`src/domain/geometry.py`, `src/simulation/physics/gripper.py`, `src/simulation/physics/collision_guard.py`, `src/simulation/virtual_fr3_backend.py`, các file config trong `shared/`).
2. **Xác định nguyên nhân gốc rễ**: Tự phản biện lại 5 manh mối trên, xem đâu là bản chất vật lý cốt lõi.
3. **Thực hiện giải pháp dứt điểm**:
   - Sửa code chuẩn mực, sạch sẽ, nhất quán về mặt hình học và động học.
   - Tuyệt đối không dùng các biện pháp giả tạo như giảm ngưỡng an toàn, xóa assertion, hay viết thêm các hàm phục hồi chắp vá.
4. **Kiểm thử nghiệm thu**:
   - Chạy test xác nhận: `pytest tests/unit/test_phase3_final_master.py -q -x`
   - Chạy các test va chạm liên quan trong thư mục `tests/`.
   - Kết quả cuối cùng phải chứng minh được: robot gắp thả hoàn toàn trơn tru, không có hiện tượng va chạm hay đâm xuyên mặt bàn/vật thể (clearance $\ge 0.5\text{ mm}$, collision = 0).

Chúc bạn xử lý thuận lợi! Mọi kết quả hãy tóm tắt rõ ràng ở phần phản hồi cuối cùng.
