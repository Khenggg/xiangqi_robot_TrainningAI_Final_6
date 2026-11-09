# [⬇ TẢI XIANGQI.ZIP — WINDOWS X64, ƯU TIÊN GPU](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-gpu-light-20261109/xiangqi.zip)

**Bản vá R1–R4 (09/11):** sau khi giải nén ZIP ở trên, tải [xiangqi-r1-r4-fix.zip](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-gpu-light-20261109/xiangqi-r1-r4-fix.zip), thoát ứng dụng rồi giải nén bản vá **vào đúng thư mục chứa `start.bat`**, cho phép ghi đè `app/` và `manifest.json`. Máy đã cài GPU chỉ cần mở lại `start.bat`, không cần cài lại GPU. Bản vá sửa việc Player vs Robot chưa truyền đường dẫn profile cố định, dẫn đến lỗi User/WObj 1/0. Push source không tự cập nhật ZIP đã tải.

Giải nén **toàn bộ ZIP** → lần đầu mở **INSTALL.bat** (cần Internet để cài thư viện GPU/CPU) → những lần sau mở **start.bat**. ZIP khoảng **274 MiB**; lúc cài cần thêm vài GB dung lượng.

Bản mới từ `fix/fix-capsule`: camera thử 0–2, tự enable khi kiểm tra đạt, Player vs Robot dùng logic `vsc-v3` riêng và giữ cấu hình phần cứng hiện tại; web 3D tiếp tục hiển thị. Đã kiểm tra YOLO và ONNX chạy CUDA trên GTX 1650. Xem [hướng dẫn capsule](docs/CAPSULE_OPERATOR.md), [luồng Player vs Robot](docs/HVR_VSC_V3.md) và [SHA256](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/download/xiangqi-gpu-light-20261109/xiangqi.zip.sha256).

# Xiangqi Robot — Sổ tay sử dụng

Hướng dẫn cho người chơi và người vận hành hệ thống cờ tướng có camera, AI Moonfish và cánh tay **FAIRINO FR3**. Các tên nút/phím bên dưới được đối chiếu với code nhánh `final` tại [`005f955`](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/tree/005f95539531c32601232cdeeec3cca4185f32d9), ngày **07/11/2026**. Phần tải/cài và cấu hình capsule được cập nhật **09/11/2026**; các mục điều khiển/recovery cũ bên dưới cần đọc cùng hướng dẫn luồng Player vs Robot mới ở trên.

**Phạm vi kiểm chứng:** tài liệu mô tả hành vi từ code và cấu hình; lần cập nhật sổ tay này chưa chạy thử camera, robot thật hay một ván hoàn chỉnh trên Windows. Các vấn đề phần cứng còn mở được nêu ở [Giới hạn hiện tại](#gioi-han).

[![Video demo Xiangqi Robot — bấm để xem trên YouTube](https://img.youtube.com/vi/PShKIGPRk10/hqdefault.jpg)](https://youtu.be/PShKIGPRk10)

## Tra cứu nhanh

- [1. Bắt đầu trong vài bước](#bat-dau)
- [2. Chọn môi trường và kiểu chơi](#chon-che-do)
- [3. Nhận biết cửa sổ, trạng thái và lượt](#giao-dien)
- [4. Chơi từng chế độ](#cach-choi)
- [5. Chuẩn bị và bật robot thật](#robot-that)
- [6. Cân chỉnh camera](#camera)
- [7. Tạm dừng, ván mới, đầu hàng và thoát](#quan-ly-van)
- [8. Chọn đúng cách phục hồi](#phuc-hoi)
- [9. Tra lỗi theo hiện tượng/thông báo](#xu-ly-loi)
- [10. Bảng nút và phím tắt](#phim-tat)
- [11. Cài đặt, dữ liệu và gửi thông tin lỗi](#du-lieu)
- [12. Giới hạn hiện tại](#gioi-han)
- [Phụ lục: chạy source và tài liệu kỹ thuật](#source)

<a id="bat-dau"></a>
## 1. Bắt đầu trong vài bước

### Máy đã có capsule

1. Tải bản **Capsule Windows x64** ở đầu trang. ZIP **Source code** của GitHub là mã nguồn, cần cài môi trường riêng.
2. Giải nén toàn bộ vào thư mục local có quyền ghi. Giữ nguyên `start.bat`, `INSTALL.bat`, `start.run`, `runtime.zip`, `app/` và `manifest.json`; không chạy trong ZIP hoặc chỉ copy riêng START.bat.
3. Lần đầu mở **INSTALL.bat**. Capsule dành cho **Windows 10/11 x64**: có Python nền, model, engine và tài nguyên 3D; bộ cài tải thư viện ML vào runtime riêng của ứng dụng. NVIDIA có driver phù hợp được ưu tiên CUDA; máy không có NVIDIA dùng CPU. Không cần Python/Git/Node riêng. Những lần sau mở **start.bat**.
4. Chọn **CHƠI TRÊN MÁY** để bắt đầu dễ nhất, hoặc **MÔ PHỎNG 3D** để xem robot ảo.
5. Bấm **VS ROBOT**, chọn độ khó, rồi bấm quân Đỏ và bấm ô đích. Đỏ đi trước. Chờ AI hoàn tất rồi đi tiếp.

Lần sau chỉ mở lại **START.bat**. Nếu muốn dùng robot thật, thực hiện [mục 5](#robot-that) trước. Trên máy dùng capsule, không chạy SETUP/pip/npm để sửa bộ đóng gói.

### Kiểm tra trước buổi sử dụng

| Mục đích | Việc cần làm |
|---|---|
| Chơi 2D | Mở được menu, chọn được độ khó, đi được nước bằng chuột |
| Xem mô phỏng | Viewer mở và nhận trạng thái từ backend; quan sát đúng nguồn VIRTUAL |
| Vận hành robot thật | Bộ thiết bị đã được hiệu chuẩn/commission; camera thấy đủ bàn, controller không lỗi, tay/kẹp đã được kiểm tra và có E-stop sẵn sàng |
| Kiểm tra bộ capsule | Trong PowerShell tại thư mục capsule, chạy `.\START.bat --check`; kết quả thành công là `CAPSULE CHECK PASSED` |

`--check` kiểm tra tính toàn vẹn file, import thư viện, nạp model, engine và PyBullet offline; **không mở camera/controller**. `.\START.bat --smoke` thêm kiểm tra giao diện không màn hình, tạo `state/ui-smoke.png`. Hai lệnh không chứng minh thiết bị thật hoặc cả ván chơi hoạt động đúng.

<a id="chon-che-do"></a>
## 2. Chọn môi trường và kiểu chơi

Màn hình đầu có **hai lựa chọn riêng**: nơi chạy và cách chơi.

### Môi trường

| Lựa chọn trên menu | Bạn sử dụng | Camera / robot thật |
|---|---|---|
| **CHƠI TRÊN MÁY** | Bàn 2D, nhập nước bằng chuột, không viewer 3D | Không sử dụng |
| **MÔ PHỎNG 3D** | Bàn 2D và robot FR3 ảo trên viewer | Không sử dụng |
| **ROBOT THẬT** | Bàn thật, camera, controller và viewer mirror khi khả dụng | Có; ban đầu chỉ đọc, phải kích hoạt riêng |

Mất kết nối robot trong phiên thật là sự cố cần xử lý. Phần mềm không biến phiên đó thành mô phỏng để tiếp tục chạy nước một cách mặc định.

### Kiểu chơi

| Nút | Ai chọn nước? | Robot làm gì? |
|---|---|---|
| **VS ROBOT** | Người Đỏ; AI Đen | Trong mô phỏng/physical, executor thực hiện nước AI; với physical, người tự đi quân Đỏ trên bàn thật |
| **HUMAN VS HUMAN** | Hai người lần lượt bấm chuột trên cùng bàn 2D | Không điều khiển robot thật, kể cả trước đó chọn môi trường ROBOT THẬT |
| **ROBOT VS ROBOT** | AI chọn nước cho cả Đỏ và Đen | Một executor/robot dùng chung thực hiện cả hai màu |
| **2 NGƯỜI + ROBOT** | Đỏ trên máy chủ, Đen trên cửa sổ riêng | Một executor/robot thực hiện nước cho cả hai; không AI |
| **VÀO PHÒNG / NGƯỜI ĐEN** | Mở client Đen của phòng đã có | Không tạo thêm chủ điều khiển robot |

**2 NGƯỜI + ROBOT** cần **MÔ PHỎNG 3D** hoặc **ROBOT THẬT**; menu từ chối nếu đang chọn CHƠI TRÊN MÁY. HUMAN VS HUMAN có thể vẫn mở mô phỏng/viewer theo môi trường đã chọn, nhưng không sở hữu robot thật.

### Độ khó AI

Sau VS ROBOT hoặc ROBOT VS ROBOT, chọn **Easy / Medium / Hard / Impossible** bằng chuột hoặc phím **1 / 2 / 3 / 4** tại màn hình chọn độ khó. Tất cả dùng **Moonfish local**; các mức đầu giới hạn tìm kiếm khác nhau. Impossible dùng cấu hình Moonfish gốc, tên mức này không có nghĩa AI bất bại. Tốc độ tính tùy máy và thế cờ.

Hai chế độ dành cho hai người không có bước chọn độ khó. **SETTINGS** hiện có công tắc debug dashboard; không phải màn hình cấu hình đầy đủ camera, IP và robot.

<a id="giao-dien"></a>
## 3. Nhận biết cửa sổ, trạng thái và lượt

| Cửa sổ/khu vực | Cách sử dụng |
|---|---|
| **Game 2D** | Chọn quân, bấm nút, đọc lượt và thông báo; bấm vào cửa sổ này trước khi dùng phím game |
| **Camera Monitor** | Xem ảnh và nhận diện trong phiên physical; ảnh có quân/box chưa đồng nghĩa toàn bộ FEN đã được xác nhận |
| **Viewer 3D trên trình duyệt** | Quan sát robot, bàn, quân và trạng thái live; robot thật dùng viewer như mirror |
| **Panel phục hồi** | Đọc “Cần làm”, “Lý do”, “Nước chờ”, “Thực thi”; lỗi dài xem tiếp trong log |
| **Terminal** | Giữ thông báo khởi tạo, đường dẫn viewer/log và lỗi chi tiết |

**F11** đổi toàn màn hình/cửa sổ; **Esc** thoát toàn màn hình. Có thể kéo cạnh cửa sổ game để đổi kích thước. Phím `S/R/Q` trong CALIBRATE phải nhập khi cửa sổ CALIBRATE đang được chọn, không phải game hoặc trình duyệt.

Một số từ sẽ gặp:

| Từ/trạng thái | Ý nghĩa thực tế |
|---|---|
| **FEN** | Cách phần mềm ghi thế cờ và lượt; không phải bằng chứng tay/kẹp đã dừng |
| **Baseline / T1** | Mốc ảnh/occupancy trước nước đi để so sánh với ảnh sau |
| **READ-ONLY** | Có thể đọc robot; game chưa được cấp quyền chuyển động |
| **AI is thinking** | AI đang tìm nước; chờ kết quả, không bấm liên tục |
| **Pending / nước chờ** | Có thao tác chưa được xác nhận hoàn tất; đọc tình trạng trước khi thử lại |
| **PICK_PAUSED / ĐO LẠI** | Đo tâm quân trước một bước gắp chưa đạt; có thể còn checkpoint của bước trước trong nước ăn |
| **RECOVERY_REQUIRED / Move stopped** | Cần đối soát hoặc xử lý thiết bị; không chỉ là tạm dừng hiển thị |

Một phiên mới bắt đầu ở **thế khai cuộc, Đỏ đi trước**. Hiện menu không có chức năng tiếp tục nguyên ván cũ sau khi mở lại ứng dụng. Dữ liệu phục hồi thao tác cũ vẫn có thể khóa phiên mới.

<a id="cach-choi"></a>
## 4. Chơi từng chế độ

### 4.1. Người đấu AI trên máy hoặc mô phỏng

1. Chọn **CHƠI TRÊN MÁY** hoặc **MÔ PHỎNG 3D** → **VS ROBOT** → độ khó.
2. Bấm quân Đỏ muốn đi, rồi bấm giao điểm đích. Đây là thao tác **bấm chọn rồi bấm đích**, không cần kéo thả.
3. Nước hợp lệ được xử lý; nước sai luật bị từ chối và có thể nháy ô đích.
4. Chờ AI và, nếu có, robot ảo thực hiện nước Đen. Chỉ đi tiếp khi game đã chuyển về lượt người và hết lỗi.

Không cần bàn thật, camera hoặc SPACE. Dòng “HvR ẢO / bộ nhập test” là nhãn của luồng nhập chuột hiện có, không phải yêu cầu lắp camera.

Nếu AI lỗi nhưng bàn chưa đổi và không có lỗi đồng bộ, kiểm tra engine rồi **F5** để yêu cầu tính lại. Nếu mô phỏng báo lỗi chuyển động/va chạm, dùng [quy trình lỗi mô phỏng](#loi-mo-phong).

### 4.2. Người đấu AI với bàn và robot thật

Sau khi hoàn thành [chuẩn bị robot thật](#robot-that):

1. Đúng lượt Đỏ, tự đi **một nước hợp lệ** trên bàn thật. Nếu ăn quân, lấy quân Đen bị ăn ra ngoài và đặt quân Đỏ vào đúng giao điểm đích.
2. Rút tay/vật che ra, giữ bàn ổn định. Luồng mặc định có tự xác nhận khi các quan sát ổn định cùng thể hiện một nước hợp lệ; nếu chưa xác nhận, dùng **SPACE / XÁC NHẬN NƯỚC ĐI**.
3. Quan sát bàn 2D đã nhận đúng nước, đúng lượt. Đừng đi thêm một nước trong lúc hệ thống đang xác nhận hoặc AI suy nghĩ.
4. AI chọn nước Đen. Robot kiểm tra bàn/điểm gắp, thực hiện và camera hậu kiểm trước khi ghi nhận hoàn tất.
5. Với nước ăn, robot lấy quân bị ăn ra trước rồi chuyển quân đi đến đích. Nếu dừng giữa hai bước, xử lý như nước dang dở; không tự chọn lại nước đó.
6. Chỉ đi tiếp khi bàn thật và game khớp, lượt đã về Đỏ và không còn thông báo phục hồi.

Tự xác nhận ổn định không phải hệ thống bảo vệ phát hiện mọi bàn tay/vật cản. Người vận hành phải giữ vùng chuyển động thông thoáng. Nếu SPACE báo không có nước mới, không đi thêm quân để “kích hoạt”; xem [lỗi camera/nước người](#loi-camera).

### 4.3. Hai người trên cùng bàn ảo

1. Chọn **HUMAN VS HUMAN**; CHƠI TRÊN MÁY là lựa chọn gọn nhất.
2. Đỏ bấm quân và đích; sau đó Đen thao tác trên cùng cửa sổ.
3. Đúng lượt mới đi được. Không cần phòng, camera, SPACE hoặc F9/F10.

Muốn robot gắp cho cả hai người, chọn **2 NGƯỜI + ROBOT** thay vì chế độ này.

### 4.4. Hai AI đấu nhau

1. Chọn môi trường → **ROBOT VS ROBOT** → độ khó chung cho hai AI.
2. Ở mô phỏng, khi executor sẵn sàng, chọn độ khó xong có thể bắt đầu chạy liên tục ngay. Chuẩn bị trước khi vào chế độ.
3. Ở physical, hoàn tất kiểm tra/bật quyền robot; **F6** bắt đầu self-play liên tục khi đủ điều kiện.
4. **F8** yêu cầu dừng. Chờ trạng thái dừng và đối soát nếu có nước đang dở. F8 không thay E-stop.
5. Sau khi phục hồi, chỉ khởi động lại bằng F6 khi không còn nước/checkpoint/test chưa giải quyết.

Nếu self-play đang **PICK_PAUSED**, dùng Y/V để đo lại hoặc F8 để dừng và xử lý pending. Nút đầu hàng không được nhận ở mọi trạng thái của self-play; nếu bấm chưa có tác dụng, đọc trạng thái thay vì bấm liên tục.

**F7 / NƯỚC TIẾP** yêu cầu một nước khi controller đang READY; hữu ích nếu phiên đã được cấu hình ở step mode. Menu hiện tại khởi chạy continuous; không có nút chọn step mode trên màn hình đầu, và F7 không tự chuyển continuous sang step.

### 4.5. Hai người chọn nước, một robot thực hiện

1. Chọn **MÔ PHỎNG 3D** hoặc **ROBOT THẬT** → **2 NGƯỜI + ROBOT**.
2. Máy chủ là **Đỏ**. Ghi mã phòng **6 ký tự** ở đầu bàn.
3. Trên máy chủ, bấm **O / MỞ NGƯỜI ĐEN**. Hoặc mở client từ **VÀO PHÒNG / NGƯỜI ĐEN**, nhập mã rồi Enter/kết nối.
4. Hai cửa sổ phải chạy **trên cùng PC**; phòng hiện chỉ dùng localhost, không có LAN/Internet.
5. Với physical, người vận hành thực hiện kiểm tra và F9 → F10 **trên máy chủ**. Chỉ mở một host sở hữu robot thật.
6. Đỏ bấm quân và đích trên máy chủ; Đen bấm trên cửa sổ riêng. Cửa sổ Đen xoay bàn 180° để nhìn thuận phía Đen.
7. Robot thực hiện cho cả hai màu; đợi máy chủ xác nhận và đổi lượt. Trong chế độ này, người chơi không tự dời quân bằng tay thay robot.

**Các tình huống trong phòng:**

| Tình huống | Cách xử lý |
|---|---|
| Đỏ cũng không đi được | Kiểm tra client Đen đã kết nối, đúng lượt, hết pending và robot đã sẵn sàng |
| Báo bàn đã thay đổi | Chờ trạng thái mới rồi chọn lại quân; không phát lại yêu cầu cũ |
| Client mất kết nối | Máy chủ khóa nước mới; nước đã bắt đầu vẫn do máy chủ xử lý. Kết nối lại cùng phòng và đọc trạng thái hiện tại |
| Đen đóng cửa sổ | Cửa sổ đóng trực tiếp; mở lại từ host bằng O khi cần |
| Máy chủ đang ĐO LẠI | Người vận hành dùng V/Y trên host cho đúng nước chờ, theo [mục 8](#phuc-hoi) |
| Muốn ván mới/đầu hàng | Điều khiển ở máy chủ; **SURRENDER trên host là Đỏ đầu hàng**, kể cả đang lượt Đen |

SPACE, M, Z, T/H không dùng để đi tay, rollback hoặc test trong chế độ này. Chi tiết: [Hai người + robot](docs/TWO_HUMAN_ROBOT_MODE.md).

### 4.6. Khi ván kết thúc

Game hiển thị bên thắng và không nhận thêm nước trong ván đã kết thúc. Muốn chơi lại, dùng **NEW GAME** và làm theo bước dừng/đối soát; với physical, người vận hành xếp lại quân thật. Nếu kết quả hoặc thế cuối không đúng, giữ log/journal và chụp bàn trước khi tạo ván mới để team kiểm tra.

<a id="robot-that"></a>
## 5. Chuẩn bị và bật robot thật

Phần này dành cho người vận hành **bộ FR3 đã được hiệu chuẩn**. Sao chép capsule sang một máy khác không làm hiệu chuẩn một robot/bàn/tool khác.

### Trước khi mở phiên

1. Kiểm tra đúng camera, controller và bộ bàn/quân của setup. Xếp đủ **32 quân đúng thế khai cuộc**.
2. Cố định camera/bàn; ảnh nhìn rõ bốn giao điểm góc và toàn lưới, ánh sáng đều, không chói hoặc bị che. Nếu dùng DroidCam, mở kết nối điện thoại/PC trước.
3. Kiểm tra Ethernet, IP/subnet và trạng thái controller. Camera có ảnh không chứng minh robot đã kết nối. Xem [Kết nối robot](ROBOT_CONNECTION.md).
4. Người phụ trách xác minh vị trí tay hiện tại, tool/TCP, robot-base/user frame, kẹp, vùng di chuyển, độ cao và đường đi; chuẩn bị E-stop. Sau mất điện, va chạm hoặc đổi setup, cần kiểm tra lại trước khi bật game.
5. Không mở hai host physical ở hai bản source/capsule cùng lúc.

### Mở và xác nhận

1. START.bat → **ROBOT THẬT** → kiểu chơi; chọn độ khó nếu có AI.
2. Nếu cần chấm lại góc, tick **Chấm lại 4 góc bàn từ camera** trước khi bấm kiểu chơi; làm [mục 6](#camera).
3. Đọc Camera Monitor và bàn 2D. Nếu báo bàn ban đầu chưa xác nhận, kiểm tra bố trí quân rồi **V** đối soát; xử lý mọi lỗi còn lại trước.
4. Khởi tạo chỉ đọc: chưa tự Enable/HOME. Chỉ sau kiểm tra thực tế, bấm **F9**, rồi **F10 trong 30 giây**. F9 lần nữa hủy yêu cầu; hết hạn thì bắt đầu lại từ F9.
5. Đợi thông báo đã bật quyền chuyển động. Việc bật có thể cấp quyền/cấp enable controller; sẵn sàng cho nước phát sinh khi đủ lượt.
6. VS ROBOT: người Đỏ đi theo mục 4.2. ROBOT VS ROBOT: F6. Hai người + robot: kết nối client rồi chọn nước.

F9/F10 có thể bị chặn bởi controller lỗi, telemetry cũ/chưa idle, calibration không hợp lệ, bàn chưa khớp hoặc giao dịch chưa giải quyết. **Không lặp F9/F10 để vượt lỗi**; sửa đúng nguyên nhân trong [mục 9](#xu-ly-loi).

Profile mặc định là [`calibration/physical_teaching_points_user0.json`](calibration/physical_teaching_points_user0.json), theo robot base/user 0. Luồng hiện tại dùng bộ teaching cố định, không tự đọc lại các teaching point vừa dạy trên controller. Chấm lại camera chỉ sửa ánh xạ ảnh, không cập nhật profile robot. Đổi robot/tool/bàn phải được người phụ trách kiểm chứng riêng.

<a id="camera"></a>
## 6. Cân chỉnh camera

### Khi nào cần chấm lại?

Khi camera hoặc bàn xê dịch, góc nhìn/độ phân giải/focus thay đổi, lưới lệch, hoặc phần mềm báo perspective không hợp lệ. Bình thường hệ thống dùng `perspective.npy` đã lưu; không nhất thiết mở CALIBRATE ở mọi lần chạy. Khi chưa có file, luồng khởi tạo sẽ yêu cầu hiệu chuẩn, có thể đi qua nhận diện góc tự động.

### Chấm thủ công bốn góc

1. Trở về menu sau khi phiên cũ đã dừng/đối soát → chọn ROBOT THẬT → tick **Chấm lại 4 góc bàn từ camera** → chọn kiểu chơi.
2. Đợi cửa sổ **CALIBRATE** và ảnh mới. Click **giao điểm lưới trên mặt bàn** theo thứ tự:

| Lần click | Giao điểm theo hướng hiển thị chuẩn của bàn | Tọa độ logic `(cột, hàng)` |
|---|---|---|
| 1 | Góc Xe Đen trái | `(0, 0)` |
| 2 | Góc Xe Đen phải | `(8, 0)` |
| 3 | Góc Xe Đỏ phải | `(8, 9)` |
| 4 | Góc Xe Đỏ trái | `(0, 9)` |

3. Kiểm tra lưới vàng khớp cả ngoài rìa, vùng trong và hai bờ sông. Không click mép trang trí, mép tấm bàn hoặc tâm mặt quân đang che giao điểm. Nếu hướng ảnh khác, xác định đúng phía Đen/Đỏ trước khi chọn.
4. **S** lưu, **R** xóa điểm và chấm lại, **Q/Esc** hoặc đóng CALIBRATE để hủy. Khi chủ động chấm lại mà hủy/lỗi, phiên có thể bị chặn; không coi calibration cũ là đã được xác minh lại.
5. Sau khi lưu, kiểm tra nhận diện và bàn khai cuộc; chỉ bật physical khi toàn bộ điều kiện ở mục 5 đạt.

`perspective.npy` nằm ở thư mục source hoặc `app/perspective.npy` trong capsule. Hiệu chuẩn intrinsics/độ cao/điểm gắp là công việc khác của team kỹ thuật; xem phụ lục. Sao lưu calibration trước khi thay đổi setup.

<a id="quan-ly-van"></a>
## 7. Tạm dừng, ván mới, đầu hàng và thoát

| Mục đích | Thao tác | Điều cần đợi/kiểm tra |
|---|---|---|
| Tạm dừng | **F8** | Có thể yêu cầu controlled stop; chờ worker và bằng chứng dừng. Không tự thả quân đang kẹp |
| Chơi ván mới | **NEW GAME** | Đợi dừng/đối soát giao dịch trước; physical cần tự xếp lại 32 quân, V xác nhận rồi kích hoạt riêng |
| Đổi môi trường/kiểu chơi | **F2 / CHỌN CHẾ ĐỘ** | Phiên cũ cần được đóng có kiểm soát; nếu bị giữ lại, xử lý panel phục hồi rồi thử F2 |
| Đầu hàng | **SURRENDER** | Khi đang chạy, yêu cầu được giữ để chờ xử lý nước hiện tại và dừng/đối soát; không nhất thiết kết thúc ngay |
| Thoát ứng dụng chính | Bấm X hoặc Ctrl+C trên terminal | Hộp **THOÁT / Ở LẠI**; Enter/Y xác nhận, Esc/N ở lại |

**NEW GAME không tự xếp lại quân thật.** Nếu còn nước đang dở, phần mềm có thể giữ yêu cầu New Game và yêu cầu V đối soát trước. Khi đã nhận yêu cầu đổi ván/đầu hàng, V/CONTINUE trong luồng đó chỉ phục vụ đối soát, không được coi là nút thử lại chuyển động.

**Xác nhận THOÁT đóng phần mềm ngay, không gửi lệnh dừng robot hoặc kẹp.** Đừng dùng đóng ứng dụng làm cách dừng thiết bị. Nếu đang có sự cố, xử lý thiết bị theo quy trình vận hành/E-stop thích hợp; giữ journal để xử lý kết quả chưa xác định. Bấm X cửa sổ client Đen đóng trực tiếp, khác cửa sổ chính.

<a id="phuc-hoi"></a>
## 8. Chọn đúng cách phục hồi

Trước hết đọc **nước chờ và trạng thái thực thi**. Cùng phím V nhưng hành vi tùy tình huống:

| Bạn đang ở tình huống nào? | Thao tác phù hợp | Kết quả cần quan sát |
|---|---|---|
| Chỉ mô phỏng/viewer lệch, không pending/lỗi | **V / ĐỒNG BỘ VIEWER** | Đồng bộ bàn game sang viewer; không dùng camera thật |
| Camera tạm dừng, không có chuyển động chưa rõ | Dọn vật che, kiểm tra bàn → **V / CONTINUE** theo UI | Xác minh bàn và lấy baseline mới; hết pause mới chơi |
| Đo tâm trước gắp chưa đạt, UI có **ĐO LẠI / THỬ NƯỚC CHỜ** | Kiểm tra quân mà log chỉ ra → **Y / V / ĐO LẠI** | Đo lại và có thể chạy tiếp **đúng nước/bước đang chờ**, khi đủ điều kiện |
| Robot đã chạy dở, timeout, mất phản hồi hoặc camera hậu kiểm không khớp | Xác nhận tay/kẹp đã dừng → **V** đối soát theo UI | Xác định bàn trước/sau, giải quyết pending; không gửi lại motion mù |
| Thế thật khác game, muốn nhận lại toàn bộ thế cờ | Sau khi thiết bị/giao dịch đủ điều kiện, **F4** | Hai lần quét nhận diện cùng thế; có thể thay thế cờ/lịch sử và cần xác nhận lượt |
| Báo chưa biết bên tới lượt sau quét | **1 = Đỏ / 2 = Đen** khi được hỏi | Đúng lượt rồi mới tiếp tục; lựa chọn Đen trong VS ROBOT có thể làm AI được lên lịch |
| Lỗi phiên còn giữ, đã xác minh bàn đúng FEN hiện tại | **F12 / XÓA PHIÊN LỖI** khi UI cho phép | Retire trạng thái lỗi của ứng dụng; không reset controller, không về Home |
| Controller/telemetry chưa xác nhận dừng | Kiểm tra WebApp/pendant; khi tay/kẹp đã dừng, **Ctrl+F8**, rồi **V** | Đủ bằng chứng dừng mới gỡ gate. Nếu vẫn lỗi controller thì tiếp tục bị chặn |

### 8.1. Chưa gắp được tâm quân

1. Xem log chỉ **quân di chuyển** hay **quân bị ăn cần lấy ra**, ô và lý do không đạt.
2. Rút tay/vật che; kiểm tra ánh sáng, vị trí quân trên giao điểm và lưới camera. Chỉ chỉnh bàn khi tay/kẹp đã dừng và người vận hành cho phép.
3. Khi UI đang ở pick retry, dùng **Y/V/ĐO LẠI**. Đây có thể dẫn tới robot chạy tiếp; đứng ngoài vùng chuyển động.
4. Nếu tiếp tục không đạt, giữ trạng thái và gửi log. Không tăng ngưỡng hoặc tắt xác minh để ép chạy.

Trong nước ăn, checkpoint có thể đã ghi nhận việc lấy quân bị ăn ra trước khi dừng ở lần đo tiếp theo. Không tự đặt lại quân đã ăn hoặc yêu cầu chạy lại toàn bộ nước mà chưa đối soát checkpoint.

### 8.2. Đã chạy nhưng kết quả chưa được xác nhận

1. Không đi nước mới, không bấm liên tục F5/F6/F9/F10 hoặc chọn lại cùng nước.
2. Xác minh trạng thái cơ khí/controller trước; giữ quân đang kẹp theo quy trình của team. Dùng luồng dừng và Ctrl+F8 khi UI yêu cầu và đã kiểm tra thực tế.
3. **V** đối chiếu toàn bàn với thế trước hoặc thế sau nước chờ. Nếu camera khớp nhưng robot còn lỗi, xử lý lỗi controller; FEN đúng chưa đủ.
4. Nếu thế sau được xác nhận, hệ thống có thể ghi nhận nước đã xong thay vì chạy lại. Nếu thế trước được xác nhận, việc thử tiếp vẫn phụ thuộc gate và thông báo hiện tại; không mặc định robot chắc chắn chưa chuyển động.
5. Nếu không khớp cả hai, nhờ người vận hành chỉnh bàn theo hướng dẫn cụ thể. F4 là lựa chọn quét nhận thế khác, có thể đổi lịch sử/lượt; không dùng tùy tiện thay V.

**Ctrl+F9** chỉ dùng khi UI báo kết quả disable controller chưa rõ và người vận hành **đã tắt controller trên pendant**. Phím này ghi nhận xác nhận đó; không phải nút tự tắt controller hay sửa mất mạng.

<a id="loi-mo-phong"></a>
### 8.3. Lỗi mô phỏng

F8 dừng → đọc lỗi backend/log → sửa nguyên nhân → **NEW GAME** khi worker đã kết thúc. Nếu chỉ lệch hiển thị và không còn giao dịch lỗi, thử V đồng bộ viewer. Không tắt collision guard hoặc thay camera thật vào quy trình mô phỏng để cho qua lỗi. Sau sửa code/tài nguyên cần khởi động lại ứng dụng và tải lại viewer.

### 8.4. Mất điện hoặc mở lại sau lỗi

Ứng dụng tạo bàn khai cuộc mới, nhưng giữ dấu vết giao dịch chưa giải quyết. Kiểm tra tay/kẹp, controller và đường đi thực tế trước; xử lý dừng theo UI → xếp lại bàn khai cuộc → V xác minh → chỉ F9/F10 khi đủ điều kiện. Mở lại phần mềm không tự phục hồi an toàn đường đi của tay robot. Không xóa dữ liệu phiên hoặc đổi thư mục chạy để tránh khóa phục hồi.

<a id="xu-ly-loi"></a>
## 9. Tra lỗi theo hiện tượng/thông báo

### 9.1. Không mở được chương trình hoặc viewer

| Hiện tượng/thông báo | Cách xử lý |
|---|---|
| START.bat không mở / thiếu file / `Capsule missing/damaged` | Kiểm tra đúng Windows x64 và giải nén toàn bộ; xem `state/launcher-error-*.log`. Giữ bản cũ cùng journal/calibration; giải nén bản sạch sang thư mục riêng để kiểm tra, không dùng bản mới điều khiển physical khi giao dịch cũ chưa giải quyết |
| `Capsule checksum mismatch` | Ghi lại đúng đường dẫn lỗi; team đối chiếu manifest/thay đổi. Không sửa manifest cho qua; bảo toàn dữ liệu trước khi thay bộ phát hành |
| `settings.json` lỗi | Sửa đúng JSON và đúng ba trường hợp lệ ở mục 11; camera index phải là số nguyên, IP phải là IPv4 hợp lệ |
| Source thiếu Python/dependency/Three.js | Chạy SETUP_WINDOWS.bat và kiểm tra thành công trước RUN; xem phụ lục. Không áp dụng cách này cho capsule |
| Viewer không tự mở | Xem URL `[VIEWER]` trên terminal, mở đúng URL đó trong trình duyệt. Không mở trực tiếp `index.html` bằng `file://` |
| Viewer trắng / model không tải | Capsule: kiểm tra bộ đầy đủ. Source: kiểm tra asset và chạy SETUP. Tải lại trang, xem `VIEWER_FAILED` trong log |
| `PORT_BUSY` / cổng đang dùng | Kiểm tra phiên cũ và đúng tiến trình sở hữu cổng. Source có `--viewer-port`/`--telemetry-port`; xem phụ lục. Không mở thêm host physical để né lỗi |
| Viewer đứng / không live / sai nguồn | Kiểm tra WebSocket, nguồn PHYSICAL/VIRTUAL và telemetry mới. Nếu nước đã commit, sửa kết nối/hiển thị, không chạy lại robot |
| Chỉ thấy cánh tay, bàn/quân lệch | Mirror bàn có thể thiếu calibration phù hợp; raw arm vẫn có thể hiện. Team kiểm tra profile bàn/Z; không căn chỉnh robot thật bằng cách kéo mô hình |

Trong phiên physical, viewer là mirror, không xác minh đường đi an toàn của robot thật. Các nút Home, kẹp, Reset Backend, Service trong viewer không phải quy trình phục hồi controller thật. Trong simulation chúng có thể là lệnh vận hành, bị giới hạn theo phiên/trạng thái; không bấm thử giữa ván để sửa FEN.

<a id="loi-camera"></a>
### 9.2. Camera hoặc nước người không được nhận

| Hiện tượng/thông báo | Cách xử lý |
|---|---|
| `Camera VIDEO_INDEX=... could not be opened` / không có ảnh BGR | Đóng ứng dụng khác dùng camera, kiểm tra quyền camera Windows, driver, USB/DroidCam và đúng index. Ứng dụng không tự đổi sang camera khác. Sửa cấu hình rồi mở lại phiên sau khi phiên cũ đã đóng |
| `Physical camera recognition unavailable` | Physical cần **cả YOLO best.pt và bộ ONNX pose/layout**, cùng CameraMonitor chạy. Capsule thiếu thì kiểm tra/khôi phục bộ; source cần đủ model và thư viện |
| `Saved perspective.npy cannot be used` | Mở lại luồng physical với checkbox chấm 4 góc; không xóa calibration mù hoặc coi ma trận cũ là đã xác minh |
| Bàn ban đầu chưa xác nhận | Xếp đúng 32 quân, bỏ vật che, kiểm tra góc ảnh → V. Nếu log chỉ controller lỗi, xử lý thiết bị trước |
| SPACE báo chưa có baseline | Giữ đúng thế cờ game đang hiển thị và tạo mốc theo thông báo. Lần bấm tạo baseline không có nghĩa đã xác nhận một nước |
| `No legal move could be identified` / không thấy nước mới | Xem có đúng lượt Đỏ và đã đi đúng một nước không; rút tay, kiểm tra nguồn/đích. Nếu pause hiện CONTINUE, dùng luồng đó để đối soát; không đi thêm quân |
| `Board changed, but one legal move could not be identified` | Bàn đã thay đổi nhưng không suy ra duy nhất một nước hợp lệ. Kiểm tra nước sai luật, nhiều quân đã dời hoặc nhận diện sai; đối soát theo UI, F4 khi cần nhận toàn thế |
| `CHECK` hoặc nước sai luật | Chọn nước hợp lệ, giải chiếu nếu cần; không dùng emergency để cho qua luật |
| YOLO báo 31 ô, ONNX xác nhận 32 quân | Hai phép đo khác nhau: occupancy YOLO và nhận dạng toàn bàn ONNX. Đọc ô/quân dự kiến chưa thấy trong log và kiểm tra ảnh; chưa đủ để kết luận thiếu quân thật hoặc tự sửa số lượng |
| Bấm phím không có tác dụng | Chọn đúng cửa sổ game; kiểm tra đang AI/worker bận, đúng mode và có pending không. Nhiều phím bị khóa theo trạng thái |

Khi đọc `CAMERA_VERIFY_FAILED`, xem tiếp mã lý do:

| Mã lý do | Ý nghĩa và bước tiếp theo |
|---|---|
| `NO_FRESH_OBSERVATION`, `FRAME_UNAVAILABLE`, `STALE_FRAME` | Chưa có ảnh/kết quả mới đủ dùng; kiểm tra camera/monitor, tải xử lý và chờ dữ liệu mới |
| `DUPLICATE_FRAME`, `OUT_OF_ORDER_FRAME`, `INVALID_TIMESTAMP`, `FUTURE_FRAME` | Ảnh/mã/thời gian không hợp lệ cho xác minh; không đếm ảnh cũ thành bằng chứng mới, gửi log nếu lặp lại |
| `CALIBRATION_UNAVAILABLE` | Chưa có calibration hợp lệ; chấm/xác minh lại góc camera |
| `RECOGNITION_FAILED`, `MALFORMED_BOARD`, `BOARD_SANITY_FAILED` | Model không nhận được một bàn hợp lệ; kiểm tra ảnh, hướng bàn, model và quân |
| `QUALITY_REJECTED`, `LOW_PIECE_CONFIDENCE`, `CONFIDENCE_INVALID` | Chất lượng/dữ liệu confidence chưa đạt; xử lý ảnh/ánh sáng/vật che, xem quân nào bị chỉ ra, không tự hạ ngưỡng |
| `BOARD_MISMATCH` | Nhận được thế khác FEN dự kiến; log có hàng/cột và quân dự kiến/quan sát để đối chiếu |
| `LAYOUT_UNSTABLE`, `INSUFFICIENT_STABLE_SAMPLES` | Chưa có đủ quan sát mới liên tiếp cùng hợp lệ; giữ bàn ổn định, bỏ vật che rồi đối soát lại |

Log đánh số **hàng 0–9, cột 0–8**. Ô `b9` nghĩa cột `b = 1`, hàng `9`, không phải hàng 9 cột 2 theo cách đếm từ 1. Khi có nhãn quân Đỏ/Đen trong log, dùng nhãn đó cùng ảnh; không đoán phía robot từ số hàng.

### 9.3. Robot, kẹp và dừng/đối soát

| Hiện tượng/thông báo | Cách xử lý |
|---|---|
| `READ-ONLY`, `ROBOT_NOT_READY` | Sau khi setup/bàn/controller đã được xác nhận, F9 → F10; nếu bật thất bại, đọc nguyên nhân tiếp theo |
| `PHYSICAL_ENABLE_FAILED`, `Fresh idle robot telemetry required` | Kiểm tra telemetry mới, idle/ready, controller, camera và mọi pending/recovery; không dùng F12 thay kiểm tra thiết bị |
| `Robot SDK not connected`, RPC timeout, `outcome unknown, do not resend` | Kiểm tra tay/kẹp trước; không gửi lại lệnh chưa rõ kết quả. Kiểm tra cáp/adapter/IP/subnet trên đúng đường Ethernet; xem ROBOT_CONNECTION.md |
| Camera đã xác nhận bàn nhưng “Robot đang lỗi” | Xử lý lỗi trên WebApp/pendant theo tài liệu controller; khi tay/kẹp đã dừng và hết lỗi, Ctrl+F8 rồi V theo UI. FEN/V/F12 không xóa lỗi controller |
| `No stable box centre`, pick retry, offset vượt giới hạn | Xem đúng quân/ô, độ lệch và jitter. Giới hạn mặc định hiện tại là **6 mm** trong config; kiểm tra quân/ảnh/calibration rồi dùng Y/V đúng trạng thái. Không tăng ngưỡng để ép gắp |
| `RECOVERY_REQUIRED`, `STOP_RECOVERY_REQUIRED` | Chưa có đủ bằng chứng dừng; xem worker, tay/kẹp và telemetry. Ctrl+F8 chỉ sau kiểm tra thực tế; nếu không đạt thì giữ khóa |
| `MoveCart`, IK, mã `14` hoặc `112` | Dừng và giữ log/trạng thái. Team kiểm tra pose hiện tại, tool/frame, mục tiêu và đường đi. Không coi lệnh lỗi là thành công; không tự gửi Home, kéo tay hoặc tắt/bật nguồn để thử lại theo sổ tay |
| Robot đã gắp/ăn nhưng chưa đặt đúng | Đây là thao tác có thể đã chạy một phần; theo mục 8.2. Không gọi lại cả nước và không thả kẹp mù |
| Kẹp không mở/đóng, không nhả quân | Dừng dùng physical, kiểm tra thực tế với team. Hình kẹp trên viewer không chứng minh độ mở/giữ quân thật; không tự đảo DO hoặc tăng xung trong phiên |
| `BOARD_SYNC_FAILED`, `PROJECTION_FAILED` sau commit | Bàn/nước đã lưu có thể đúng nhưng viewer/spectator cũ; kiểm tra log/kết nối. Không thực hiện lại nước để sửa hình ảnh |
| `SESSION_PERSISTENCE_FAILED` | Kiểm tra quyền ghi/dung lượng, giữ nguyên journal/bàn; không tiếp tục gửi motion khi chưa lưu được trạng thái |
| “Chưa đổi chế độ”, New Game/đầu hàng chờ mãi | Đọc lý do dừng và nước chờ. Nếu pending còn giữ, V đối soát sau xác nhận dừng. Ctrl+F9 chỉ khi đã thực sự disable trên pendant và UI yêu cầu |

### 9.4. AI không đi

Kiểm tra đang đúng lượt AI, đã chọn độ khó, không pause/recovery/test và physical đã được bật quyền. Với **ENGINE_FAILED / Engine failed; board unchanged**, kiểm tra engine Moonfish rồi **F5** khi không có lỗi đồng bộ. F5 không sửa lỗi robot/camera. Với ROBOT VS ROBOT, kiểm tra F8 đã dừng trước đó hay chưa và dùng F6 khi đủ điều kiện. Với 2 NGƯỜI + ROBOT/HUMAN VS HUMAN không có AI tự đi.

<a id="phim-tat"></a>
## 10. Bảng nút và phím tắt

Phím game áp dụng khi **cửa sổ game chính** được chọn; các thao tác thường bị chặn lúc worker bận. Luôn ưu tiên trạng thái/nút đang hiển thị.

| Phím/nút | Khi nào dùng | Tác dụng |
|---|---|---|
| Chuột trái | Mode cho nhập chuột | Bấm quân rồi bấm đích; trong 2 người + robot là yêu cầu robot thực hiện |
| SPACE / XÁC NHẬN NƯỚC ĐI | Nước người bằng camera trong VS ROBOT physical | Thử nhận/xác nhận nước Đỏ; có thể chỉ tạo baseline nếu chưa có. Mô phỏng đi chuột không cần SPACE |
| V / QUÉT–ĐỐI SOÁT / CONTINUE | Theo trạng thái | Đối soát camera, lấy baseline, đồng bộ viewer hoặc retry nước đang chờ; xem mục 8 |
| Y / ĐO LẠI | Khi có pick retry | Đo lại rồi có thể chạy tiếp đúng nước/bước chờ |
| F4 | Phiên có camera, đủ điều kiện phục hồi | Quét nhận toàn bàn, có thể đổi thế/lịch sử; khác nút QUÉT/ĐỐI SOÁT đang gán V |
| 1 / 2 | Chỉ khi được hỏi lượt sau quét | Đỏ / Đen. Tại menu độ khó, 1–4 có nghĩa chọn độ khó |
| O / MỞ NGƯỜI ĐEN | Host 2 người + robot | Mở client Đen cùng PC |
| F5 | Lỗi AI, không lỗi đồng bộ | Yêu cầu AI tính lại |
| F6 | ROBOT VS ROBOT | Bắt đầu self-play continuous khi đủ điều kiện |
| F7 / NƯỚC TIẾP | Self-play READY | Yêu cầu nước tiếp; không phải nút chọn step mode |
| F8 | Phiên đang mở | Dừng self-play hoặc yêu cầu pause/controlled stop; không phải E-stop |
| F9 → F10 | Physical sau kiểm tra | Bắt đầu/xác nhận quyền chuyển động trong 30 giây |
| Ctrl+F8 | Phục hồi stop khi được yêu cầu | Xác nhận đã kiểm tra tay/kẹp dừng; đọc lại bằng chứng dừng |
| Ctrl+F9 | Chỉ khi UI yêu cầu sau disable chưa rõ | Xác nhận controller đã được disable trên pendant |
| F12 / XÓA PHIÊN LỖI | Có lỗi phiên, thỏa đối soát/dừng | Xóa trạng thái lỗi ứng dụng; không reset thiết bị |
| F2 / CHỌN CHẾ ĐỘ | Trong phiên | Yêu cầu dừng/đóng phiên rồi về menu |
| NEW GAME | Muốn ván khai cuộc mới | Chờ kết thúc/đối soát thao tác cũ; không xếp quân thật |
| SURRENDER | Trong ván | Yêu cầu đầu hàng, chờ thao tác hiện tại và phục hồi nếu cần |
| F11 / Esc | Game chính | Đổi toàn màn hình / thoát toàn màn hình |
| X / Ctrl+C | Ứng dụng chính | Hỏi Thoát/Ở lại; xác nhận đóng phần mềm ngay |
| S / R / Q hoặc Esc | Chỉ CALIBRATE | Lưu / chấm lại / hủy hiệu chuẩn camera |

### Các chức năng chỉ dành cho vận hành/thử nghiệm

| Chức năng | Cách dùng và giới hạn |
|---|---|
| **M / EMERGENCY MODE** | Phiên có camera, không phải 2 người + robot. Tạm dừng tự xác nhận camera để nhập chuột có giám sát. Không tự dời quân thật hay bỏ luật/gate controller; muốn trở lại phải đối soát khi cần. Đây **không phải nút dừng khẩn cấp** |
| **Z / ROLLBACK** | Chỉ khi có snapshot phù hợp và trạng thái cho phép. Khôi phục lịch sử phần mềm trước SPACE, không tự trả quân thật. Physical cần khôi phục bàn và xác minh lại; không có undo vô hạn |
| **T / GẮP–THẢ** | Khi mode có executor/mô phỏng và cho phép test, không phải 2 người + robot. T bật test → chọn quân Đỏ/Đen → chọn ô trống; có thể chạy robot thật nếu đã kích hoạt |
| **H / HOVER** | Trong test T đã chọn quân: tiếp cận/hover, không gắp; vẫn là chuyển động nếu physical |
| **Sau test** | T thoát test không tự khôi phục ván. Xác nhận dừng, đối soát test nếu dở, trả bàn về khai cuộc rồi NEW GAME. Không dùng test để tiếp tục một ván đang lỗi |

<a id="du-lieu"></a>
## 11. Cài đặt, dữ liệu và gửi thông tin lỗi

### Capsule mới: cấu hình source

Bản mới không dùng `settings.json` để ghi đè cấu hình. Chỉnh camera/IP tại `app/config.py` giống chạy source; biến môi trường vẫn có tác dụng. Camera ưu tiên `VIDEO_INDEX` nếu có, nếu không dùng `VIDEO_SOURCE`, rồi thử các index còn lại trong 0–2.

GPU được ưu tiên khi runtime CUDA và driver phù hợp; `VISION_DEVICE=cpu` cho phép chọn CPU theo cấu hình project. Lần đầu cần Internet để cài ML; những lần sau dùng runtime đã cài. Không ép engine/chế độ/token về cấu hình capsule cũ. Xem [hướng dẫn bộ cài](docs/CAPSULE_OPERATOR.md).

### Dữ liệu ở đâu?

| Dữ liệu | Capsule | Chạy source |
|---|---|---|
| Nhật ký game | `app/logs/<id-phien>/` | `logs/<id-phien>/` mặc định |
| Lỗi launcher | `state/launcher-error-*.log` | Xem terminal/log game |
| Journal/giao dịch | `app/data/runtime/` | `data/runtime/` |
| Góc camera | `app/perspective.npy` | `perspective.npy` |
| Calibration robot | `app/calibration/` | `calibration/` |

**Giữ nguyên journal khi có giao dịch chưa giải quyết.** Không xóa SQLite/lock hoặc chép đè thư mục dữ liệu để bỏ recovery. Khi cần sửa/thay bộ phần mềm, nhờ team giữ bản cũ và di trú dữ liệu sau khi phiên đóng; không chỉ copy riêng một file SQLite đang mở.

### Gửi lỗi để team kiểm tra

1. Chụp **cửa sổ game/panel phục hồi**, Camera Monitor và cảnh bàn thật nếu liên quan; ghi đúng giờ xảy ra.
2. Ghi môi trường, kiểu chơi, lượt, quân/ô nguồn–đích, nút cuối vừa bấm và robot đã chạy đến đâu. Nêu đang giữ quân hay đã thả nếu quan sát được.
3. Gửi thư mục log đúng phiên: đọc **`errors.log`** trước (có cả WARNING), rồi **`run.log`**; **`events.jsonl`** có dữ liệu chi tiết, **`session.json`** có thông tin phiên.
4. Nếu chưa vào game được, gửi thêm `state/launcher-error-*.log` và kết quả `START.bat --check` nếu đã chạy.
5. Giữ journal/calibration tại máy để team đối soát. Nếu lỗi xuất hiện ngay sau cập nhật, nêu đang dùng release ZIP nào hay commit source nào.

<a id="gioi-han"></a>
## 12. Giới hạn hiện tại

- **Nhánh source và ZIP là hai bản phát hành khác nhau.** ZIP ở đầu trang là bản `xiangqi-gpu-light-20261109` từ nhánh `fix/fix-capsule`. Sửa README/source trên GitHub không tự thay file trong ZIP; cần build/nghiệm thu capsule mới để cập nhật bộ đóng gói.
- Lần cập nhật hướng dẫn này dựa trên đọc code, **chưa nghiệm thu camera/controller/robot thật, Windows sạch thứ hai hoặc cả ván UI/browser**. Kết quả test cũ trong báo cáo chỉ có giá trị trong phạm vi/ngày được ghi; không có tuyên bố toàn bộ bộ test hiện tại xanh.
- Dự án còn ghi nhận vấn đề physical sau gián đoạn nguồn/đường tiếp cận, lỗi controller/tool context và kiểm chứng nhả kẹp có tải. **V/F12/F9/F10 không chứng minh đường đi sau sự cố đã an toàn**. Khi gặp các tình huống đó, dừng vận hành physical và để team kiểm tra trước khi chạy tiếp.
- Kẹp dùng điều khiển theo xung, không có cảm biến vị trí ngàm; hình kẹp trên viewer không chứng minh đã gắp/nhả đúng ngoài đời.
- Digital twin physical có thể hiển thị tay khi mirror bàn chưa được hiệu chuẩn đầy đủ. Mô phỏng không thay nghiệm thu hình học/va chạm thực tế.
- Phòng Đỏ–Đen chỉ localhost cùng PC. Menu chưa có tiếp tục nguyên ván cũ hoặc lựa chọn step mode cho self-play.

Chi tiết trạng thái: [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Cẩm nang cũ tại `docs/USER_MANUAL_QUICKSTART.md` đã được chuyển hướng về README này; các tài liệu kỹ thuật có ngày cũ cần đối chiếu code/config hiện tại khi vận hành.

<a id="source"></a>
## Phụ lục — Chạy source và tra cứu kỹ thuật

### A. Cài và chạy source trên Windows

Dành cho người phát triển: cần **Git, Python 3.12 x64 có Launcher `py`, Node.js/npm**, Internet cho cài dependency.

```powershell
git clone --branch final https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6.git
cd xiangqi_robot_TrainningAI_Final_6
.\SETUP_WINDOWS.bat
if ($LASTEXITCODE -ne 0) { throw 'SETUP thất bại. Xử lý lỗi trước khi chạy game.' }
.\RUN.bat
```

SETUP tạo `.venv312`, cài thư viện và tài nguyên Three.js; không tải trọng số nhận diện/calibration. Physical cần đủ `models/best.pt`, `models/cchess/pose_4_v6.onnx`, `models/cchess/layout_nano_v3.onnx`, do team cung cấp riêng. Moonfish source đã có trong repo. Những lần sau dùng RUN; chỉ chạy lại SETUP khi cần sửa/cập nhật môi trường.

| Lệnh source | Tác dụng |
|---|---|
| `.\RUN.bat --board-only` | Chọn sẵn bàn 2D; alias `--virtual` cũng nghĩa bàn 2D, không phải simulation 3D |
| `.\RUN.bat --sim` | Chọn sẵn simulation 3D; cũng là mặc định |
| `.\RUN.bat --robot` | Chọn sẵn physical, ban đầu chỉ đọc; alias `--physical` |
| `.\RUN.bat --physical --recalibrate-camera` | Yêu cầu luồng calibration camera tương tác; checkbox trên menu mở chấm tay bốn góc |
| `.\RUN.bat --no-3d` | Không mở viewer, giữ backend; alias `--no-viewer` |
| `.\RUN.bat --simulation-profile fast` | Playback mô phỏng nhanh hơn; vẫn kiểm tra physics, không đổi tốc độ robot thật |
| `.\RUN.bat --viewer-port 8098 --telemetry-port 8898` | Cổng viewer/WebSocket khác nhau khi cổng mặc định 8088/8765 bị chiếm; không cho phép chạy thêm chủ robot thật |
| `.\RUN.bat --help` | Xem tùy chọn CLI, không mở thiết bị |

Chọn một môi trường; không ghép `--sim` với `--robot`/`--board-only`. `--recalibrate-camera` cần `--physical`; playback profile chỉ cho simulation. Các cờ CLI ở bảng này dành cho **RUN.bat từ source**; START.bat capsule chỉ nhận `--check` và `--smoke`, môi trường chọn qua settings/menu.

Camera source lấy `VIDEO_INDEX` nếu có, nếu không lấy `config.VIDEO_SOURCE`. Chỉnh index đúng thiết bị trước khi mở phiên; đừng sửa tọa độ hoặc xung kẹp để giải quyết lỗi chọn camera.

### B. Build bản bàn giao mới

Trên máy phát triển đã chuẩn bị đủ model:

```powershell
.\BUILD_CAPSULE.bat --models "D:\path\to\models"
```

Kết quả portable/ZIP/checksum tại `dist/`. Build và kiểm chứng bộ mới trước khi phát hành; giữ dữ liệu phiên/calibration của máy vận hành khi nâng cấp. Xem [WINDOWS_CAPSULE_BUILD.md](docs/WINDOWS_CAPSULE_BUILD.md).

### C. Tài liệu và điểm đối chiếu code

| Chủ đề | Hướng dẫn / nguồn thực thi |
|---|---|
| Launcher capsule, check/smoke/settings | [CAPSULE_OPERATOR.md](docs/CAPSULE_OPERATOR.md), [launcher.py](tools/capsule/launcher.py) |
| Menu, độ khó, enable, dừng/thoát | [main.py](main.py), [board_renderer.py](src/ui/board_renderer.py), [exit_confirmation.py](src/ui/exit_confirmation.py) |
| Capability từng mode, CLI | [session_profile.py](src/core/session_profile.py), [launch_options.py](src/core/launch_options.py), [START_PROJECT.md](docs/START_PROJECT.md) |
| V/Y/F4/F12, emergency, rollback, test | [input_handler.py](src/ui/input_handler.py), [game_state.py](src/core/game_state.py), [recovery_status.py](src/ui/recovery_status.py) |
| Dừng, đổi phiên, New Game, đầu hàng | [session_control.py](src/core/session_control.py), [controlled_stop.py](src/hardware/controlled_stop.py) |
| Hai người + robot và client Đen | [TWO_HUMAN_ROBOT_MODE.md](docs/TWO_HUMAN_ROBOT_MODE.md), [robot_pvp.py](src/core/robot_pvp.py), [pvp_client.py](src/ui/pvp_client.py) |
| Self-play | [self_play_controller.py](src/core/self_play_controller.py) |
| Kiểm tra bàn/điểm gắp, bật physical | [hardware_manager.py](src/hardware/hardware_manager.py), [board_diagnostics.py](src/vision/board_diagnostics.py) |
| Chấm góc camera | [calibrate_camera.py](src/vision/calibrate_camera.py), [camera_startup.py](src/vision/camera_startup.py) |
| Ethernet và frame robot | [ROBOT_CONNECTION.md](ROBOT_CONNECTION.md), [ROBOT_FRAME_BASE_ONLY.md](docs/ROBOT_FRAME_BASE_ONLY.md), [BRD_XY_CALIBRATION.md](docs/BRD_XY_CALIBRATION.md) |
| Calibration intrinsics/geometry — kỹ thuật viên | [camera_offset_notes.md](docs/camera_offset_notes.md), [geometry-measurement.md](docs/geometry-measurement.md), [teaching_points_guide.md](docs/teaching_points_guide.md) |
| Log/journal và khởi tạo phiên | [LOGGING.md](docs/LOGGING.md), [project_logging.py](src/core/project_logging.py), [game_persistence.py](src/core/game_persistence.py), [session_startup.py](src/core/session_startup.py) |
| Cấu hình đang thực thi | [config.py](config.py) |

Sổ tay dành cho người dùng; không thay tài liệu commissioning hoặc hướng dẫn bảo trì của controller/robot.
