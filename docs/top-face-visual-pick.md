# Gắp theo mặt trên quân cao 10 mm

Vùng giao điểm: **250 × 281,25 mm** (8 × 9 khoảng, mỗi khoảng 31,25 mm,
đã tính sông; không tính rìa giấy). **10 mm là mặt bàn → mặt trên quân**, không
phải camera → bàn. Không cộng 10 mm vào `PICK_Z`.

## Luồng mới

`best.pt` vẫn chỉ nhận dạng vùng có quân, không nhận dạng loại quân. Mỗi snapshot
mới gồm ảnh BGR và box float đúng trên ảnh đó. Trong ROI, tìm contour vành; khử
méo các điểm vành, chiếu tia tới mặt phẳng trên quân bằng K/distortion/pose mới,
fit đường tròn trong tọa độ mm rồi lấy tâm. Không lấy tâm ellipse ảnh rồi chiếu;
không lấy tâm box, điểm 85%, trung điểm với tâm ô, hay cộng offset hướng rìa.

Với quân trắng có vòng viền in đồng tâm như ảnh đã cung cấp, code yêu cầu **vành
in bên trong mặt trên**, có vùng trắng ở cả hai phía và được đường bao quân lớn
hơn bao quanh. Chỉ đường bao thân/mặt ngoài, hoặc hai mép Canny của cùng một
đường bao, không đủ bằng chứng. Không thấy vành in đủ rõ: từ chối. Nếu vòng in
không đồng tâm với quân, thuật toán này không thể bảo đảm tâm vật lý — cần kiểm
tra quân thật hoặc dùng model segmentation/keypoint mặt trên được huấn luyện riêng.

Tâm mm → grid float → phép nội suy XY robot hiện có. T và game dùng cùng resolver;
quân bị ăn phải có target trước gắp; source chụp lại sau khi loại quân bị ăn.
Thiếu profile, sai camera/kích thước/góc bàn, vành không đủ, hai tâm khả dĩ, hoặc
chưa có nhóm samples đồng thuận đáng tin: **chưa phát lệnh gắp bị ảnh hưởng**, không fallback.
Nhánh raw mới đưa NumPy BGR trực tiếp vào best.pt theo
[quy ước Ultralytics](https://docs.ultralytics.com/modes/predict/#inference-sources),
không đổi BGR→RGB hai lần.
Nếu source thất bại sau khi đã loại quân bị ăn, bàn đang dở nước: giữ nguyên FEN
và checkpoint; chỉ thử lại phần quân nguồn khi đã xác nhận bước bỏ quân bị ăn
hoàn tất và ô đích trống. Không chạy lại bước ăn quân, không tự commit FEN.

## Chọn tâm từ nhóm đo và Thử lại

Không yêu cầu mọi frame cùng một tâm. Lấy ít nhất 3 snapshot mới; nếu chưa đủ
bằng chứng thì lấy thêm, tối đa 6 lần với ngân sách đo mềm 3 giây cho **mỗi lượt
đo tâm**. Đủ đồng thuận thì trả kết quả ngay, không sleep cho đủ 3 giây. Khi ăn
quân có lượt đo quân bị ăn và lượt đo mới cho quân nguồn sau khi bỏ quân bị ăn;
kiểm tra occupancy và thời gian arm di chuyển là các phần riêng.

Tâm được tính theo mm trên mặt quân 10 mm như trên. Xét các nhóm samples có mọi
thành viên cách trung vị XY của nhóm không quá **3,75 mm**. Chọn nhóm lớn nhất
duy nhất, ít nhất 2 thành viên và **hơn một nửa số samples hợp lệ**. Samples None
không tham gia mẫu số, nhưng **lần đo mới nhất phải có tâm và thuộc nhóm được
chọn**. Hai nhóm bằng số thành viên, ảnh cuối mất quân/thiếu vành, hoặc ảnh cuối
lệch khỏi nhóm lớn nhất: đo thêm hoặc chờ xử lý, không chọn nhóm nhỏ hơn để lờ lỗi.
Không lấy trung bình với tâm ô, không dùng confidence box làm trọng số tâm.

**3,75 mm là bán kính phân tán tới trung vị, không phải đường kính nhóm hay
độ chính xác gắp cam kết.** Hai mẫu có thể cách nhau tới 7,5 mm; ngưỡng khởi đầu
giữ tương đương jitter 0,12 ô trước đây và phải đánh giá với ngàm thật. Đồng
thuận thời gian không loại được sai lệch hệ thống của camera/teaching/TCP.

Các setting chỉ dành cho top-face trong `config.py`:

- `VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES = 3`
- `VISUAL_PICK_CONSENSUS_MAX_SAMPLES = 6`
- `VISUAL_PICK_CONSENSUS_TIMEOUT_SEC = 3.0`
- `VISUAL_PICK_CONSENSUS_RADIUS_MM = 3.75`
- `VISUAL_PICK_MIN_STABLE_SAMPLES = 2`

Đọc frame/inference lỗi tạm thời được ghi thành một lần đo thiếu, không xem ô là
trống. Mất camera/model, sai profile/frame/geometry/config hoặc lỗi không xác
định: từ chối ngay, không chuyển về nhánh tâm box/foot/logical. Kiểm tra hạn sau
inference, xử lý ROI và chọn nhóm; kết quả về muộn không được dùng. Ngân sách
**mềm** không ngắt được OpenCV/YOLO đang blocking, nên hàm có thể trả muộn hơn
3 giây nhưng vẫn loại kết quả. Không tạo worker timeout chạy ngầm rồi dùng kết
quả cũ.

Khi hết samples/ngân sách, UI thay vị trí CONTINUE bằng **R: THỬ LẠI / X: HỦY**
(bấm nút hoặc bàn phím). UI sampling hiện tại chạy đồng bộ; các nút có tác dụng
sau khi lượt đo trả về, không phải nút dừng arm đang chạy.

- Trước gắp: R đo mới hoàn toàn cho **cùng nước đã chọn**, không gọi AI chọn nước
  khác; T cũng giữ cùng quân/ô đích. X không chạy arm, không cập nhật FEN.
- Sau bỏ quân bị ăn: chỉ có checkpoint sau khi bỏ quân thành công và đã xác
  nhận ô trống. R kiểm tra ô trống lại, đo quân nguồn mới, chạy gắp/thả nguồn
  bằng flow không ăn quân. Metadata quân bị ăn giữ nguyên để commit đúng một lần.
- Lỗi motion, ô đích không xác nhận trống, hoặc không xác nhận vị trí sau thả:
  **không** tự thử lại. Kiểm tra/chỉnh tay rồi V đối soát. X ở game giữ FEN và
  trạng thái chờ phục hồi, không tự chuyển lượt.
- Retry gắn với epoch game/AI, nước đi, trạng thái bàn và metadata pending.
  Reset/rollback/đổi trạng thái làm yêu cầu cũ hết hiệu lực. Không chọn quân khác
  hay chạy AI mới trong khi đang chờ R/X.

Log `[TOP PICK]` ghi attempt, nhóm `support` (index từ 0), số samples hợp lệ,
grid tâm trung vị được chọn và `sampling=...s`. Đây là thời gian riêng lượt đo,
không bao gồm Moonfish, occupancy, di chuyển arm hay baseline sau nước đi.

## Hiệu chuẩn MỚI (không dùng folder đo cũ)

1. Đóng RUN. In [mẫu riêng](../assets/calibration/checkerboard-20mm.svg) ở 100% /
   Actual size. Đây là **tờ hiệu chuẩn ống kính tạm thời**, không thay bàn cờ tướng.
   Đo cạnh một ô thật sau in; không tin riêng con số 20 mm ghi trên file.
2. Chạy `CALIBRATE_PICK_GEOMETRY.bat`. Nhập cạnh ô đo được và tolerance XY chấp nhận
   (mm, tối đa 5). Tolerance là tiêu chí commissioning do người vận hành chọn,
   không phải độ chính xác được phần mềm cam kết.
3. Bước 1: giữ camera/focus/zoom/resolution cố định. Đưa tờ mẫu qua giữa, trái/phải,
   trên/dưới và nghiêng nhiều hướng. `S` lưu view; ít nhất 12 view khác nhau.
   `C` fit. Tool từ chối view trùng, thiếu vùng ảnh/độ nghiêng hoặc RMS > 1 px.
4. Bước 2: bỏ mẫu và quân; bàn ở đúng vị trí chơi. `F` freeze ảnh. Click lần lượt
   `(0,0),(4,0),(8,0),(0,4),(4,4),(8,4),(0,9),(4,9),(8,9)`.
   `(0,0)` là vị trí Xe Đen trái theo hướng ma trận project, **không phải góc giấy**.
   `U` undo, `R` chụp lại, Enter chấp nhận. Pose sai số > 2 px bị từ chối.
5. Bước 3: một quân cao 10 mm **đánh dấu tâm chính xác trên mặt trên**. Căn tâm đáy
   ở giao điểm yêu cầu: bốn góc và `(4,4)`. Tại mỗi ô: `F`, click dấu tâm, Enter.
   Không đo tâm bằng tâm box/ước lượng giữa ellipse. Tool so XY với giao điểm thật;
   các điểm này **không tham gia fit pose**. Một ô vượt tolerance: không lưu.
6. Bước 4: `S` phê duyệt lưu `calibration/pick_geometry.json`; profile cũ được backup.
   ESC/Q ở bất kỳ bước nào hủy, không thay profile cũ. Tool **không mở robot/gripper**.
7. Mở RUN lại, giữ nguyên setup. Auto/manual board calibration vẫn chạy, nhưng góc
   mới phải khớp pose profile trong tolerance pixel; không so hash `perspective.npy`.
   Thông báo `[TOP PICK] BLOCKED` yêu cầu sửa calibration, không tăng tolerance để lờ lỗi.

Không cần làm lại intrinsics khi lens/setup thực sự không đổi, nhưng bản wizard này
chủ động thu mới toàn bộ để tránh dùng profile sai. Đổi camera, lens, focus, zoom,
độ phân giải, hoặc vị trí bàn/camera: chạy commissioning lại. Camera index không
phải serial thiết bị: thay thiết bị cùng index cũng phải chạy lại.

## Thông số và quan sát

Trong `config.py`: `VISUAL_TOP_FACE_ENABLED`, `VISUAL_PICK_GEOMETRY_PATH`,
`VISUAL_BOARD_WIDTH_MM/HEIGHT_MM`, `VISUAL_PIECE_HEIGHT_MM`; các quality gate
`VISUAL_TOP_*` kiểm soát residual/coverage/radius/ambiguity. Radius 5–15 mm là
**khoảng lọc khởi đầu**, cần kiểm tra kích thước quân thật. Không có offset empiric.
`VISUAL_PICK_MAX_OFFSET_CELLS` vẫn là giới hạn lệch khỏi ô được chọn.
Các gate enclosing-area và white-annulus là bằng chứng mặt trên cho bộ quân trắng
có vòng in, không áp dụng mặc định cho mọi màu/vật liệu. Mơ hồ giữa các vành được
xử lý **trước** giới hạn sai lệch với ô, tránh bỏ vành đúng ngoài giới hạn rồi gắp
theo đường bao thân sai bên trong giới hạn.

Camera Monitor hiển thị **LAST PICK SNAPSHOT** trong 8 giây kể từ lúc UI vẽ được
(thời gian arm làm việc không làm ảnh hết hạn trước khi nhìn thấy): box xanh là ROI, vành
cyan là contour dùng fit, dấu vàng là tâm metric chiếu lại vào ảnh. Log ghi grid,
radius/residual, profile ID hoặc lý do từ chối. Đây là ảnh đo cũ được gắn nhãn,
không phải overlay giả trên frame live mới. Sau đó trở lại live.

Occupancy dùng box độc lập, không coi thất bại tìm mặt trên là ô trống. Inference
lỗi cũng không coi là ô trống. `VISUAL_TOP_FACE_ENABLED=False` chọn nhánh legacy
có fallback cũ; `VISUAL_PICK_ENABLED=False` giữ hành vi logical của game. T luôn
cần target. Không tắt các cờ này chỉ để vượt lỗi commissioning.

## Giới hạn cần thử thật

Contour có thể bị lẫn thân/bóng/chữ hoặc bị đứt; trường hợp không phân biệt được
thì ưu tiên từ chối. Kiểm thử synthetic/unit không chứng minh đã nhận dạng tốt ảnh
cam thực hay gắp thành công. Sau commissioning, thử có giám sát ở giữa và bốn góc.
Nếu XY đúng nhưng ngàm vẫn lệch, kiểm tra riêng TCP, R1–R4, offset và cơ khí.
Các thông số `CELL_SIZE_*`, `RIVER_GAP_Y`, offsets, Z, rotation và gripper cũ không
được sửa trong feature này; kích thước camera không tự thay robot teaching.
