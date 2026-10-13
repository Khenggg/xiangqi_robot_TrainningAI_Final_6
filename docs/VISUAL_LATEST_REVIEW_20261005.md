# Review code mới nhất nhánh visual — 05/10/2026

> **Cập nhật sau phê duyệt:** đã tích hợp chọn lọc vào working tree
> `feature/unified-robot-vs-robot`, sửa các lỗi phát hiện và kiểm chứng trong worktree riêng.
> Mục **Kết quả tích hợp và system test** cuối file là trạng thái hiện tại.
> Các câu “chưa merge/chỉ review” bên dưới là lịch sử đánh giá trước khi thực hiện.

## Mốc kiểm tra

- Đã fetch `origin/feature/visual-correction-v2` thành công; remote tiến từ `e6bb632` đến **`652af26`**.
- Đây là 7 commit chưa có trong HEAD tích hợp `7d8c5de`: `36b7448`, `0504c67`, `5e516d5`, `836ed4d`, `be8dc30`, `22edd27`, `652af26`.
- Review delta `e6bb632..652af26`: 21 file, chủ yếu camera calibration, tâm quân, test pick/place, đo hình học và debug. Repo chính chưa merge các commit này.
- Worktree kiểm chứng: `D:/OJT/_visual_review_652af26`, detached HEAD. Index graph riêng, đọc architecture, search/trace và đối chiếu source tại commit này.
- Chỉ chạy test và probe với SDK/camera giả, không gọi FR3 thật. Không khởi động `main.py` của nhánh visual với config mặc định.

## Findings cần sửa trước khi tích hợp

### [P1] Test gắp–thả mới vẫn tiếp tục sau mã lỗi motion 112

**Vị trí:** `src/hardware/hardware_manager.py:337–353`, đặc biệt lệnh `robot.move_piece` tại dòng 350; `src/hardware/robot_VIP.py:361`, `397`, `579–582` và `666`.

`execute_pick_place_test` gọi trực tiếp `move_piece`, không kiểm tra kết quả typed execution. Các wrapper MoveCart hiện cho mã 112 đi qua rồi trả số đó; pick/place không kiểm tra số trả về. Vì vậy lỗi tiếp cận/hạ xuống có thể không chặn lệnh gripper và các stage phía sau.

**Tái hiện:** dùng FR5Robot thật của nhánh này với SDK Mock, mọi `MoveCart` trả 112, camera verification giả xác nhận. Kết quả: **7 lần MoveCart lỗi**, **3 lần gọi gripper**, vẫn yêu cầu HOME và hàm test trả visual target như thành công. Không có lệnh phần cứng thật.

**Nguồn lỗi:** xử lý 112 đã có trong robot legacy; commit `5e516d5` tạo thêm luồng test sử dụng đường đó. Không quy toàn bộ lỗi wrapper cho commit mới.

**Sửa đề xuất:** đưa test qua executor có kết quả `MotionExecutionResult`, kiểm tra từng stage và dừng ngay khi không thành công. Giữ cơ chế typed failure của repo tích hợp; không thay bằng `move_piece` legacy hoặc chỉ kiểm tra camera cuối nước.

**Tin cậy:** cao về control flow; chưa kiểm chứng FR3 thật.

### [P1] Test thất bại sau motion không khóa lần chạy kế tiếp

**Vị trí:** `src/ui/input_handler.py:309–331`; `src/hardware/hardware_manager.py:350–353`.

Khi arm đã được gọi nhưng `verify_visual_move` không xác nhận được, handler chỉ in lỗi/hiện status và giữ bàn test như cũ. Không ghi trạng thái cần đối soát để chặn lần chạy tiếp theo. Trạng thái vật lý có thể đã thay đổi trong khi giao diện vẫn giữ nguồn cũ.

**Tái hiện:** lần execute đầu báo lỗi “Motion executed; camera verification failed”; chọn quân khác rồi ô trống. Handler gọi execute lần thứ hai, cập nhật bàn test và vẫn giữ mode active, chưa có bước đối soát giữa hai lần.

**Sửa đề xuất:** sau lỗi có khả năng đã thực thi motion, latch fault và chặn execute cho đến khi có xác nhận trạng thái bàn/payload phù hợp. Phân biệt lỗi trước motion với lỗi sau motion. Bàn test cần đồng bộ vào world simulation riêng bằng identity/cells; việc không commit FEN game không có nghĩa được bỏ đồng bộ vật thể.

**Tin cậy:** cao về GUI control flow. Mức sai lệch ngoài đời phụ thuộc kết quả thực thi chưa xác minh.

## Các phần mới có thể tận dụng

| Tính năng | Nhận xét |
|---|---|
| Calibration auto bằng nhiều frame | Có consensus whole-board và kiểm tra jitter; lưu ma trận sau người dùng chấp nhận. Hủy không ghi đè ma trận trước. |
| Stable center pick | Không tự rơi về foot point khi thiếu tâm ổn định; thay bằng lỗi để chặn pick. Đây là thay đổi cần mang sang luồng physical tích hợp. |
| Đo camera→grid và grid→robot riêng | Có ảnh gốc, ma trận dùng, overlay, CSV và metadata; phép đo không tự áp dụng correction hay thay calibration. |
| Client đo từng bước | Kết nối raw chỉ đọc teaching points; bỏ `connect()` legacy để không pulse gripper. Enable/motion chỉ xảy ra khi người dùng chọn bước chạy. Kiểm tra lỗi stage trong measurement tốt hơn đường pick test. |
| Debug visual pick | Ghi delta XY mm và chiếu grid correction về pixel; có status đang gắp/lần gắp gần nhất. Cần giữ API debug hiện có của bản tích hợp khi ghép. |
| Thu nhỏ cửa sổ 0,9× | Đã map lại click, nhưng bản tích hợp hiện có resize/fullscreen/fit desktop đầy đủ hơn; giữ `GameWindow` hiện tại. |

Stable confidence/jitter không tự chứng minh camera chính xác hoặc motion an toàn. Công cụ đo giúp thu số liệu, không thay thế calibration/parity đã đo.

## Những ràng buộc khi tích hợp

1. Giữ launcher hiện tại, `--virtual` game-only, `--physical` khởi đầu chỉ đọc và quyền enable theo gate của repo tích hợp.
2. Nhánh visual vẫn có `config.DRY_RUN=False`; `initialize_all` gọi `_init_robot` trước `_init_camera`, `connect()` enable robot/pulse gripper rồi `_init_robot` gọi HOME. Đây là hành vi legacy tại bản nền, không phải tính năng calibration mới; không đem trở lại repo tích hợp.
3. Measurement dùng Tool 0/User 1 như robot legacy của visual. Repo tích hợp kiểm tra frame base/parity khác; phải lấy tool/user/mapping từ authority hiện hành và ghi provenance. Không nhập CSV User 1 vào base frame một cách mặc định.
4. Test pick mode có `pick_test_board` riêng và chủ ý không đổi FEN; nếu đưa vào bản có viewer, phải cập nhật vật thể trong world và identity tương ứng qua cùng runtime authority. Không gọi robot trực tiếp để bypass operation lock/telemetry/failure gate.
5. Ghép delta chức năng vào `main.py`, `hardware_manager.py`, `robot_VIP.py`, `game_state.py`, `input_handler.py`, `debug_dashboard.py`; không thay toàn bộ các file đó bằng bản visual vì sẽ mất các sửa tích hợp/logging/safety đã có.

## Bằng chứng thực thi

Chạy Python `C:/Users/Ken/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe` trong worktree, basetemp riêng; các test robot dùng Mock.

- **36/36 test mới đạt:** auto calibration safety, center pick no fallback, geometry measurement, measurement client, pick/place mode.
- **26/26 regression liên quan đạt:** debug dashboard, planned command, visual estimator, human confirmation, commit/AI handoff.
- Gate gộp cuối: **62 passed**, exit 0. Những test hiện có không bao phủ hai trường hợp lỗi tái hiện ở trên.
- Probe SDK/camera giả tái hiện hai findings; exit 0 chỉ nghĩa probe chạy hoàn tất, không nghĩa sản phẩm không có lỗi.

Artifacts tại `reports/visual-review-652af26/`: `target-tests.log`, `reproduction.log`, `review_probe.py`. Chạy probe với PYTHONPATH trỏ đến worktree commit 652af26, không chạy với module của repo tích hợp rồi coi đó là cùng bằng chứng.

## Quyết định đề xuất

Tận dụng calibration ổn định, center pick strict, measurement và debug; sửa hai P1 của test pick/place trước khi ghép. Giữ simulation/viewer, launcher, logging và gate phần cứng của repo tích hợp. **Chưa nên merge nguyên nhánh.** Đợt này chỉ review, chưa sửa source nhánh visual và chưa merge/push.

## So sánh từng commit với code hiện tại

Đối chiếu trực tiếp cả HEAD tích hợp và các sửa chưa commit trong repo chính, không chỉ đọc commit message. Lợi ích dưới đây là đánh giá từ source/kiểm chứng nhánh visual; chưa có bằng chứng chạy bản đã ghép vì chưa thực hiện merge.

| Commit | Thay đổi thực tế | So với bản hiện tại | Quyết định |
|---|---|---|---|
| `36b7448` | Thu cửa sổ xuống 90%, scale click về canvas | Bản hiện tại có `GameWindow`: fit theo desktop, resize, fullscreen, xử lý letterbox và DPI. Scale cố định 90% không giải quyết đầy đủ màn hình nhỏ. | **Bỏ phần window của commit này**, giữ hiện tại. |
| `0504c67` | Lấy nhiều frame, consensus bốn góc, giới hạn jitter, preview chờ S chấp nhận; cancel không ghi đè calibration | Bản hiện tại chọn frame có score cao nhất trong 5 frame, lưu M trước preview và đợi preview theo thời gian. Thay đổi mới kiểm soát việc nhận calibration tốt hơn. | **Nên tích hợp sớm**. Gắn lỗi/cancel vào readiness và logging hiện tại, bảo đảm hủy không bật quyền motion. |
| `5e516d5` | T bật chế độ chọn bất kỳ quân đỏ/đen rồi ô trống để test gắp–thả, không đi theo luật/AI, dùng bàn test riêng | Là chức năng mới hữu ích để commissioning nhanh. Nhưng đường mới gọi robot legacy trực tiếp, có hai P1 đã tái hiện; chưa đồng bộ bàn test với world của bản tích hợp. | **Chưa nhận nguyên commit**. Giữ ý tưởng/GUI, xây adapter vào runtime/executor hiện tại rồi sửa fault/reconciliation. Đây là phần tích hợp khó nhất. |
| `836ed4d` | Thiếu camera/center estimator hoặc không đủ tâm ổn định thì raise; bỏ fallback foot-point; in delta XY mm | Bản hiện tại đã lấy nhiều sample và kiểm tra spread, nhưng vẫn fallback sang foot-point nếu center không đạt. Cải tiến chính là không âm thầm đổi cách định vị, không phải thuật toán ổn định hoàn toàn mới. | **Nên tích hợp sớm** vào physical pick; giữ typed failure, log và không buộc virtual/game-only có camera. |
| `be8dc30` | Tạo phép đo riêng camera→grid và grid→robot, lưới 9 điểm tham chiếu, ảnh/CSV/metadata, robot plan-only hoặc --move | Bản hiện tại có R1–R4 và parity/validation mô phỏng, nhưng chưa có công cụ riêng thu sai số pixel/grid và XY vật lý như vậy. Hai nhóm công cụ bổ sung cho nhau. | **Nên nhận** phần tính sai số, lưu dữ liệu và chế độ plan-only; thích nghi frame/mapping và quyền motion trước khi dùng --move. |
| `22edd27` | Client Tkinter tiếng Việt từng bước, checklist, click/undo ảnh, nhập XYZ, ghi số đo, luồng worker/UI | Dễ dùng hơn console của commit trước; không nâng độ chính xác phép đo tự động. Chưa tự đọc/xác minh XYZ nhập tay. Phụ thuộc `be8dc30`. | **Nên nhận sau commit đo nền**; dùng authority/frame hiện hành, giữ cửa sổ và SDK lifecycle độc lập. |
| `652af26` | Lưu trạng thái correction trong robot, vẽ vector correction camera pixel trong debug, cho xoay hiển thị; đồng thời đổi MOVE_SPEED 70→60 | Bản hiện tại debug đã đọc telemetry backend virtual/physical và planned command, nhưng chưa có vector correction. Visual thêm quan sát tốt hơn; thay cả debug class sẽ mất backend support. Giảm tốc không phải bằng chứng safety. | **Nhận chọn lọc phần correction/debug** vào class hiện tại, đưa sự kiện vào logging. Tách thay đổi tốc độ để quyết định riêng theo vận hành, không tự nhận 60 như ngưỡng an toàn. |

### Các điểm giữ của repo hiện tại

- `src/ui/game_window.py` và cách main map mouse/resize/fullscreen.
- `src/core/launch_options.py`, `src/core/project_logging.py`, các sửa reset/rollback và startup lifecycle.
- `HardwareManager.execute_piece_move`, operation lock, typed result và observer đồng bộ game/twin.
- `FR5Robot.physical_motion_authorized`, activation có xác nhận, reject lỗi stage; không thay bằng donor enable/pulse/HOME lúc connect.
- Debug `backend.get_state_snapshot()` cho virtual/physical và toàn bộ simulation/viewer/geometry hiện hành.

### Thứ tự tích hợp đề xuất

1. `0504c67` + `836ed4d`: tăng kiểm soát calibration và định vị pick, phạm vi thay đổi nhỏ nhất; test cancel/thiếu center phải không phát motion.
2. `be8dc30` + `22edd27`: bổ sung bộ công cụ đo, dùng chính frame/mapping của bản tích hợp; plan-only và mở kết nối phải không enable/move/gripper.
3. Phần debug của `652af26`: bổ sung vector mà vẫn đọc được virtual/physical backend, không làm lỗi debug ảnh hưởng game.
4. Tính năng của `5e516d5`: chỉ tích hợp sau khi sửa hai P1 và chứng minh camera/test-board/world/FEN được tách quyền đúng. Test không cần luật Xiangqi nhưng vẫn cần collision, identity, operation lock và recovery.
5. Không nhận scale window `36b7448`; giữ tốc độ hiện hành đến khi có quyết định riêng.

**Đánh giá tổng hợp:** năm commit có phần đáng tích hợp (`0504c67`, `836ed4d`, `be8dc30`, `22edd27`, `652af26`); một commit có ý tưởng đáng làm lại (`5e516d5`); một commit không mang lợi ích thêm cho window hiện tại (`36b7448`). Ghép chọn lọc sẽ tăng khả năng nhận biết/đo/debug lỗi vật lý; merge nguyên nhánh chưa chắc tốt hơn và có nguy cơ làm mất những chức năng tích hợp đã kiểm chứng.

## Kết quả tích hợp và system test — 05/10/2026

### Phạm vi đã áp dụng

Tích hợp chọn lọc vào repo chính `feature/unified-robot-vs-robot`, HEAD nền `7d8c5de`;
nguồn visual đã fetch là `652af26912c66ef160f7c622a49fed3feaca0ea0`.
Các sửa hiện nằm trong working tree, chưa commit/push. Các thay đổi chưa commit có sẵn
về launcher, log, recovery và simulation được giữ nguyên. Đây là bằng chứng kiểm chứng
bản làm việc sau tích hợp, khác với review commit donor ở phần đầu.

| Phần | Kết quả |
|---|---|
| Calibration `0504c67` | Consensus nhiều frame, preview chờ chấp nhận; cancel không ghi đè ma trận |
| Center pick `836ed4d` | Thiếu tâm box ổn định thì từ chối; không đổi sang footpoint |
| Measurement `be8dc30` / `22edd27` | GUI/CLI riêng, ảnh/CSV/metadata; dùng calibration provider hiện tại, User 0 và tool của R1–R4 |
| Debug `652af26` | Bù XY mm/pixel và hướng vector; giữ backend telemetry và tùy chọn không spawn cửa sổ |
| Manual test `5e516d5` | Viết lại qua executor chung, MoveContext/identity, board test riêng và khóa lỗi |
| Window / tốc độ | Giữ GameWindow fit/resize/fullscreen và MOVE_SPEED=70; không lấy scale 90% hoặc đổi tốc độ tự động |

### Lỗi/gap đã sửa

1. `HardwareManager.execute_pick_place_test` kiểm tra typed result trước camera và commit scene.
   SDK 112 không còn bị coi là hoàn thành. Executor game và test dùng cùng nhánh virtual/physical.
2. `InputHandler._handle_pick_test_click` khóa lỗi lệnh, camera và scene. Không cho lần gắp tiếp,
   không cho T bật lại để xóa lỗi. Game/AI/self-play cũng chặn tại entry point khi test hoặc chờ khôi phục.
3. Bàn test có bản sao symbol và identity riêng. Chuyển động thành công mới reconcile scene;
   FEN/lượt bàn game không đổi. Sau test phải khôi phục bàn và New Game; physical reset vẫn cần camera đối soát.
4. `RobotMeasurement` không bypass connect/calibration/activation hiện hành: snapshot TCP mới ≤2s,
   IDLE, finite và Z thật ≥SAFE_Z. Dùng Z thật cho travel, không tin chỉ số nhập trên pendant.
   Lỗi khóa phiên; close/menu/restart tắt enable của phiên đã kích hoạt, đóng RPC và báo lỗi cleanup.
   Manual physical test fault dùng `FR5Robot.deactivate_physical_control`, không gửi gripper/HOME.
5. `board_picker.mjs` không nhận carried status alias, cell sai biên hoặc khoảng cách không hợp lệ.
   Giới hạn chọn mặc định là nửa pitch 40mm; đây là logic chọn ô trong viewer, không phải ngưỡng an toàn vật lý.
6. Thay readout HTML 150mm cũ bằng trạng thái chờ profile. Contract tọa độ/tool đọc canonical scene/profile.
   Test giả định tool cũ không với tới hai ô đã lỗi thời; thay bằng target TCP dưới mặt bàn 20mm,
   kiểm tra từ chối và joints/TCP bất biến, không sửa collision guard để ép test xanh.
7. GUI hiện lỗi khóa test và yêu cầu khôi phục kể cả khi status timeout. Thêm Pillow vào dependencies
   cho measurement GUI.

### Bằng chứng thực thi

Tất cả chạy tại `D:/OJT/_simple_launch_sync_20261005`, không kết nối/điều khiển FR3 thật.
Không dùng toàn bộ thư mục tests gốc vì có các script hardware legacy; chọn các module mock an toàn.

| Gate | Kết quả / artifact | Phạm vi |
|---|---|---|
| Broad regression `tools/test_fast.ps1 -Workers 4` | **731 parallel + 8 serial passed**, exit 0; `full-regression.log` | tests/unit và các module visual/mock được chọn; khoảng 648s |
| Follow-up integration | **97 passed**, exit 0; `final-target.log` | Sau sửa cleanup/frame, direct game guards và đo trước sync |
| System/owned cleanup/SDK | **51 passed**, exit 0; `system-and-cleanup.log` | Sau thêm revoke activation cho lỗi physical manual test |
| GUI/status/window | **30 passed**, exit 0; `final-ui.log` | Bản cuối: lỗi khóa/resume vẫn hiện, không phá window contract |
| Node viewer | **9/9 exit 0**; `node-results.json` | Picker, board mesh transform, camera reconciliation, tọa độ, ruler, gripper/telemetry, placement, profile, single authority |
| Startup | Game-only và game+simulation đều **exit 0**; `startup-results.json` | main.py, engine, twin, viewer HTTP/assets, piece sync và cleanup |
| Actual PyBullet | GUI chọn quân/ô → manager → executor, bàn X+10mm/yaw+3° | Sai lệch XY **0.1504mm trước reconciliation**, không còn payload attached; guard vẫn bật |
| Reset | Giữ đúng taught placement, trả đủ 32 quân và identity | Không biến board test thành FEN game |
| GUI render | `manual-test-gui.png`, `manual-test-fault.png` | Production renderer; ảnh lỗi là fixture SDK112, không phải lỗi robot thật |

Các gate sau broad regression chỉ chạy lại phạm vi bị sửa; không cộng các số trên thành số test duy nhất.
Log rộng dùng snapshot trước vài sửa nhỏ cleanup/status; các sửa đó có follow-up riêng như bảng.
Nguồn chuyển động đã giữ cùng geometry/profile, không sửa chiều dài/gripper opening.

Artifacts: [reports/visual-integration-20261005](../reports/visual-integration-20261005/).
Test tích hợp mới: [test_visual_selective_integration.py](../tests/unit/test_visual_selective_integration.py).
Hướng dẫn: [START_PROJECT.md](START_PROJECT.md), [geometry-measurement.md](geometry-measurement.md).

### Mức tin cậy và phần chưa xác minh

- **Cao:** static diff, mock failure injection và kết quả thực thi bên trên cho bản làm việc đã ghép.
  Root source/worktree được đối chiếu SHA256 trong `verification-summary.json`.
- **Giới hạn:** optics camera thật, SDK/controller thật, R1–R4/contact offset thực và đường đi hardware
  chưa kiểm chứng. Công cụ đo trên cao cần commissioning/clearance do người vận hành xác nhận;
  không được diễn giải nó là planner chống va chạm cho robot thật.
- Không chứng minh toàn bộ 8010 route, mọi placement, hoặc hoàn thành một ván vật lý.
  Các cảnh/test cụ thể đã chạy được ghi rõ; warning còn lại là deprecation pygame/websockets.
- Graph detect_changes đã chạy nhưng index bao gồm lịch sử cũ; Git diff và file chính xác được dùng
  để xác định phạm vi hiện tại. Không sửa hoặc mở lại tài liệu tương lai đã bị treo.
