# Khởi động dự án

Chạy lệnh tại thư mục repo bằng môi trường Python đã cài các dependencies.

Trên Windows: chạy `SETUP_WINDOWS.bat` một lần để cài Python dependencies và
Three.js theo `package-lock.json` (cần Node.js LTS/npm). Sau đó dùng `RUN.bat`;
tham số được chuyển nguyên vẹn vào `main.py`, ví dụ `RUN.bat --physical`,
`RUN.bat --virtual` hoặc `RUN.bat --viewer-port 8090 --telemetry-port 8770`.
Mặc định vẫn là mô phỏng; `--physical` kết nối ban đầu chỉ đọc.

Nếu viewer trống: xem lỗi `VIEWER_FAILED` trong phiên log. Thiếu module Three.js
thì chạy lại setup hoặc `npm ci --include=dev`. Server phục vụ `.mjs` và `.js`
bằng MIME JavaScript cố định. Sau khi cập nhật code server, thoát phiên game cũ,
chạy lại `RUN.bat` rồi tải lại trang bằng Ctrl+F5.

Mỗi phiên tự ghi log vào `logs/<id-phien>/`; đường dẫn xuất hiện trên terminal. Dùng `--log-level DEBUG` để xem chi tiết hơn hoặc `--log-dir <thu-muc>` để đổi nơi lưu. Xem [LOGGING.md](LOGGING.md) để đọc mã lỗi và truy vết nước đi.

| Lệnh | Chức năng |
|---|---|
| `python main.py` | Game + mô phỏng FR3 + viewer; không dùng camera/robot thật |
| `python main.py --virtual` | Theo quy ước của chủ dự án: **tắt mô phỏng**, chỉ chơi game bằng chuột với AI |
| `python main.py --physical` | Game + camera + FR3 thật + viewer đồng bộ; kết nối ban đầu chỉ đọc |
| `python main.py --no-viewer` | Game + mô phỏng, không mở web viewer |
| `python main.py --help` | Xem các lựa chọn, không mở thiết bị |

Chọn chế độ chơi trên màn hình đầu. Khi chọn ván, engine/backend/camera tương ứng được khởi tạo; viewer tự mở và Connect live tự kết nối sau khi tải model xong. Quân cờ được đồng bộ từ GameState, tay robot từ telemetry. Ở chế độ physical, quân simulation cập nhật sau khi camera xác nhận nước đi hoàn tất.

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
