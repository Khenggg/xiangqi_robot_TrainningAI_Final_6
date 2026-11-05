# Khởi động dự án

Game robot thật hiện lấy R1–R4, HOMECHESS và R_Trash từ bộ tọa độ cố định
`calibration/physical_teaching_points_user0.json` (tool 0/user 0), không đọc lại
teaching points/WObj trên controller. Không cần chọn frame trên pendant mỗi lần
mở game. Sau cập nhật code, khởi động lại ứng dụng rồi xác nhận bàn và F9/F10 như
bình thường. Telemetry robot và đối soát FEN vẫn hoạt động.

Chạy lệnh tại thư mục repo bằng môi trường Python đã cài các dependencies.

Mỗi lần mở game/chọn chế độ từ màn hình đầu sẽ tạo **phiên mới, FEN khai cuộc
mới, Đỏ đi trước**. Xếp lại đủ 32 quân đúng vị trí ban đầu trước khi chơi bằng
robot thật. Camera lấy ảnh mới để xác nhận toàn bộ bàn; ứng dụng không tự nạp
FEN hoặc nước đi đang dở của lần chạy trước. Ván cũ được lưu trong lịch sử phiên
(`session_archive` trong journal), không bị xóa cùng các biên nhận lệnh robot.
Hiện không có nút tiếp tục ván cũ trong launcher.

Nếu lần trước robot bị ngắt/lỗi, phiên mới vẫn giữ yêu cầu kiểm tra tay/kẹp và
xác nhận robot đã dừng. Theo thông báo phục hồi, dùng Ctrl+F8 khi cần rồi V xác
nhận **bàn khai cuộc mới**; sau đó mới F9/F10 để cho phép chuyển động. Khởi động
lại không tự phát lại lệnh robot. Việc lấy ảnh mới dùng calibration camera đã
lưu; không bắt buộc chấm lại bốn góc nếu camera/bàn vẫn ở vị trí cũ.

Trong PowerShell: chạy `.\SETUP_WINDOWS.bat` một lần để cài Python dependencies và
Three.js theo `package-lock.json` (cần Node.js LTS/npm). Sau đó dùng `.\RUN.bat`;
tham số được chuyển nguyên vẹn vào `main.py`, ví dụ `.\RUN.bat --physical`,
`.\RUN.bat --board-only` hoặc `.\RUN.bat --viewer-port 8090 --telemetry-port 8770`.
Mặc định vẫn là mô phỏng; `--robot`/`--physical` kết nối ban đầu chỉ đọc.

`RUN.bat` ưu tiên `.venv312` rồi `.venv`, kiểm tra nhanh `pygame`, `numpy`, `cv2`,
`pybullet`, `websockets` trước khi chạy, và giữ nguyên mã thoát của `main.py`.
Đặt `XIANGQI_NO_PAUSE=1` khi chạy từ script/CI để bỏ bước chờ Enter. Nếu thiếu
`ultralytics` hoặc `node_modules/three`, launcher chỉ cảnh báo; game vẫn có thể
chạy ở chế độ không dùng camera/viewer.

Nếu viewer trống: xem lỗi `VIEWER_FAILED` trong phiên log. Viewer dùng
`three` từ `node_modules/three` và `occt-import-js` đã vendor tại
`robot-3d-viewer/vendor/occt-import-js/` (JS + WASM + license), nên không cần
Internet/jsDelivr để tải CAD gripper. Thiếu module Three.js thì chạy lại setup
hoặc `npm ci --include=dev`. Server phục vụ `.mjs`/`.js` bằng MIME JavaScript
và `.wasm` bằng `application/wasm`. Sau khi cập nhật code server, thoát phiên
game cũ, chạy lại `RUN.bat` rồi tải lại trang bằng Ctrl+F5.

Mỗi phiên tự ghi log vào `logs/<id-phien>/`; đường dẫn xuất hiện trên terminal. Dùng `--log-level DEBUG` để xem chi tiết hơn hoặc `--log-dir <thu-muc>` để đổi nơi lưu. Xem [LOGGING.md](LOGGING.md) để đọc mã lỗi và truy vết nước đi.

| Lệnh | Chức năng |
|---|---|
| `python main.py` / `--sim` | Game + mô phỏng FR3 + viewer; không dùng camera/robot thật |
| `python main.py --board-only` | Game-only: bàn cờ 2D, không mô phỏng/camera/robot/viewer |
| `python main.py --robot` | Game + camera + FR3 thật + viewer đồng bộ; kết nối ban đầu chỉ đọc |
| `python main.py --no-3d` | Vẫn mô phỏng/kết nối robot, chỉ không mở web viewer |
| `python main.py --help` | Xem các lựa chọn, không mở thiết bị |

Các alias cũ `--virtual`, `--physical`, `--no-viewer` vẫn dùng được. `--board-only`/`--robot`/`--sim` là tên dành cho người vận hành; `--no-3d` chỉ tắt cửa sổ 3D, **không** tắt robot hay mô phỏng.

Màn hình chính có ba thẻ môi trường: **Chơi trên máy**, **Mô phỏng 3D**, **Robot thật**. Flag CLI chỉ chọn sẵn thẻ; người dùng vẫn có thể đổi thẻ trước khi chọn chế độ chơi. Thẻ **Robot thật** đi qua đúng luồng camera + FR3 read-only và vẫn cần F9/F10 để bật chuyển động.

> **Lưu ý dây mạng robot:** cáp/đầu nối Ethernet tới `192.168.58.2` đang lỏng,
> nên kết nối có thể mất tạm thời. Kiểm tra bằng
> `ping -n 2 -S 192.168.58.3 192.168.58.2`, cắm lại dây nếu timeout; không bật
> F9/F10 khi link chưa ổn định. Chi tiết: [`../ROBOT_CONNECTION.md`](../ROBOT_CONNECTION.md).

### Camera Monitor khác quét FEN như thế nào

- **Camera Monitor** hiển thị kết quả CChess ONNX theo từng frame và tổng số quân
  (`Đỏ 16 / Đen 16`). Đây là hiển thị nhận diện, không phải xác nhận FEN.
- **Quét FEN / V / F4** dùng cùng CChess nhưng yêu cầu thêm: board sanity, frame
  mới, hai mẫu liên tiếp giống nhau, confidence trên các ô có quân, và so khớp
  chính xác từng ô với FEN dự kiến.
- Vì vậy Camera Monitor có thể thấy đủ 32 quân trong khi FEN sai chỉ vì một quân
  lệch ô, sai loại, hoặc confidence thấp.
- `CCHESS_RECOVERY_MIN_CONFIDENCE` chỉ áp dụng cho ô có quân; confidence của ô
  trống không được dùng để chặn FEN. Log `camera.verification_failed` có
  `diff_cells` để chỉ ô lệch.

### Calibrate lại camera bằng 4 điểm bàn cờ

- Mặc định `--physical` dùng `perspective.npy` đã lưu.
- Muốn chấm lại 4 góc bàn từ camera, chọn thẻ **ROBOT THẬT**, tick **Chấm lại 4 góc bàn từ camera** rồi bấm **VS ROBOT**.
- App mở cửa sổ **CALIBRATE** với ảnh camera. Click lần lượt 4 giao điểm ngoài cùng của lưới:
  1. Xe Đen trái
  2. Xe Đen phải
  3. Xe Đỏ phải
  4. Xe Đỏ trái
- Bấm `S` để lưu, `R` để chấm lại, `Q`/`ESC` để hủy. Lưới vàng hiện trên ảnh để kiểm tra trước khi lưu.
- Checkbox này bỏ qua auto-detection và mở thẳng chế độ chấm tay. Chỉ có hiệu lực cho một lần khởi động.
- Có thể chọn sẵn bằng `python main.py --physical --recalibrate-camera`. Flag này chọn sẵn checkbox (chấm tay); nếu bỏ tick, app dùng luồng cũ: auto trước, fallback chấm tay.
- Nếu chưa có `perspective.npy`, app tự mở calibration ở lần chạy đầu. File hỏng làm startup dừng với hướng dẫn.
- Không có cửa sổ calibration không có nghĩa là camera không được kiểm tra: app vẫn mở camera, đọc frame và kiểm tra ma trận đã lưu.
- Calibration này chỉ sửa phối cảnh camera → lưới bàn cờ. Nó **không** sửa R1–R4 của controller và không cấp quyền chuyển động; F9/F10 vẫn bắt buộc.
- Physical cần **cả** model CChess ONNX và YOLO `best.pt`. Thiếu một trong hai, startup dừng với `Physical camera recognition unavailable`.
- `verify_physical_board` vẫn đòi khớp chính xác 90 ô, nhưng có retry tối đa `VERIFY_BOARD_RETRY_TIMEOUT_SEC` (mặc định 2 giây).

Chọn chế độ chơi trên màn hình đầu. Khi chọn ván, engine/backend/camera tương ứng được khởi tạo; viewer tự mở và Connect live tự kết nối sau khi tải model xong. Quân cờ được đồng bộ từ GameState, tay robot từ telemetry. Ở chế độ physical, quân simulation cập nhật sau khi camera xác nhận nước đi hoàn tất.

## Khi camera lag hoặc physical viewer OFFLINE

Polling tự động dùng kết quả nhận diện của luồng nền; không chạy lại model ở mỗi lượt giao diện. Mẫu cũ/lặp không được dùng để đủ điều kiện xác nhận nước đi. Lần đầu khởi tạo model và thao tác SPACE/scan vẫn có thể chờ.

Nếu chưa đo `BOARD_CALIBRATION_OFFSET_MM`, server web vẫn mở **PREVIEW OFFLINE** với lý do. Không có live telemetry trong trạng thái này; model/bàn mặc định trên web chưa đại diện setup thật. Chỉ sau khi calibration hợp lệ và bridge khởi tạo được, WebSocket/live mirror mới chạy. Không nhập số đo giả để bỏ gate.

Sau cập nhật, thoát game cũ rồi chạy `.\RUN.bat --physical`; tải lại viewer bằng Ctrl+F5. Xem `ui.slow_frame`, `camera.slow_inference`, `twin.unavailable` trong log để phân biệt UI chờ, model chậm và mirror chưa sẵn sàng.

## Test gắp–thả riêng

Trong ván, bấm **T** hoặc **TEST GẮP / THẢ**, chọn quân đỏ/đen rồi chọn ô trống.
Test dùng executor và R1–R4 hiện tại; không sửa FEN/lượt của ván. Simulation cập nhật
identity của bàn test sau khi chuyển động thành công. Bấm T để thoát; khôi phục bàn
và **New Game** để chơi tiếp. Lỗi lệnh, camera hoặc đồng bộ sẽ khóa test, không tự thử lại.
Robot thật vẫn phải được kích hoạt qua F9/F10 và camera xác nhận trước/sau thao tác.
Chế độ game-only `--virtual` không có robot/simulation nên không chạy test gắp–thả.

Đo sai số camera/grid và grid/robot độc lập: `python scripts/measure_geometry.py gui`.
Xem [geometry-measurement.md](geometry-measurement.md) để chuẩn bị frame và phiên đo.

## Chơi bằng robot thật

`--physical` không tự bật motor hoặc gripper. Sau khi người vận hành đã kiểm tra setup, calibration, tool, vùng chuyển động, tốc độ và nút dừng khẩn cấp: bấm **F9**, rồi **F10** để xác nhận bật quyền chuyển động. F9 lần nữa hủy yêu cầu. Phải có camera xác nhận bàn hiện tại, telemetry robot mới và idle, twin đã đồng bộ, không có nước đi/lỗi đang treo. Thiếu điều kiện thì chương trình từ chối bật.

Người đi ngoài đời rồi bấm SPACE. AI chỉ cập nhật nước đi khi chuyển động thành công và camera xác nhận toàn bộ bàn. Nếu đồng bộ viewer thất bại, game báo lỗi và chặn AI; dùng luồng quét/xác nhận bàn để khôi phục.

## Lưu bàn và khôi phục lỗi

Trong viewer, tab **Vị Trí** có **Lưu vị trí đã áp dụng** / **Khôi phục profile đã lưu**. Profile chỉ dùng cho mô phỏng; sau restart nạp theo thao tác có giám sát qua SERVICE_SAFE. Khi game khóa, panel trái hiện lý do, nước chờ và bước khôi phục. Xem `docs/BOARD_PROFILE_AND_RECOVERY.md`.

Khi physical đang khóa vì lỗi nước đi, bấm **XÓA PHIÊN LỖI** (`F12`) để app
kiểm tra toàn bộ bàn thật khớp FEN hiện tại rồi mới xóa giao dịch lỗi và mở khóa.
Nếu camera báo bàn chưa khớp, nút không xóa và yêu cầu dùng `V`/`F4` hoặc
calibrate lại camera. Nút không gửi lệnh robot/gripper.

Khi khởi động lại, giao dịch AI lỗi do kiểm tra **HOMECHESS trước khi gửi lệnh**
được bỏ khỏi pending transaction thay vì nạp lại mãi. Bàn/FEN vẫn ở trạng thái
khóa và phải xác nhận bằng `V`/`F4` hoặc **XÓA PHIÊN LỖI**; các lỗi sau khi đã
gửi lệnh robot vẫn được giữ để điều tra, không tự động xóa.

## Cổng đang được sử dụng

Không chạy hai game trên cùng cổng telemetry. Dừng phiên cũ do mình mở hoặc chọn cổng khác:

```powershell
python main.py --viewer-port 8090 --telemetry-port 8879
```

Viewer mặc định: `http://127.0.0.1:8088/robot-3d-viewer/`. Nếu cổng web bận, chương trình báo rõ và không dừng một server khác. HTTP phục vụ assets viewer/shared và thư viện Three.js nội bộ trên localhost. Nếu chưa có `node_modules/three`, chạy `npm install` một lần ở thư mục repo. Không cần CDN Three.js khi mở viewer.

Robot–robot: bấm nút **NƯỚC TIẾP** (hoặc F7) để chạy một lượt. Chờ lượt đó ghi vào lịch sử rồi mới bấm tiếp. **SURRENDER** chỉ kết thúc tự đấu khi một lượt đã hoàn tất; không ngắt giữa lúc tay đang gắp.

## Kiểm chứng ngày 2026-10-05

- Sửa và kiểm tra code trong worktree `D:/OJT/_simple_launch_sync_20261005`, sau đó giữ các thay đổi đã kiểm chứng ở repo chính. Không chạy phần cứng.
- Gate cuối: 108 kiểm thử liên quan qua, exit code 0, dùng `tools/test_fast.ps1 -Workers 2` cho các file simple launch, phase2 vision, camera startup/game pipeline, self-play, physical camera commit, end-to-end twin và legacy physical gates.
- Startup thực tế với SDL ảo: mặc định khởi tạo engine, backend virtual, telemetry, HTTP viewer và đồng bộ nước người; `--virtual` khởi tạo engine/game, không mở camera hoặc simulator, thực hiện được nước AI. Cả hai thoát sạch. Browser mở được gọi qua mock; chưa xác minh render/autoconnect bằng trình duyệt thật trong lần này.
- Node kiểm tra cú pháp viewer và `test_viewer_camera_reconciliation.mjs` qua: vị trí, ẩn quân bị ăn và khôi phục snapshot.
- Full regression đầu tiên: 655 qua / 3 thất bại. Hai lỗi mới về mock cấu hình đã sửa và kiểm tra lại trong gate 108 ca. Ca `test_phase3_final_g90_corrective.py::Phase3FinalG90CorrectiveTests::test_shortened_tool_rejects_unreachable_near_center_critical_routes` cũng thất bại trên worktree baseline sạch `7d8c5de`: test kỳ vọng pose không tới được nhưng backend chấp nhận. Chưa sửa hoặc kết luận lại hợp đồng vùng với tới trong đợt này. Không tuyên bố full suite đã qua.
- Đường bật FR3 được kiểm bằng mock; calibration thực, chuyển động và đồng bộ camera/robot ngoài đời chưa được kiểm chứng.

## Khi chọn chế độ nhưng khởi tạo thiết bị thất bại

Game giữ màn hình đầu và hiện lỗi để bạn khắc phục rồi chọn lại chế độ.
Nếu không đọc được camera: đóng Windows Camera/OBS/Teams và các phiên game khác
đang dùng thiết bị, kiểm tra VIDEO_INDEX/VIDEO_SOURCE và quyền camera Windows.
Không tự chuyển sang camera khác; camera đúng phải cung cấp frame hợp lệ.

Nếu log báo Physical board surface contact offset has not been calibrated,
viewer đồng bộ phần cứng chưa sẵn sàng. Cần calibration điểm chạm bàn có
nguồn gốc phép đo; chiều dài CAD gripper không tự thay thế phép đo này.
