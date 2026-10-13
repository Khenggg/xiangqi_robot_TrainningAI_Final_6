# BRANCH TECHNICAL AUDIT REPORT — 09/10/2026

**Review Branch:** `origin/feature/visual-correction-v2`

**Review SHA:** `fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09`

**Target Branch:** `feature/unified-robot-vs-robot`

**Target SHA:** `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e`, kèm thay đổi working tree được phân tích riêng.

**Merge Base:** `e6bb6323a966727de1a17e57625711b3c2ead0c3`

**Ahead / Behind:** visual-only 26 / target-only 145 commit. Snapshot working source `da703237561c5264d96886514852bd958e613409`; chỉ là object phân tích với parent target, không cập nhật nhánh/index chính.

## Tóm tắt và phán quyết

**DO NOT MERGE** đối với merge nguyên nhánh/ghi đè nguyên file vào dự án hiện tại. Có giá trị để **tích hợp chọn lọc sau lựa chọn của người dùng và sửa adapter**.

Nhánh visual bổ sung hình học mặt trên quân, consensus theo mm, calibration camera, height sampling, worker, retry, hover, colored-ring và biên gắp ngoài lưới. Tuy nhiên đường thực thi của donor là robot legacy; thiếu hợp đồng typed result, world/identity/simulation và full-board verification mà target hiện tại đang dùng. Thông số vật lý và camera cũng khác.

Phiếu quyết định: [VISUAL_V2_INTEGRATION_CHOICES_20261009.md](../../docs/VISUAL_V2_INTEGRATION_CHOICES_20261009.md). Chưa có lựa chọn nào được tự xem là phê duyệt.

## Phạm vi diff và xung đột

- Primary diff: `git diff HEAD...fe3faa8` (từ merge-base), 64 file.
- Delta mới sau lần tích hợp chọn lọc trước: `git diff 652af26..fe3faa8`, 19 commit / 54 file / 4.930 insertions, 151 deletions. Hai commit merge trong nhóm 19 không phải hai tính năng mới độc lập.
- Tip-to-tip và source working tree được đối chiếu riêng: không quy khác biệt do target phát triển thành lỗi do visual đưa vào.
- `git merge-tree --write-tree HEAD fe3faa8`: exit 1, 10 file conflict. Lệnh không merge vào checkout.
- Merge-tree với snapshot gồm tracked working changes và untracked source/docs/tests: exit 1, **17 file conflict**.
- Snapshot bỏ reports, .codex untracked và ignored assets/profile. Chỉ mô phỏng xung đột source, không phải bản runtime đầy đủ hoặc đã tích hợp.
- `inventory.py` còn dùng merge-file độc lập để tạo 29 ứng viên hunk conflict; số 29 không thay cho 17 conflict do Git merge-tree, vì xử lý add/delete và line endings khác nhau.

### 17 file Git yêu cầu resolve khi tính working source

```text
.codex/session-data/last-state.md
config.py
docs/geometry-measurement.md
main.py
requirements.txt
scripts/measure_geometry.py
src/core/game_state.py
src/hardware/hardware_manager.py
src/hardware/robot_VIP.py
src/ui/board_renderer.py
src/ui/debug_dashboard.py
src/ui/input_handler.py
src/ui/measurement_client.py
src/vision/camera_monitor.py
tests/test_center_pick_no_fallback.py
tests/test_geometry_measurement.py
tests/test_measurement_client.py
```

Không có conflict chữ vẫn chưa đủ: RUN.bat/lock, calibration được commit, flags fallback và quan hệ actor/commit có thể merge sạch nhưng đổi hành vi.

## Đường đi đã truy vết

Donor: camera_source → CameraMonitor fresh/raw frame → resolver center/height/top/ring → GridTarget → visual_move_coordinator → FR5Robot.move_piece → MoveCart/Tool DO → verify nguồn/đích → caller commit pending AI.

Target: camera → strict measured target và full-board verification → game MoveContext/identity → execute_ai_move/execute_piece_move → Resolver/Executor hoặc simulation runtime → camera xác nhận expected board → commit → twin/world/telemetry/viewer.

Graph của main và donor đã dùng architecture/search/trace. Donor index fast được khởi tạo tại worktree; lời gọi index chờ lâu và orchestration bị dừng, sau đó `get_architecture` xác nhận graph donor có 4.020 nodes, 14.156 edges. Graph là công cụ định vị, kết luận dựa trên source đúng SHA.

## Findings trọng yếu

### [HIGH] Đường legacy tiếp tục sau SDK status khác 0

- **Origin:** PRE-EXISTING trong donor base `652af26`; các tính năng mới tiếp tục dùng đường này. Không quy việc chấp nhận 112 cho commit mới.
- **Confidence:** VERIFIED với SDK/camera Mock; HARDWARE UNVERIFIED.
- **Location:** donor `src/hardware/robot_VIP.py:346-364`, `384-400`; `src/hardware/hardware_manager.py:608-638`; `src/core/visual_move_coordinator.py:80-88`.
- **Evidence/current behavior:** MoveCart trả 112 vẫn được wrapper trả về như mã cho phép; các stage pick/place không kiểm tra giá trị. Probe exact donor: 7 motion trả 112, gripper CLOSE/OPEN/CLOSE_TO_SAFE_GAP tiếp tục sau lỗi đầu, manual test trả GridTarget khi camera verify Mock trả True. Chỉ SDK Mock, không mở RPC thật. Main contract `tests/unit/test_physical_architecture_closure.py:139-165` yêu cầu chỉ 0 là success.
- **Expected/impact/failure scenario:** khi motion thất bại, không được đóng kẹp/hạ/đặt tiếp hoặc báo motion thành công; callback camera giả/dữ liệu gây false positive không được biến thất bại SDK thành hoàn tất.
- **Suggested fix:** giữ typed executor, kiểm tra mã/kết quả từng stage; ghép target/retry mới vào luồng đó. Không thay bằng coordinator legacy dựa hoàn toàn vào exception.
- **Test needed:** inject 112 và mã nonzero tại từng stage; khẳng định không có motion/gripper tiếp theo, không commit, latch recovery phù hợp; cùng trường hợp capture sau removal.

### [HIGH] Thay nguyên config/entrypoint làm mất hợp đồng khởi động và tham số hiện tại

- **Origin:** PRE-EXISTING `DRY_RUN=False` của donor; INTRODUCED BY DONOR DELTA cho tuning mới; nguy cơ hồi quy phát sinh từ cách tích hợp.
- **Confidence:** HIGH/static.
- **Location:** donor `config.py:39-135`, `main.py`; target `main.py`, `src/core/launch_options.py`, config runtime backend/calibration.
- **Evidence/current behavior:** donor mặc định live, camera 0/640×480, SAFE_Z 220, speed 50, rotation `[180,0,-73.2]`, xung close .2s; target VIRTUAL/DRY_RUN, speed 70 và calibration/activation gate riêng. Donor RUN gọi entrypoint legacy; config có nhiều bộ board/height khác nhau.
- **Expected/impact/failure scenario:** giữ CLI game/sim/physical và read-only startup của target; đổi thông số phải dựa trên profile phù hợp. Ghi đè config/main có thể đổi startup hoặc mất tùy chọn viewer/ports/logging.
- **Suggested fix:** additive config và profile ứng viên; người dùng chọn C06/C07, không tự kích hoạt physical. Giữ nguồn BoardPoseProvider/scene geometry hiện tại.
- **Test needed:** startup default/--virtual/physical read-only, port conflict, profile thiếu/mismatch, bảo toàn board/version và tool.

### [MEDIUM] Fallback legacy xung đột với strict center đã tích hợp

- **Origin:** INTRODUCED BY DONOR DELTA (`2d097a1` restore fallback), cấu hình quyết định đường chạy.
- **Confidence:** HIGH/static.
- **Location:** donor `hardware_manager.py:455-504`, target resolver cùng tên.
- **Evidence/current behavior:** routing ưu tiên ring, top-face, height. Height mặc định True nên **không chạy fallback**. Khi height/top/ring tắt, thiếu/tâm không ổn định chuyển sang foot-point, còn target hiện tại dừng.
- **Expected/impact/failure scenario:** tắt height vì chưa calibration có thể vô tình đổi strict center thành foot fallback nếu lấy nguyên resolver.
- **Suggested fix:** giữ strict center; legacy fallback chỉ thành một lựa chọn tường minh nếu người dùng chọn C03=B.
- **Test needed:** ma trận flags, thiếu estimator/frame/tâm, không fallback giữa các mode đang yêu cầu hình học khác nhau.

## Điểm chính sách/tích hợp, không kết luận là lỗi donor

- Height aggregation loại None và cần tối thiểu hai mẫu hợp lệ; có thể lấy hai mẫu tốt trước đó khi quan sát cuối None. Probe xác nhận semantics này; **không đủ bằng chứng gọi là stale-sample bug**. Top/ring consensus dùng điều kiện latest-supported chặt hơn. Khi ghép cần ghi rõ sampling policy và tests, không đổi ý nghĩa âm thầm.
- Coordinator donor kiểm tra `turn == b`, phù hợp pending AI đen của donor. Target có robot-vs-robot hai actor: cần adapter, không coi đây là lỗi trong use case gốc.
- Donor verify riêng source/destination; target full-board identity trước/sau. Giữ kiểm tra target và thêm measurement/capture checkpoint của donor.
- Xung mở thêm OPEN_MAX/CLOSE_TO_SAFE_GAP trước mỗi pick trong `fb857d5` là thay đổi thao tác thật. Chỉ ghép sau khi kiểm tra payload/gripper state; không pulse lúc đang giữ quân và không áp timing thử nghiệm như geometry kẹp.
- Calibration intrinsics camera0 được commit không chứng minh đúng camera/lens của người dùng. Loader kiểm tra index/resolution, không nhận dạng serial/lens/focus. Dữ liệu này là ứng viên, công cụ calibration mới là phần có thể tái sử dụng.
- Lock Windows thiếu `pybullet` và `websockets`; SETUP import smoke chỉ vision/game. Ghép dependency của stack thay vì thay môi trường bằng lock donor. Chưa thử cài fresh Python 3.12.
- `VISUAL_PICK_OUTSIDE_MARGIN_MM=10` là admission limit trong estimator, không collision clearance và không thay vị trí R1–R4; trajectory guard phải tiếp tục hoạt động.
- Worker mới và cleanup join cần ghép vào ownership/epoch/telemetry hiện tại; chưa kiểm chứng SDK bị treo hoặc cleanup worker ngoài đời.

## Kiểm chứng thực thi

Worktree donor detached: `D:/OJT/_visual_review_fe3faa8`, SHA `fe3faa8`. Không chạy main/camera/SDK thực. Copy **trusted runner từ main** vào worktree vì donor không có tools/test_fast.ps1; source/test donor giữ nguyên.

| Lệnh/check | Exit | Kết quả |
|---|---|---|
| `git fetch origin` | 0 | Visual `652af26 → fe3faa8` |
| `git merge-tree --write-tree HEAD fe3faa8` | 1 | Conflict mong đợi, không phải lỗi test |
| `python .../snapshot_compare.py` | 0 | Snapshot/index riêng; merge-tree nội bộ exit 1 / 17 conflicts |
| `tools/test_fast.ps1 -Workers 2 -Tests <12 files> -ParallelOnly` | 0 | **168 passed, 200 subtests passed**, 2 deprecation warnings |
| `python .../probe_donor.py` với PYTHONPATH donor | 0 | Counterexample motion112 và semantics height aggregation |

Test list và nguyên lệnh/đầu ra: `../visual-preintegration-20261009/donor-tests.log`. Includes top-face geometry, consensus/retry, height geometry/sampling, hover, ring, camera-open, outward compensation, center fallback, gripper, manual test and estimator. Tests là phần lớn fixture/image synthetic/SDK Mock; không phải physical acceptance hay system test của bản merge chưa tồn tại.

Probe đầu exit 1 do gọi sai chữ ký constructor (`dry_run`); đã sửa harness dùng constructor đúng và SDK Mock. Source donor không sửa để làm pass. Probe cuối và call trace: `donor-probe.json`, `donor-probe.log`.

## Merge gates

| Gate | Trạng thái | Ghi chú |
|---|---|---|
| Correctness donor tính năng vision được chọn test | PASS có phạm vi | 12 test files; không phủ mọi luồng |
| Textual integration | FAIL | 17 conflicts với working source |
| Regression safety / architecture | FAIL nếu merge nguyên nhánh | Executor/identity/launcher/GUI khác |
| Vision integrity | UNKNOWN physical | Synthetic/mock đã chạy, optics thật chưa |
| Coordinate/calibration integrity | UNKNOWN | Bộ thông số/profile chưa chốt |
| Robot safety | FAIL với legacy path theo contract target | Probe motion nonzero tiếp tục stage |
| Config/dependency compatibility | FAIL nếu thay nguyên | Profile, default và dependency khác |
| CI exact visual SHA | UNKNOWN | Không thu checks remote cho SHA này |

## Coverage và bước tiếp theo

**Reviewed:** diff inventory/commit history/config/runtime seams, camera acquisition, target selection, sampling, capture/commit/retry, legacy motion status, wizard và setup entrypoints; graph/main source ownership.

**Runtime verified:** 12 donor test modules và hai counterexamples đọc/mocks; merge conflict simulation bằng Git; không phải integrated runtime.

**Static only:** camera/calibration lifecycle, raw-frame locks, GUI/worker ownership, tuning/defaults, dependency installer, phần thuật toán image geometry đối chiếu tests.

**Hardware unverified:** camera thật, optical calibration, R1–R4 thực, tool/rotation/pulses, hover/motion/gripper, retry sau physical removal. Không truy cập `192.168.58.2`.

**Not reviewed/executed:** fresh Windows setup, long soak, integrated system/GUI sau merge, full regression, CI, robot commissioning, mọi thuật toán ở mọi ảnh/quỹ đạo. Không đọc các tài liệu tương lai đang được đánh dấu không áp dụng.

Người dùng chọn ở phiếu trước; sau đó mới ghép trong worktree, giữ tests/regression hiện có và thêm tests mới tương thích kiến trúc. Không cherry-pick hàng loạt vì một số commit mới thuộc các nhánh đã merge, source cũ đã được port chọn lọc và chưa commit.
