# Nhận diện cờ tướng + tự hiệu chỉnh bằng 4 QR

Project robot giữ UI, luật cờ, Moonfish, API simulation và SDK FR5. Backend mới
`cchess_qr` dùng ONNX của project `chinese-chess-recognition` để phân loại 90 giao
điểm. Checkpoint YOLO `models/best.pt` được dùng riêng cho *visual correction*
(tâm thực của quân); ONNX giữ trách nhiệm nhận dạng loại quân và thế cờ. Không
cần chạy OpenMMLab.

## Phạm vi đã tích hợp

- `main.py`: preview camera mặc định; `--play` chơi với AI, di chuyển quân đen bằng
  tay; `--robot` dùng FR5 với cấu hình đã đo.
- `src/vision/qr_calibration.py`: giải mã 4 QR, bù lệch, cập nhật homography.
- `src/vision/xiangqi_recognizer.py`: preprocessing đúng model upstream, chuyển
  nhãn sang board nội bộ/FEN, kiểm tra kết quả ổn định và nước đi hợp lệ.
- `src/vision/qr_board_monitor.py`: sở hữu camera, nhận diện nền, công bố ảnh và
  ma trận cùng thời điểm; không dùng ảnh hoặc phép hiệu chỉnh quá hạn.
- `src/vision/visual_correction.py`: sau khi đã biết ô có quân, phát hiện vòng
  tròn của quân trong vùng nhỏ quanh ô và trả về tâm thực tế để gắp.
- `src/vision/yolo_visual_correction.py`: chạy checkpoint YOLO một lớp `piece`,
  đổi tâm bounding-box sang tọa độ lưới QR rồi hợp nhất với phép tìm vòng tròn.
- `src/hardware/board_robot_mapping.py`: ghép phép đổi grid → camera → robot XY.
- `HardwareManager` và `InputHandler` đã nối backend mới; đường YOLO cũ vẫn còn
  cho mã gọi cũ với `VISION_BACKEND="yolo"`.

Bản thư mục ban đầu thiếu source `main.py`, `config.py`; hai file này được tạo
lại để chạy backend mới. Các giá trị vật lý cũ trong cache không được suy đoán.
Chế độ play hiện khởi đầu từ thế khai cuộc. Preview có thể đọc thế cờ khác và in
FEN, nhưng lượt đi do người dùng cung cấp, không thể suy ra chỉ từ ảnh.

## 1. Dán QR và đo khoảng lệch

Camera cố định phía trên, nhìn xuống; nhìn được trọn bàn cờ và cả 4 QR.
QR phải dán cố định trên cùng mặt phẳng với bàn cờ, dịch chuyển cùng bàn cờ.
Không bật chế độ mirror camera. QR càng rõ, lưới càng ổn định.

Các PNG đã tạo trong `assets/qr_markers/`. Mã chứa đúng các chuỗi sau:

| QR | Giao điểm thật được tham chiếu | Tọa độ logic |
|---|---|---|
| `XQ:TL` | Xe đen bên trái | (0,0) |
| `XQ:TR` | Xe đen bên phải | (8,0) |
| `XQ:BR` | Xe đỏ bên phải | (8,9) |
| `XQ:BL` | Xe đỏ bên trái | (0,9) |

Trái/phải là theo bàn cờ chuẩn có đen ở trên, đỏ ở dưới. ID giữ nguyên khi xoay
bàn; phần mềm không sắp QR theo trái/phải của ảnh camera.

Tạo `config/qr_board.json` từ mẫu `config/qr_board.example.json`, thay tất cả
`null` bằng số đo thật. `cell_mm=[dx,dy]` là khoảng cách giữa hai giao điểm liền
kề theo ngang/dọc (bàn chuẩn có 8 khoảng ngang và 9 khoảng dọc). Đo cả khoảng qua
sông: phiên bản này giả định các khoảng dọc bằng nhau.

`qr_to_corner_mm=[dx,dy]` là vector **từ tâm QR tới giao điểm thật**:

- X dương: từ cột 0 sang cột 8.
- Y dương: từ hàng đen 0 sang hàng đỏ 9.
- QR nằm ngoài trên-trái thường có offset `(+,+)`.
- QR nằm ngoài trên-phải: `(-,+)`; dưới-phải: `(-,-)`; dưới-trái: `(+,-)`.

Ví dụ minh họa, KHÔNG phải số đo bàn thật: ô 40×45 mm, QR TL nằm lệch ra trái
30 mm và lên trên 25 mm thì `cell_mm=[40,45]`, offset TL `[30,25]`.
Mỗi QR được phép có khoảng lệch khác nhau. Mã không phải giao điểm góc bàn cờ.

Phép tính: `QR_grid = corner_grid - offset_mm / cell_mm`. Homography ánh xạ
4 tâm QR trong ảnh tới 4 tọa độ QR đã biết trên mặt phẳng bàn. Từ phép nghịch
đảo tính được 4 góc thật và 90 giao điểm. Bù lệch theo trục bàn nên vẫn đúng khi
xoay hoặc dịch bàn; không cộng trừ một số pixel cố định.

Khoảng lệch là dữ liệu phải đo một lần. Bốn QR chỉ chứa ID không thể tự cung cấp
những khoảng cách vật lý chưa biết. Kích thước QR không cần biết nếu dùng tâm,
nhưng phải đủ lớn để giải mã từ độ cao lắp camera; giữ vùng trắng xung quanh.

## 2. Cài đặt và chạy preview

Chạy tại thư mục gốc project robot, Python 3.12:

Môi trường `.venv_qr` đã được chuẩn bị trên máy hiện tại. Có thể chạy thẳng dòng
cuối sau khi điền `config/qr_board.json`. Hai dòng đầu dùng khi cài trên máy khác.

```powershell
py -3.12 -m venv .venv_qr
.\.venv_qr\Scripts\python.exe -m pip install -r requirements-qr.txt
.\.venv_qr\Scripts\python.exe -X utf8 -B main.py --camera 0
```

SPACE in FEN khi bàn đã ổn định. `S` lưu ảnh tham chiếu vào `config/` (chỉ khi
QR đã xác định được bàn cờ). Q/ESC thoát. Chưa nối robot trong preview.
Đổi `--camera` nếu dùng thiết bị khác; không tự đổi camera khi thiết bị được
chọn lỗi vì sẽ làm sai phép đổi tọa độ robot.

Model nhận dạng thế cờ đã tải: `models/cchess_nano_v3.onnx`, 31,101,356 bytes.

- Nguồn: https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition/blob/main/onnx/layout_recognition/nano_v3-0319.onnx
- SHA256: `da66ba9809f15127f8ae729b1755e42ee61c100c4f9979ce0ef13602ac471298`
- Code nguồn: https://github.com/TheOne1006/chinese-chess-recognition
- Preprocessing đối chiếu `core/helper_4_kpt.py` và `core/runonnx/full_classifier.py`
  trong Hugging Face Space: warp 450×500, margin 50, crop giữa 400×450, resize
  280×315, BGR→RGB, ImageNet mean/std. Adapter ghép warp/crop thành một phép.
- Model trả probabilities `[1,90,16]`; lớp `x` và confidence thấp là chưa rõ,
  không được đổi thành ô trống rồi đưa vào điều khiển.

Model hiệu chỉnh vị trí là `models/best.pt`. Checkpoint hiện có lớp duy nhất
`piece`, vì thế nó không được dùng để quyết định quân là Xe/Mã/Tướng hay màu gì;
nó chỉ xác định tâm quân thật. Khi tâm YOLO và vòng tròn không đồng thuận, robot
không được nhận mục tiêu đó. QR vẫn là nguồn duy nhất cho 4 góc bàn.

Có thể tạo lại PNG bằng `python -m tools.qr_setup markers --out <folder_moi>`.

## 3. Hiệu chỉnh camera → robot một lần

QR tự cập nhật vị trí bàn cờ trong ảnh. Robot cần một phép đổi thứ hai từ pixel
sang XY tính bằng mm trong đúng hệ `user=1`, `tool=0` hiện dùng bởi FR5.

1. Cố định camera so với robot, giữ nguyên độ phân giải/focus/zoom sau hiệu chỉnh.
2. Khi bàn ở vị trí tham chiếu, dạy/đo XY của bốn **giao điểm thật** TL,TR,BR,BL
   trong hệ robot. Chụp bằng `S` trong preview khi bàn chưa bị dịch chuyển.
3. Tạo file JSON từ `robot_reference.example.json`, điền `robot_points_xy_mm`
   theo đúng thứ tự trên, `xy_limits_mm` là phạm vi XY được phép hoạt động,
   `robot_user=1`, `robot_tool=0`. Hai trường pixel/độ phân giải sẽ được lệnh dưới
   lấy từ ảnh; không cần tự điền.
4. Chạy, thay tên ảnh/file đo:

```powershell
python -m tools.qr_setup bind --image config/reference_123.png --layout config/qr_board.json --robot-points config/measured_robot_corners.json --out config/robot_reference.json
```

Lệnh này chỉ đọc ảnh và số đo, không kết nối hay di chuyển robot. Có thể nhập
trực tiếp đủ dữ liệu vào `robot_reference.json` nếu đã có cặp pixel/XY chính xác.

Sau đó `grid_to_robot = camera_to_robot × grid_to_camera_current`. Ma trận
`camera_to_robot` giữ nguyên, QR cập nhật `grid_to_camera_current` khi bàn dịch
chuyển. Tọa độ đặt quân cũng cập nhật, không chỉ tọa độ gắp.

Camera bị di chuyển so với robot phải hiệu chỉnh lại tham chiếu. Chỉ 4 QR gắn
trên bàn không phân biệt được bàn dịch với camera dịch. Homography cũng không
giải quyết bàn nghiêng/lên xuống, mặt bàn cong hoặc méo ống kính mạnh; bố trí này
áp dụng bàn phẳng chuyển động trong cùng mặt phẳng XY, camera nhìn từ trên.
Z và góc tool vẫn lấy từ profile FR5 đã dạy.

## 4. Chạy ván cờ

```powershell
python -B main.py --play --camera 0
```

Xếp thế khai cuộc. Chờ `Ready`, đi đỏ và bấm SPACE. Chương trình nhận diện
toàn bộ bàn, kiểm tra nước đi và gọi Moonfish. Trong `--play`, làm nước đen
được in ra trên bàn thật; camera xác nhận xong mới trả lượt đỏ.

Để dùng FR5, điền profile đã đo vào `config/robot_motion.json` theo mẫu tương
ứng. Cần robot reference và QR layout đầy đủ:

```powershell
python -B main.py --robot --camera 0
```

`--robot` là thao tác kết nối/enable robot và có thể vận hành thật. Phần tích hợp
không tự chạy lệnh này khi kiểm thử. Khởi động không tự đưa tay về HOMECHESS.

Nhận diện dùng ba frame ổn định và confidence tối thiểu 0.80 cho tất cả 90 ô.
Ngưỡng này cần đánh giá trên bộ quân/camera thật; scores không phải bảo đảm về
độ chính xác. Các nước mơ hồ bị từ chối, không đoán theo khoảng cách.

Trước mỗi nước robot, kiểm tra bàn còn khớp trạng thái game, đóng băng ma trận
cho nước đó và kiểm tra QR trước từng lệnh di chuyển/kẹp. Mất mã, ảnh quá hạn,
hoặc dịch quá ngưỡng `motion_tolerance_mm` sẽ ngăn lệnh kế tiếp và giữ lỗi,
không tự chạy lại nước có thể đã thực hiện một phần. Sau nước đi phải nhìn thấy
bàn cờ kết quả khớp rồi mới cập nhật trạng thái game.

Kiểm tra này không thay thế E-stop: lệnh SDK đang chạy không bị ngắt tức thì khi
bàn bị động vào. Khi lỗi trong một nước, cần kiểm tra tay/quân trên bàn trước
khi khởi động lại. QR bị tay che cũng làm hệ thống chờ/ngăn lệnh kế tiếp.

Model nhận diện trạng thái tại các giao điểm, không ước lượng tâm thực của quân
nếu quân đặt lệch khỏi giao điểm. Backend QR mới đã bổ sung visual correction:
sau khi model biết ô nguồn/ô quân bị ăn, ảnh bàn đã được QR warp phẳng được quét
vòng tròn trong vùng tối đa 0.34 ô. Robot gắp tại tâm đó, không gắp cố định ở
giao điểm. Sau khi đặt quân, nó lại tìm tâm thực tại ô đích trước khi đồng bộ
trạng thái game. Không tìm được tâm đủ tin cậy thì FR5 không bắt đầu nước đi;
nếu lỗi sau khi đặt, game bị khóa để người vận hành kiểm tra bàn thật.

Các tham số trong `config.py` có thể chỉnh sau khi xem camera thật:
`VISUAL_CORRECTION_MIN_RADIUS_CELLS`, `MAX_RADIUS_CELLS`, `MAX_OFFSET_CELLS`
`MIN_CONFIDENCE` và `HOUGH_PARAM2`. Không tăng `MAX_OFFSET_CELLS` quá 0.5: khi đó vùng tìm kiếm
có thể lẫn quân ở giao điểm kế bên. Hough-circle hiệu quả với quân tròn có viền
rõ; quân quá bóng, bị che, hoặc camera quá chéo sẽ bị từ chối thay vì tự đoán.
Camera càng gần vuông góc mặt bàn thì sai số parallax do độ dày quân càng nhỏ.

## Kiểm thử không phần cứng

```powershell
python -X utf8 -B -m unittest discover -s tests -p 'test_qr*.py' -v
```

Kiểm tra giải mã QR thật trên ảnh tổng hợp; bù lệch khác nhau ở bốn góc; xoay
0/15/90/180/270 độ; phối cảnh/dịch bàn; mất mã/quá hạn; nhãn tượng/ô chưa rõ;
nước đi/ăn quân; đổi tọa độ XY khi bàn dịch và từ chối di chuyển ngoài phạm vi.
Không chạy `unittest discover` không có filter: các test hardware cũ có thể gọi
robot thật.

Kết quả kiểm thử lúc tích hợp: 18 test QR/model, 5 test visual correction,
4 test visual-pick hiện có và 1 test đồng bộ game-state hiện có đều qua. Model nhận đúng 90/90 ô trên
`assets/demo001.png` của repo recognition với 4 góc chỉ định trong test; đây
không phải kết quả benchmark trên camera thật. Moonfish khởi động và trả một
nước đi hợp lệ. Chưa kết nối/chạy robot hoặc kiểm tra bàn cờ vật lý.
