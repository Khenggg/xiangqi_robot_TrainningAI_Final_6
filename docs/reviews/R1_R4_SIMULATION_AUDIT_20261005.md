# Kiểm tra áp dụng R1–R4 trong simulation — 2026-10-05

## Kết luận theo phạm vi đã kiểm chứng

Nút **Áp dụng R1–R4** có gửi lệnh và thay đổi backend thật. Bàn, quân, bộ chuyển ô sang tọa độ robot và bridge dùng cùng placement. Áp dụng một vị trí thành công không bảo đảm mọi ô/nước đi tại đó đều có đường đi an toàn.

Nền repo `7d8c5de`; kiểm chứng trong `D:/OJT/_simple_launch_sync_20261005`, có bản sao thay đổi launcher/log chưa commit. Cổng web/backend riêng 8098/8898. Không kết nối camera hoặc FR3 thật. Không thay đổi bàn đang chạy trên cổng 8088.

## Bằng chứng thực thi

- GUI: Connect live với simulator → Vị trí → lấy 4 điểm → sửa X của cả bốn điểm tăng 10 mm → Service/Chuẩn Bị Dời Bàn → Áp dụng. Giao diện báo thành công, RMS 0.00 mm, phiên 1 → 2. Thử khi chưa chuẩn bị bị từ chối, không đổi phiên.
- Đọc trực tiếp 32 rigid body trong PyBullet: cả 32 dịch theo; sai lệch lớn nhất so với vector `[10,0,0]` mm là **0.008823 mm**. Sai lệch nhỏ đến từ settling trong bước chuẩn bị. Không suy ra độ chính xác phần cứng từ con số này.
- GUI kiểm định vị trí đã dịch tại phiên 2: **90/90 LOCAL CELL TRAJECTORIES PASS**; các bộ đếm grasp/approach IK và collision đều 90/90. Mất khoảng 8 phút; UI không hiện tiến độ từng ô trong lúc chạy. Không suy ra 8010 tuyến đều đạt từ kết quả này.
- Trong phiên kiểm định dài có một cảnh báo `TWIN_UNAVAILABLE` về telemetry cũ lúc 14:46:24, sau đó `twin.telemetry_recovered` lúc 14:46:25. Cuối phiên bridge không có lỗi và các authority vẫn dùng cùng placement. Đây là vấn đề cần cải thiện về freshness/polling trong lúc validation; không báo rằng phiên hoàn toàn không có cảnh báo. Log gốc: `ui-session-events.jsonl` trong thư mục bằng chứng.
- GUI áp dụng tiếp bộ điểm xoay **90°** quanh tâm bàn: thành công, phiên 2 → 3, RMS 0.00 mm. Đối chiếu cả 32 body bằng phép quay độc lập: sai lệch lớn nhất **0.026240 mm** sau settling; resolver R1 trả `[146.2,557,10.5]` mm đúng điểm nhập, provider/world/bridge chung state, không có twin fault. Chưa chạy lại toàn bộ 90 ô của phiên 3.
- Runtime/world/provider/bridge chia sẻ cùng state; backend mang placement_version 2, bridge không có lỗi. Target R1 của resolver đổi từ `[156.2,217,10.5]` sang `[166.2,217,10.5]` mm.
- Thử riêng nước tốt đen `(row=3,col=4) → (4,4)` sau cùng phép dịch R1–R4, dùng adapter game và collision guard thực: gắp/đặt thành công. Đo vị trí body **trước reconciliation**: về đúng ô, sai lệch XY **0.152137 mm**. Một nước thành công không chứng minh mọi tuyến.
- `tools/test_fast.ps1 -Workers 2` với `test_sim_board_teaching.py`, `test_merged_placement_and_recovery.py`, `test_motion_resolver.py`, `test_motion_executor.py`: **31 passed**, exit 0. Bao gồm xoay 3°/90°, một tuyến mẫu, từ chối bàn xuyên sàn/cánh tay, bốn điểm sai hình học, phiên cũ và bất biến khi từ chối.
- Node `test_viewer_placement_integrity.mjs`: PASS. `test_viewer_single_motion_authority.mjs` thất bại do fixture đòi `MEASURED_APPROXIMATE` trong khi cấu hình là `MEASURED_PHYSICAL`; cùng lỗi trên worktree sạch của `7d8c5de`. Không sửa production geometry để làm test xanh.

Các số đo và snapshot nằm tại `reports/r1r4-audit-20261005/`: `before.json`, `after-shift.json`, `shift-verification.json`, `actual-pawn-move.json`, `after-validation.json`, `after-rotation.json`, `rotation-verification.json`.

## Truy vết code và giới hạn

| Phần | Vị trí | Kết quả / giới hạn |
|---|---|---|
| GUI và lệnh | `robot-3d-viewer/main.mjs:initPlacementPanelEvents`, handler `board_teaching_result` | Gửi XYZ mm và phiên editor; nhận thành công/từ chối từ backend |
| Calibration và bảo vệ | `src/simulation/runtime.py:apply_board_teaching_points` | Kiểm robot idle, không giữ quân, thế giới ổn định, SERVICE_SAFE mới, hình học và swept collision trước commit |
| Chia sẻ placement | `runtime.py:_commit_board_placement_state`; `hardware_manager.py:initialize_twin` | Đổi world, provider, bridge, backend version và telemetry |
| Bàn và quân vật lý | `src/simulation/physics/world.py:relocate_board_to_state` | Transform cứng cho bàn và quân ổn định; giữ vị trí tương đối với bàn |
| Target gắp và chơi game | `src/motion/resolver.py:_cell_to_pose_mm_deg`; `src/hardware/simulation_adapter.py:_execute_virtual_move` | Tọa độ từ state hiện tại; game adapter gọi runtime pick/place |
| Điểm bỏ quân bị ăn | `simulation_adapter.py:select_capture_slot` | XY theo bàn, Z theo sàn mô phỏng; chưa chơi một nước ăn quân sau R1–R4 trong đợt này |
| Viewer và thước | `main.mjs:applyAuthoritativeBoardPlacement`; `board.mjs:boardPointToXYZ` | Board mesh/cell/ruler nhận matrix; precheck kiểu trục cũ được ẩn trong R1–R4 |
| Kiểm định | `runtime.py:validate_board_placement`, `validate_full_board_routes` | Đọc transform hiện tại. 90 ô là kiểm tra quỹ đạo cục bộ; không tương đương mọi tuyến 8010 cặp ô hoặc cả ván |

Độ tin cậy cao cho phép dịch đã quan sát, đồng bộ 32 body, một nước gắp thực và các trường hợp chạy test. Ăn quân sau xoay bàn, mọi tuyến, mặt bàn nghiêng và FR3 thật chưa được xác nhận toàn diện.

R1–R4 nhận trong phiên runtime; hiện không có thao tác lưu calibration mới xuống file qua nút này. Khởi động lại/reset nominal có thể trở về cấu hình file. R1–R4 là giao lưới trên mặt bàn, không phải mép gỗ hoặc số flange/TCP chưa chuyển đổi.

## Sửa nhỏ trong đợt kiểm tra

- Khóa hai điều khiển H trong chế độ R1–R4 và chặn gọi precheck công thức cũ từ input, vì backend đang giữ H hiện tại và nút áp dụng kiểu trục không được dùng cho pose bốn điểm. Đã mở tab mới trên cùng backend: VER 2, cả ô H và slider disabled, badge vẫn CHƯA KIỂM.
- Probe chạy qua console CP1252 phát hiện lỗi ghi tiếng Việt có thể làm logging tự lặp qua stderr. Thêm console handler tự vô hiệu hóa khi ghi lỗi, giữ file log; regression console encoding và 6 case logging cũ: **7 passed**, exit 0.
- Root DEBUG cũng thu packet DEBUG của thư viện WebSocket khiến file xoay quá nhanh. Đã lọc DEBUG của `websockets.*` trên các handler; vẫn giữ INFO/WARNING/ERROR và DEBUG ứng dụng. Gate cuối logging: **8 passed**, exit 0. `ui-session-events.jsonl` là các sự kiện có cấu trúc và cảnh báo được trích theo thứ tự thời gian từ file phiên và các bản xoay, không phải toàn bộ packet log.
- Kiểm tra cú pháp JS và `git diff --check` đạt. Các sửa này không thay đổi collision margin hay quyền điều khiển robot.
