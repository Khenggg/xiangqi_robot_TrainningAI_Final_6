# CẨM NANG VẬN HÀNH VÀ THAO TÁC HỆ THỐNG XIANGQI ROBOT (USER MANUAL)

> **Tài liệu hướng dẫn vận hành chuẩn (SOP) dành cho người trực tiếp sử dụng & thử nghiệm hệ thống Robot Cờ Tướng.**  
> Phiên bản: 2.3 | Cập nhật: 09/09/2026

---

## 📋 MỤC LỤC
1. [Chuẩn bị trước khi khởi động](#1-chuẩn-bị-trước-khi-khởi-động)
2. [Cách khởi động chương trình](#2-cách-khởi-động-chương-trình)
3. [Quy trình cân chỉnh Camera (Calibration)](#3-quy-trình-cân-chỉnh-camera-calibration)
4. [Quy trình thi đấu ván cờ (Từng lượt đi)](#4-quy-trình-thi-đấu-ván-cờ-từng-lượt-đi)
   - [Chế độ A: Có cánh tay Robot FR5 thật](#chế-độ-a-có-cánh-tay-robot-fr5-thật)
   - [Chế độ B: Chạy mô phỏng / Không có Robot](#chế-độ-b-chạy-mô-phỏng--không-có-robot)
5. [Bảng phím tắt điều khiển](#5-bảng-phím-tắt-điều-khiển)
6. [Xử lý sự cố thường gặp (Troubleshooting)](#6-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. CHUẨN BỊ TRƯỚC KHI KHỞI ĐỘNG

### 1.1. Sắp xếp bàn cờ vật lý
* **Quy ước màu cờ:**
  * **Người chơi:** Cầm quân **ĐỎ** (ngồi ở phía gần camera hơn).
  * **Robot AI:** Cầm quân **ĐEN** (ở phía đối diện, xa camera hơn).
* **Xếp quân:** Xếp **ĐẦY ĐỦ 32 QUÂN CỜ** vào đúng vị trí xuất phát ban đầu của bàn cờ tướng tiêu chuẩn. Tuyệt đối không bỏ bớt quân cờ nào ra ngoài.

### 1.2. Thiết lập Camera / Điện thoại (DroidCam)
* **Góc nhìn camera:** Hướng camera từ trên cao nhìn chéo xuống bàn cờ sao cho:
  * Nhìn rõ toàn bộ bàn cờ (cả 4 góc và đường biên).
  * Bàn cờ chiếm khoảng **70% – 85%** diện tích khung hình (tránh đặt camera quá xa khiến quân cờ bị nhỏ, khó nhận diện).
  * Ánh sáng đồng đều, tránh bóng sọc bàn tay hoặc đèn chiếu thẳng gây chói lóa lên mặt quân cờ.
* **Nếu dùng DroidCam trên điện thoại:**
  1. Mở app DroidCam trên điện thoại và máy tính, bấm **Start**.
  2. Trong file `config.py`, biến `VIDEO_SOURCE = 2` đã được cấu hình sẵn để ưu tiên nhận DroidCam.

---

## 2. CÁCH KHỞI ĐỘNG CHƯƠNG TRÌNH

Bạn có thể chạy hệ thống bằng một trong hai cách:

### Cách 1: Chạy nhanh bằng file Batch (Khuyên dùng)
* Nhấp đúp chuột vào file **[`RUN.bat`](../RUN.bat)** ở thư mục gốc của dự án.
* Cửa sổ terminal sẽ tự động bật lên và kiểm tra các điều kiện môi trường.

### Cách 2: Chạy qua dòng lệnh Terminal
Mở PowerShell / Command Prompt tại thư mục dự án và gõ:
```bash
python main.py
```

---

## 3. QUY TRÌNH CÂN CHỈNH CAMERA (CALIBRATION)

Khi chương trình chạy lên, cửa sổ có tiêu đề **`CALIBRATE`** sẽ xuất hiện đầu tiên:

```text
               (Phía Robot / Quân ĐEN - Xa Camera)
               
        Điểm 1 [Xe Đen Trái]  ────────  Điểm 2 [Xe Đen Phải]
               │                                │
               │          SÔNG (HÀ HỚI)         │
               │                                │
        Điểm 4 [Xe Đỏ Trái]   ────────  Điểm 3 [Xe Đỏ Phải]
        
               (Phía Người / Quân ĐỎ - Gần Camera)
```

### Các bước thao tác:
1. **Trường hợp đã từng Calibrate trước đó:**
   * Bạn sẽ thấy các đường lưới màu vàng đã được vẽ sẵn đè lên bàn cờ.
   * Nếu thấy lưới vàng đã **khớp khít** với các đường kẻ chỉ của bàn cờ thật $\rightarrow$ Nhấn ngay phím **`S`** để vào game (không cần click lại).
2. **Trường hợp Calibrate lần đầu hoặc góc camera bị lệch:**
   * Nhấn phím **`R`** để xóa các điểm cũ.
   * Dùng chuột trái click **chính xác vào tâm giao điểm của 4 quân Xe ở 4 góc** theo đúng thứ tự 1-2-3-4:
     - **Click 1:** Tâm quân **Xe Đen (Trái)** (Góc trên bên trái)
     - **Click 2:** Tâm quân **Xe Đen (Phải)** (Góc trên bên phải)
     - **Click 3:** Tâm quân **Xe Đỏ (Phải)** (Góc dưới bên phải)
     - **Click 4:** Tâm quân **Xe Đỏ (Trái)** (Góc dưới bên trái)
   * Sau khi click đủ 4 điểm, hệ thống tự động vẽ lưới màu vàng gồm 10 hàng và 9 cột.
   * Kiểm tra: Nếu lưới vàng đã trùng khít lên các đường kẻ $\rightarrow$ Nhấn phím **`S`** để lưu và chuyển vào game.

---

## 4. QUY TRÌNH THI ĐẤU VÁN CỜ (TỪNG LƯỢT ĐI)

Sau khi bấm **`S`**, hai cửa sổ sẽ hiển thị song song:
* **`Camera Monitor`**: Video camera thực tế kèm bounding box AI và thẻ `[GPU]`/`[CPU]`.
* **`Xiangqi Robot VIP`**: Giao diện bàn cờ ảo 2D hiển thị trạng thái game.

---

### Chế độ A: Có cánh tay Robot FR5 thật (`config.DRY_RUN = False` & Cắm cáp Robot)

1. **Lượt của Người (Quân ĐỎ - Đi trước):**
   * Người chơi lấy tay nhấc **1 quân cờ Đỏ** đi đến ô hợp lệ trên bàn cờ thật.
   * **Rút tay ra hoàn toàn** khỏi tầm nhìn của camera.
   * Bấm phím **`SPACE`**.
   * Camera chụp ảnh, nhận diện nước đi và cập nhật lên bàn cờ ảo.

2. **Lượt của Robot (Quân ĐEN - Đi sau):**
   * AI tự động suy nghĩ (chạy luồng nền ~1–3 giây).
   * Cánh tay robot FR5 tự động kích hoạt:
     - Nếu là nước đi thường: Robot hút quân Đen $\rightarrow$ Nhấc lên độ cao an toàn $\rightarrow$ Đặt vào ô đích $\rightarrow$ Về vị trí nghỉ Home.
     - Nếu là nước ăn quân: Robot gắp quân Đỏ bị ăn bỏ vào bãi thải (`R_Trash`) $\rightarrow$ Sau đó gắp quân Đen thế vào vị trí đó.
   * Robot hoàn thành nước đi $\rightarrow$ Hệ thống tự động chụp lại mốc Baseline T1 mới $\rightarrow$ Báo `Your turn!` để chuyển lại lượt Người.

---

### Chế độ B: Chạy mô phỏng / Không có Robot (`DRY_RUN = True` hoặc Robot Disconnected)

1. **Lượt của Người (Quân ĐỎ):**
   * Đi 1 quân Đỏ trên bàn thật $\rightarrow$ Rút tay ra $\rightarrow$ Bấm **`SPACE`**.
   * *(Nếu camera bị che khuất hoặc nhận diện sai, bạn có thể dùng chuột kéo thả trực tiếp quân cờ trên màn hình bàn cờ ảo Pygame)*.

2. **Lượt của AI (Quân ĐEN):**
   * AI tính nước đi và in thông báo ra màn hình terminal, ví dụ:
     ```text
     🤖 AI đi: b_C (1,2) -> (4,2)
     👉 Hãy di quân này trên bàn thật, rồi bấm SPACE!
     ```
   * Bạn lấy tay **di chuyển quân Đen giúp AI trên bàn cờ thật**.
   * Rút tay ra $\rightarrow$ Bấm phím **`SPACE` 1 lần** (để AI chụp cập nhật trạng thái bàn cờ T1).
   * Bây giờ chuyển sang lượt của bạn: Đi tiếp quân Đỏ $\rightarrow$ Bấm **`SPACE`** để AI nhận diện nước tiếp theo.

---

## 5. BẢNG PHÍM TẮT ĐIỀU KHIỂN

| Phím tắt | Cửa sổ áp dụng | Chức năng |
| :---: | :---: | :--- |
| **`S`** | CALIBRATE | Lưu ma trận góc nhìn, chụp baseline ban đầu và bắt đầu ván cờ. |
| **`R`** | CALIBRATE | Xóa 4 điểm click cũ để chọn lại từ đầu. |
| **`SPACE`** | Game (Pygame) | Xác nhận hoàn thành nước đi / Yêu cầu AI chụp ảnh nhận diện. |
| **`Z`** | Game (Pygame) | **Rollback (Đi lại):** Khôi phục trạng thái bàn cờ về trước nước đi vừa bấm SPACE. |
| **Chuột trái**| Game (Pygame) | Chọn và di chuyển quân cờ thủ công khi camera nhận diện sai (Manual Override). |
| **`Q`** | Camera / CALIBRATE | Thoát chương trình an toàn, tự động ngắt kết nối robot và camera. |

---

## 6. XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)

### ❓ 1. Sau khi bấm `S`, bấm `SPACE` báo lỗi: "❌ Không thấy nước đi!"
* **Nguyên nhân 1:** Bạn vừa bấm `S` xong đã bấm ngay `SPACE` mà **chưa di chuyển quân Đỏ nào**.
  * 👉 **Khắc phục:** Hãy đi 1 quân Đỏ thật trên bàn trước, sau đó mới bấm `SPACE`.
* **Nguyên nhân 2:** Tay người chơi vẫn còn trong khung hình camera khi bấm `SPACE`.
  * 👉 **Khắc phục:** Rút tay ra hoàn toàn trước khi bấm.
* **Nguyên nhân 3:** Lưới vàng bị lệch khỏi các đường kẻ của bàn cờ.
  * 👉 **Khắc phục:** Đóng app, chạy lại `main.py`, bấm `R` ở cửa sổ Calibrate và click lại 4 tâm quân Xe cho thật chuẩn.

### ❓ 2. Báo lỗi: "⚠️ Lỗi nhận diện / Đi sai luật! Dùng chuột kéo thả"
* **Nguyên nhân:** Nước đi bị cản, hoặc nhận diện lệch sang ô bên cạnh (ví dụ Tốt chưa qua sông nhưng đi ngang).
* 👉 **Khắc phục:** Bạn chỉ cần dùng **chuột trái kéo thả quân cờ trên màn hình Pygame** vào đúng ô bạn vừa đi trên bàn thật. Hệ thống sẽ tự động đồng bộ lại và tiếp tục ván cờ bình thường.

### ❓ 3. Cửa sổ Camera không mở được hoặc báo "❌ Lỗi: Không mở được Camera!"
* **Nguyên nhân:** Camera đang bị ứng dụng khác chiếm giữ (như Zoom, Chrome, Camera Windows) hoặc sai index.
* 👉 **Khắc phục:**
  1. Tắt hết các ứng dụng đang dùng camera.
  2. Mở file `config.py`, thử đổi `VIDEO_SOURCE = 0` (Webcam tích hợp) hoặc `VIDEO_SOURCE = 1` / `2` (USB cam / DroidCam).

### ❓ 4. Robot báo lỗi kẹt `MoveCart` hoặc lỗi mã `112`
* **Nguyên nhân:** Tọa độ di chuyển chạm tới điểm kỳ dị (Singularity) hoặc ngoài tầm với.
* 👉 **Khắc phục:** Hệ thống đã tích hợp cơ chế tự phục hồi: nếu lỗi nhẹ sẽ tự coi là thành công và cho tiếp tục ván cờ. Nếu lỗi nặng làm dừng game, tắt nguồn robot, kéo cánh tay về vị trí an toàn rồi khởi động lại.
