> **TẠM NGƯNG SỬ DỤNG — 2026-10-05:** Theo yêu cầu của chủ dự án, hiện tại không đọc, viện dẫn hoặc đề cập đến tài liệu này khi làm việc với dự án. Nội dung được lưu để tham khảo cho tương lai; chưa quyết định có triển khai hay không. Không dùng tài liệu này làm yêu cầu, kế hoạch thực hiện hoặc nguồn xác định trạng thái hiện tại. Cảnh báo này thay thế các tuyên bố “hiện hành” bên dưới, cho đến khi chủ dự án yêu cầu sử dụng lại.

# R1–R4: vị trí bàn cờ trong mô phỏng và phép đo thật

**Cập nhật 2026-09-29.** Đây là hướng dẫn hiện hành cho việc đổi vị trí bàn trên nhánh `feature/unified-robot-vs-robot`. Những số R1–R4 trong tài liệu cũ, mock backend và script legacy chỉ là ví dụ hoặc dữ liệu lịch sử. Không nạp chúng làm hiệu chuẩn FR3 thật.

## Quy ước bốn điểm

R1 = giao điểm lưới `(row=0, col=0)` (xe đen thứ nhất); R2 = `(0,8)` (xe đen thứ hai); R3 = `(9,8)` (xe đỏ bên tương ứng); R4 = `(9,0)` (xe đỏ còn lại). Đây là **tâm giao điểm trên mặt chơi**, không phải bốn góc gỗ. Trong board-local, theo mm: R1 `(-160,-180,0)`, R2 `(160,-180,0)`, R3 `(160,180,0)`, R4 `(-160,180,0)`. Thứ tự dạy là R1 → R2 → R3 → R4; cả bốn XYZ phải cùng hệ `robot_base`, đơn vị mm, cùng định nghĩa điểm chạm.

## Hôm nay: dùng bàn hiện tại trong simulator

Lấy R1–R4 bằng `BoardPlacementState.cell_to_robot_xyz(row,col)` của **pose bàn đang chạy** để điền sẵn bốn điểm. Đây là tọa độ **suy ra từ mô hình**, không phải phép đo đầu kẹp chạm bàn hay bằng chứng bàn ngoài đời ở vị trí ấy. Có thể chỉnh bốn bộ XYZ để thử một bố trí mới. Sau khi áp dụng, cùng một `T_robot_from_board` và `placement_version` phải đến MotionResolver, PyBullet và viewer; quân đang ở trên bàn phải chuyển theo biến đổi này. Kế hoạch chuyển động thuộc phiên bản cũ phải bị từ chối. Kiểm tra va chạm với cánh tay và đầu kẹp trước khi chuyển pose bàn; từ chối thay đổi khi robot đang di chuyển, kẹp đang giữ quân hoặc quân đang rơi/đang ổn định.

`forward_shift_mm` trong UI cũ chỉ là điều khiển một trục tương thích ngược. Nó **không đại diện** cho việc dời bàn sang trái/phải hoặc quay bàn. Không tính vị trí ô từ công thức cố định `X=-360-d-u, Y=-v`; dùng `T_robot_from_board` của phiên bản hiện tại.

### Thao tác đang có

Chạy `python tools/simulation/run_simulation_server.py --no-sync-physical` để **không truy cập IP FR3**, mở viewer và bấm **Connect live → Vị Trí → Lấy 4 điểm từ bàn mô phỏng**. Mười hai ô XYZ nhận tọa độ từ pose hiện tại. Sửa điểm cần thử, vào tab **Service** chuẩn bị dời bàn để robot ảo ở `SERVICE_SAFE`, rồi bấm **Áp dụng R1–R4**. Server fit hình chữ nhật, kiểm va chạm quét của bàn/quân với robot/kẹp và sàn, sau đó phát pose/phiên bản/world state mới. Nếu editor cũ hơn phiên bản đang chạy, nạp lại bốn điểm. Sau mỗi lần áp dụng cần chuẩn bị dời bàn lại. UI khóa slider một trục sau khi áp dụng R1–R4; **Reset Nominal** mới trở về điều khiển cũ.

Pose mới chỉ nằm trong bộ nhớ của phiên chạy simulator; khởi động lại server sẽ về scene JSON. Lưu bốn số đã nhập ra biên bản nếu muốn dùng lại. Kiểm tra 90 ô và tuyến đường sau mỗi lần đổi pose; kết quả mô phỏng không thay thế việc đo, kiểm clearance và commissioning FR3 thật.

## Bằng chứng mô phỏng hiện tại

Trong worktree tách biệt, lấy R1–R4 từ scene rồi cộng **10 mm theo X của robot** vào cả bốn điểm: R1 `(190,200,10.5)`, R2 `(190,520,10.5)`, R3 `(-170,520,10.5)`, R4 `(-170,200,10.5)` mm. GUI xác nhận `BOARD_TEACHING_POINTS_APPLIED`, phiên bản `1 → 2`, RMS `0.00 mm`; board, quân, MotionResolver và PyBullet cùng dùng pose mới. Thử quay 3° giữ nguyên tọa độ board-local của quân; thử quay 90° cho R1 mới `(160,540,10.5)` mm và 4/4 quỹ đạo ô cục bộ qua. Thử quét bàn vào robot và hạ bàn xuyên sàn đều bị từ chối, pose/quân giữ nguyên. `python -m pytest tests/unit/test_sim_board_teaching.py tests/unit/test_phase3_dynamic_board_placement.py -q -k 'sim_board_teaching or coordinate_transform_contract or board_placement_runtime_state_and_pybullet_consistency'`: **12 passed**.

GUI đã chạy `VALIDATE CURRENT PLACEMENT (90 Ô)` trên pose dịch 10 mm: **90/90 local cell trajectories pass** (IK tiếp cận/gắp và va chạm tiếp cận/gắp: 90/90). Kiểm tra 12 tuyến lấy mẫu từ nguồn tới đích: **12/12 pass** sau khi bộ kiểm tra tuyến chọn nhánh IK bằng cùng phép LAND/LIFT có kiểm va chạm như bộ kiểm tra 90 ô. Bộ kiểm tra cũ từng báo sai 7/12, tuyến đầu `(0,0) → (0,1)` ở LIFT vì dùng một nghiệm Grasp IK đơn lẻ. Đây là lỗi kiểm tra có sẵn, không phải kết quả va chạm do R1–R4 mới. Mẫu 12/8010 tuyến **không chứng minh mọi tuyến an toàn**; phải kiểm tra tuyến cụ thể trước khi chạy, và commissioning FR3 thật vẫn chưa thực hiện.

## Ngày mai: thay bằng bốn phép đo thật

Người vận hành đưa **chính đầu kẹp** tới gần từng giao điểm, hạ chậm dưới giám sát và dừng khi **điểm tiếp xúc đã chọn trên kẹp** vừa chạm mặt bàn. Không cần lắp đầu dò rời. Nhưng XYZ của bích J6, TCP trên controller và điểm thấp nhất của ngón kẹp không tự động trùng nhau. Trước khi nhập, xác định controller đang trả XYZ của frame nào; đo/hiệu chuẩn phép biến đổi từ frame đó đến **điểm tiếp xúc trên kẹp**, hoặc cấu hình TCP tại đúng điểm tiếp xúc rồi kiểm tra. Không gán bừa `[0,0,0]` cho offset của bích hay lấy chiều dài CAD 168,3 mm làm chiều dài thực đã đo. Bốn điểm phải dùng cùng tool/frame, cùng tư thế kẹp và cùng phương pháp dừng.

Nếu không có cảm biến lực/tiếp xúc được tích hợp và kiểm chứng, phần mềm **không thể tự biết** thời điểm kẹp vừa chạm mặt bàn; người vận hành phải tự dừng và xác nhận trước khi ghi mỗi điểm. Không phát lệnh tự hạ đến khi va chạm. Trên bốn ô xe đang có quân, cần dọn quân ra trước khi lấy mặt bàn; không chạm vào mặt trên quân rồi coi đó là mặt bàn.

Lưu bộ R1–R4 kèm thời gian, operator, tool ID, user frame, nguồn tọa độ, ảnh/đo độc lập và kết quả kiểm sai số. Chỉ khi chất lượng hình chữ nhật/mặt phẳng, TCP contact, robot base và camera đều đạt kiểm tra mới coi là hiệu chuẩn vật lý. Sau khi bàn dịch chuyển, invalidate phiên bản cũ và đo lại; việc viewer trùng hình không chứng minh quỹ đạo FR3 thật an toàn.

## Nguồn mã và trạng thái

- `src/domain/board_pose.py`: transform và phiên bản pose bàn.
- `src/domain/board_pose_provider.py`: fit R1–R4 và kiểm hình học.
- `src/simulation/runtime.py`, `src/simulation/physics/world.py`: áp dụng pose trong simulator, kiểm va chạm, cập nhật backend/PyBullet/telemetry.
- `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`: đặt model và nhập/hiển thị điểm.
- `docs/PHASE4_PHYSICAL_VALIDATION_RUNBOOK.md`: checklist commissioning lịch sử; các con số TCP cũ trong đó không phải giá trị đo hiện tại. **Không chạy FR3 thật trong đợt mô phỏng này.**
