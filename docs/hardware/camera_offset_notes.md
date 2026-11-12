# Ghi chú về Vấn đề Sai lệch Hệ tọa độ Cánh tay Robot (Camera Offset)

## 1. So sánh hai phương pháp xác định tọa độ

*   **Phương pháp Pixel-to-MM (Hiện tại):**
    *   Sử dụng hình ảnh từ Camera để lấy tọa độ Pixel của quân cờ, sau đó dùng ma trận biến đổi (Perspective Transform) để chuyển sang tọa độ mm thực tế.
    *   *Nhược điểm:* Dễ bị gặp lỗi thị sai (Parallax error - camera không thể nhìn thẳng đứng vuông góc mọi điểm), méo viền ống kính, và nhiễu (bóng đổ, ánh sáng chập chờn), dẫn đến tọa độ trung tâm quân cờ rập rình, không ổn định.
*   **Phương pháp Tọa độ Lưới Cố định (Grid-based tĩnh - Ý tưởng đề xuất):**
    *   Quy định sẵn tọa độ (X, Y) mm cho từng giao điểm/ô trên bàn cờ thông qua đo đạc và tính toán (Ví dụ khoảng cách các ô là 30mm đều nhau). Cánhtay robot chỉ chạy đến đúng tọa độ tĩnh đó dựa trên Logic nước đi (từ Camera/AI trả về vị trí lưới lô-gic chứ không trả về tọa độ vật lý).
    *   *Ưu điểm:* Độ chính xác cao, lặp lại tuyệt đối, loại bỏ hoàn toàn mọi sai số rung lắc từ Camera. Tính toán cực nhanh.
    *   *Nhược điểm:* Bắt buộc bàn cờ và đế robot phải được cố định (ghim ốc/dán keo) vào cùng một mặt phẳng, tuyệt đối không được xê dịch vật lý dù chỉ 1mm trong suốt quá trình chơi. Độ cao Z cũng phải phẳng.

---

## 2. Phân tích lỗi hiện tại: Tay robot gắp bị lệch sang phải và lên trên

Hiện tượng gắp luôn bị chệch một hướng cụ thể (ví dụ: lệch phải, lệch lên trên) là một lỗi kinh điển gọi là **Sai số tịnh tiến (Translation Offset)** trong thị giác máy tính. Dưới đây là 3 hướng giải quyết nếu giữ nguyên phương pháp Pixel-to-MM hiện tại:

### Cách 1: Thêm biến "Bù trừ tọa độ" (Software Offset) - Ưu tiên thử đầu tiên
*   **Dấu hiệu nhận biết:** Robot bị lệch hướng (lên trên, qua phải) y hệt nhau ở MỌI VỊ TRÍ trên bàn cờ. Chỗ nào cũng lệch một khoảng cách tương đương.
*   **Giải pháp:** Xử lý bằng phần mềm. Bù trừ (trừ đi) một hằng số vào lệnh tọa độ cuối cùng trước khi chuyển lệnh cho cánh tay robot di chuyển:
    *   `X_robot = X_camera_tính_ra - Delta_X` *(ví dụ Delta_X = 5mm sang phải thì trừ đi 5)*
    *   `Y_robot = Y_camera_tính_ra - Delta_Y` *(ví dụ Delta_Y = 3mm lên trên thì trừ đi 3)*

### Cách 2: Calibrate (Hiệu chuẩn lại) ma trận biến đổi Camera
*   **Dấu hiệu nhận biết:** Mức độ lệch không đồng đều. Ở giữa bàn cờ thì gắp khá chuẩn, nhưng càng ra góc bàn cờ thì càng bị lệch nhiều hơn.
*   **Giải pháp:** Camera có thể đã bị vô tình chạm nhẹ làm xê dịch (ví dụ gật xuống 1 độ, hoặc xoay nghiêng). Ma trận quy đổi cũ không còn đúng với thực tế. Cần chạy lại bước thiết lập camera ban đầu (hiệu chuẩn lấy lại 4 điểm ở 4 góc của bàn cờ trên camera) để OpenCV tính toán lại ma trận `getPerspectiveTransform` góc nhìn mới.

### Cách 3: Triệt tiêu ảnh hưởng của bóng đổ (Shadow Interference)
*   **Dấu hiệu nhận biết:** Thường bị lệch ở một số quân cờ cụ thể có bóng đen in rõ xuống mặt bàn do hướng chiếu của bóng đèn trong phòng.
*   **Giải pháp:** Thuật toán (ví dụ OpenCV) tìm trọng tâm khối (Centroid) / Bounding Box có thể nhận diện gộp lẫn cả "quân cờ" và cái "bóng đổ" của nó thành 1 vật thể. Điều này kéo tâm tọa độ bị lệch tịnh tiến sang phía cái bóng (lên trên/sang phải).
    *   *Khắc phục phần cứng:* Thêm đèn hắt sáng từ nhiều hướng để triệt tiêu bóng đen, chiếu sáng đều toàn bàn.
    *   *Khắc phục phần mềm:* Tinh chỉnh lại ngưỡng cắt ảnh nhị phân (Thresholding binary / Mask) để hệ thống nhận diện loại bỏ bóng đen, chỉ bắt đúng vòng tròn của quân cờ.

---

## 3. Cách triển khai Tọa độ Lưới Cố định (Grid-based mm)

Nếu bạn quyết định chuyển sang dùng tọa độ cố định để triệt tiêu hoàn toàn sai số máy ảnh, dưới đây là quy trình thực hiện:

### Bước 3.1: Đo đạc và Khai báo Hằng số
Bạn cần đo thực tế trên bàn cờ vật lý của bạn bằng thước kẹp điện tử để lấy 2 thông số:
*   `GRID_SIZE_X`: Chiều dài 1 ô cờ theo trục X (Cột). *Cách đo chuẩn: Đo từ mép vạch cột 1 đến cột 9, rồi chia cho 8.*
*   `GRID_SIZE_Y`: Chiều dài 1 ô cờ theo trục Y (Hàng). *Cách đo chuẩn: Đo từ mép vạch hàng 1 đến hàng 10, rồi chia cho 9.*

### Bước 3.2: Xác định Tọa độ Gốc (Origin Point)
Cánh tay robot cần biết điểm bắt đầu (giao điểm A1 hoặc 0,0) nằm ở đâu trong hệ tọa độ không gian mm của nó.
*   Dùng bộ điều khiển tay robot di chuyển đầu gắp đến **CHÍNH TÂM** của điểm giao cắt dưới cùng bên trái của bàn cờ (ví dụ Cột 0, Hàng 0).
*   Ghi lại tọa độ X, Y hiển thị trên bộ điều khiển robot. Đây sẽ là `BASE_X` và `BASE_Y`.

### Bước 3.3: Công thức Chuyển đổi Logic sang Thực tế
Khi Camera/AI trả về nước đi (Ví dụ Mã ở cột `col`, hàng `row`):
*   `Tọa_độ_gắp_X_mm = BASE_X + (col * GRID_SIZE_X)`
*   `Tọa_độ_gắp_Y_mm = BASE_Y + (row * GRID_SIZE_Y)`

*(Lưu ý: Công thức trên giả định bạn đặt trục X,Y của bàn cờ song song hoàn hảo với trục X,Y của robot. Nếu bị xoay chéo, bạn sẽ cần nhân thêm với một ma trận xoay góc Sin/Cos tương ứng. Tốt nhất là căn chỉnh bàn cờ thật thẳng hàng ngay từ đầu.)*

---

## 4. Hỏi - Đáp: Camera bị nghiêng khi dùng Tọa độ Lưới thì sao?

**Câu hỏi:** *Nếu tôi chuyển sang dùng tọa độ Grid-based (mm), nhưng lúc Calibrate (Hiệu chuẩn) góc nhìn thì cái Camera của tôi vô tình bị lắp nghiêng, hoặc chân đế camera hơi lệch sang một bên thì có bị sao không? Cánh tay có gắp trượt không?*

**Câu trả lời:** **KHÔNG BỊ SAO CẢ! Đây chính là điểm "ăn tiền" nhất của phương pháp này.**

Khi bạn chuyển sang dùng Grid-based (mm), thuật toán đã tách rời hoàn toàn thành 2 thế giới độc lập:
1.  **Thế giới AI/Logic (Của Camera):** Nhiệm vụ duy nhất của camera lúc này là cung cấp mảng tọa độ lô-gic kiểu như *(Từ: cột 3 hàng 4 -> Đến: cột 3 hàng 5)*.
2.  **Thế giới Vật lý (Của Robot):** Cứ có tọa độ lô-gic *(cột 3 hàng 4)* là nó tự móc công thức Grid-base ra tính thành milimet rùi phi thẳng đến đo.

Do đó, dù camera của bạn có bị:
*   Bị nghiêng góc (VD: Xoay chéo góc 10 độ, gập xuống).
*   Bị méo hình (Do ống kính góc rộng Fisheye).
*   Độ cao treo camera thấp hay cao.

Thì thuật toán OpenCV xử lý ảnh lúc Calibrate **chỉ cần nhận diện đủ 4 góc bàn cờ để uốn lại tấm ảnh** (warp perspective). Miễn là sau khi uốn xong, AI Model của bạn vẫn đọc (detect) được trong ô Cột 3 - Hàng 4 đang là quân "Mã", thì bước số (1) đã hoàn thành. Cánh tay robot ở bước số (2) hoàn toàn bị "mù" (không quan tâm đến ảnh camera thế nào), nó chỉ biết được nhận lệnh đến (Col 3, Row 4) và áp hệ số mm cố định vào để chạy mà thôi.

## 5. Cần bổ sung những gì nếu chuyển sang Tọa độ Lưới (mm)?

Để ý tưởng quy chuẩn (mm) chạy trơn tru, bạn sẽ cần bổ sung một vài khối mã (Code) và chỉnh sửa thiết lập vật lý (Hardware) như sau:

### 5.1 Phần Cứng (Hardware)
1. **Thước kẹp / Thước đo điện tử:** Để đo `GRID_SIZE_X` (ví dụ 32.5mm) và `GRID_SIZE_Y` (ví dụ 33.0mm) thật tỉ mỉ đến hàng thập phân. Sai 0.5mm x 9 ô là lệch cả nửa lóng tay rồi!
2. **Kẹp cố định đế Robot & Bàn Cờ:** Bạn bắt buộc phải có nẹp gỗ, ngàm vít hoặc băng keo 2 mặt loại siêu dính để ghim chặt vị trí của cả đế tay robot lẫn bàn cờ xuống mặt bàn. Cấm kỵ việc xê dịch trong lúc chơi.
3. **Mặt bàn siêu phẳng:** Đảm bảo trục Z (độ cao từ mặt cờ lên không trung) của tất cả 90 ô cờ là bằng nhau. Nếu mặt bàn gồ ghề (trái cao, phải thấp), hút chân không/ngàm kẹp sẽ cắm xuống quá mạnh hoặc hút hụt khí.

### 5.2 Phần Mềm (Software & Code)
Bạn sẽ không cần đụng đến (hoặc phải đập bỏ bớt) phần Code cũ chuyển đổi tọa độ Pixel sang MM nữa. Thay vào đó, bạn sẽ viết một hàm (Function) mới:

1. **Từ điển (Dictionary) tọa độ Hàng / Cột:**
   *  Viết một hàm ánh xạ lô-gic bàn cờ sang hệ Cột (0-8) và Hàng (0-9). Ví dụ: A1 = (0,0), B1 = (1,0), C3 = (2,2) v.v...
2. **Hàm tính toán thuật toán rẽ nhánh Inverse Kinematics (IK) tĩnh:**
   Lập trình một Class/Hàm có thông số cấu hình:
    ```python
    # Ví dụ thông số bạn phải đo
    BASE_X = 150.0  # mm - Tọa độ X gốc mũi kẹp so với đế Robot
    BASE_Y = 100.0  # mm - Tọa độ Y gốc mũi kẹp so với đế Robot
    GRID_X = 32.5   # mm - Khoảng cách 1 ô theo chiều X
    GRID_Y = 32.5   # mm - Khoảng cách 1 ô theo chiều Y
    
    def logic_to_physical(col, row):
        target_x = BASE_X + (col * GRID_X)
        target_y = BASE_Y + (row * GRID_Y)
        return target_x, target_y
    ```
3. **Mã xử lý Lệch góc (Tùy chọn nâng cao):**
   Nếu xui xẻo bạn lỡ dán bàn cờ xuống hơi lệch (không vuông góc 90 độ hoàn hảo với Robot), bạn sẽ cần thêm Code ma trận xoay Vector `(X * cos(θ) - Y * sin(θ))` để xoay bù hướng tọa độ. Tuy nhiên, nếu bạn dán thẳng thớm bằng thước Eke thì có thể bỏ qua bước này.
4. **Trục Z nhấc cờ an toàn:**
   Hàm di chuyển cánh tay phải tuân thủ nghiêm ngặt quy trình: Dịch chuyển X,Y ở độ cao Z an toàn (không va chạm cờ khác) -> Cắm trục Z thẳng đứng -> Hút/Kẹp -> Rút Z thẳng đứng -> Di chuyển X,Y.

* đo từ xe đen (phải) qua xe đen (trái) / 8
* đo từ xe đen (phải) qua xe đỏ (phải) / 9
=> chiều dài và chiều rộng của mỗi ô cờ