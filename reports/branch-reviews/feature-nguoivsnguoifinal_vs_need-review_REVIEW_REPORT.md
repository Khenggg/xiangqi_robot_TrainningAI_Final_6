# Review tính năng PvP để tích hợp vào need-review

Ngày kiểm tra: 2026-10-30. **Verdict: DO NOT MERGE nguyên nhánh ở trạng thái đã kiểm tra.**

Nên lấy chọn lọc phần phòng localhost, gán vai Đỏ/Đen và xoay bàn theo vai. Không lấy nguyên luồng robot, camera, commit bàn hay cấu hình phần cứng của donor. Nhánh hiện tại đã có Người vs Người trên một bàn; giá trị bổ sung là hai cửa sổ có vai riêng và đồng bộ qua phòng.

## 1. Đối tượng và nguồn bằng chứng

Target giả định là nhánh đang làm việc `need-review`, kèm kiểm tra tương thích với source chưa commit trên máy. User chưa chỉ định target khác. Đây là giả định được công khai, không phải một target đã được user xác nhận riêng.

| Vai trò | Ref thực tế | SHA |
|---|---|---|
| Target committed | `need-review` | `18e67fc9006a91a2a32c4c861974760089a687de` |
| Donor 1, đã được user xác nhận | `origin/feature/player-vs-player` | `75c1bc9485eafa42aed3b04ffaf1d822b42ef757` |
| Donor 2 | `origin/feature/nguoivsnguoifinal` | `73af0f182d62f39d4e0f7ce66abe488e9b8782e8` |
| Merge base target/donor, cả hai donor | — | `e6bb6323a966727de1a17e57625711b3c2ead0c3` |
| Parent ngay trước tính năng PvP | — | `fb0598d` |
| Commit thêm PvP | — | `93fef3a29da8f39700372b673d3fae96daf2a94b` |

Đã kiểm tra heads của `origin` và `upstream`: không có ref tên chính xác `final/playervsplayer`. Sau khi lập báo cáo, user xác nhận hai nhánh cần xem chính là `feature/player-vs-player` và `feature/nguoivsnguoifinal`. Lựa chọn donor đã được xác nhận; không merge ref nào trong review này. Các SHA và kết quả kiểm tra giữ nguyên.

Mỗi donor có **29 commit riêng**, target có **147 commit riêng** sau merge base. Target hiện có nhiều thay đổi chưa commit và module mới chưa tracked, trong đó có SessionProfile, journal/persistence, fresh-start, FEN diagnostics, F2 cleanup và fixed user-0 profile. Vì vậy kết quả merge của hai committed SHA không đại diện đầy đủ cho source đang vận hành.

Đã fetch hai ref cụ thể; không checkout, reset, cherry-pick, commit, push hoặc merge cây làm việc. Production source không được sửa trong review. SHA-256 của tám file runtime trọng yếu trước/sau kiểm tra giữ nguyên; trạng thái và hashes lưu tại [metadata.json](pvp-20261030/metadata.json).

## 2. Hai nhánh thực sự khác nhau thế nào

`feature/player-vs-player` kết thúc bằng `75c1bc9 Revert "feat: add local two-player Xiangqi mode"`. `git diff fb0598d origin/feature/player-vs-player` rỗng: ở tip này tính năng PvP đã bị gỡ hoàn toàn. Không có tính năng PvP còn hiệu lực để lấy từ tip đó.

`feature/nguoivsnguoifinal` xuất phát từ cùng commit PvP `93fef3a`, rồi thêm `73af0f1`. Phần mới so với `fb0598d` gồm 6 file, 1.299 dòng thêm/36 dòng bỏ:

- `player_vs_player.py`: controller PvP độc lập, 1.122 dòng; phòng qua socket loopback và registry trong thư mục temp; giao diện chủ/khách, vai Đỏ/Đen, xoay bàn; chế độ robot và test gắp/thả.
- `main.py`, `src/ui/board_renderer.py`: entry point và màn hình VS NGƯỜI.
- `src/hardware/hardware_manager.py`, `src/hardware/robot_VIP.py`, `src/ui/input_handler.py`: bổ sung log mismatch và lỗi kết nối/controller.

**Không có test PvP mới được thêm trong hai commit tính năng này.** Bản diff từ merge base còn bao gồm hàng chục thay đổi visual/setup kế thừa từ nhánh cũ, không được tính là toàn bộ giá trị PvP mới.

## 3. Kết quả mô phỏng merge

Chạy `git merge-tree --write-tree` với các ref đã chốt, không sửa working tree:

| So sánh | Exit | Kết quả |
|---|---:|---|
| HEAD + feature/player-vs-player | 1 | 32 file có conflict |
| HEAD + feature/nguoivsnguoifinal | 1 | 32 file có conflict |
| feature/player-vs-player + feature/nguoivsnguoifinal | 1 | modify/delete conflict tại `player_vs_player.py` |

Các conflict trọng yếu gồm `main.py`, `config.py`, `src/core/game_state.py`, `src/core/visual_move_coordinator.py`, `src/hardware/hardware_manager.py`, `src/hardware/robot_VIP.py`, `src/ui/input_handler.py`, `src/ui/board_renderer.py`, `src/vision/camera_monitor.py`, runner/setup và các file visual-pick.

Lấy cả hai nhánh theo thứ tự không giải quyết được vấn đề: một nhánh xóa đúng module mà nhánh kia đang sửa. Không dùng chiến lược chọn toàn bộ `theirs` để xử lý conflict.

Output nguyên bản: [player vs HEAD](pvp-20261030/player_vs_head.merge-tree.txt), [final vs HEAD](pvp-20261030/final_vs_head.merge-tree.txt), [hai donor](pvp-20261030/between_donors.merge-tree.txt). Các tree chứa conflict do Git tạo chỉ là dữ liệu phân tích, không phải bản tích hợp dùng được.

## 4. Các phát hiện chặn lấy nguyên luồng robot

Các vị trí `player_vs_player.py` và robot/manager bên dưới là source **donor 73af0f1**, được giữ nguyên trong [snapshot](pvp-20261030/final/). Khi nói "current", vị trí thuộc source chưa commit trên máy được hash trong metadata.

### F1 — BLOCKER / HIGH: entry point PvP dùng startup cũ tự enable, điều khiển gripper và HOME trước camera

**Vị trí:** donor `player_vs_player.py:L741-L764`, `L1102-L1122`; donor `src/hardware/hardware_manager.py:L71-L90`; donor `src/hardware/robot_VIP.py:L99-L134`.

Click tạo phòng robot gọi `_initialize_robot_hardware()`, chạy `_init_robot()` trước `_init_camera()`. `_init_robot()` gọi `connect()` rồi HOMECHESS. `connect()` tự gọi `RobotEnable(1)`, `Mode(0)`, ghi gripper và hai thao tác mở/thu ngàm. Không có bước enable riêng theo session/telemetry/camera của target.

**Nguồn gốc:** entry point PvP mới đưa thêm consumer của startup cũ. Hành vi tự enable/HOME trong lớp legacy là **PRE-EXISTING trên donor parent**, không quy toàn bộ nội dung đó cho commit `73af0f1`. Đối với target, chọn implementation legacy khi giải conflict sẽ tái đưa hành vi này vào thay cho kết nối read-only hiện tại.

**Kịch bản/tác động:** tạo phòng có thể energize/gripper/HOME trước khi camera sẵn sàng; mất các cổng activation hiện có. Target đang dùng explicit enable và fixed user-0 profile, không được thay bằng startup donor.

**Kiểm chứng:** mock SDK tái hiện chính hàm donor `connect()` gọi enable/mode và hai lệnh gripper. Không kết nối hay vận hành FR3 thật. Toàn chuỗi UI→startup được kiểm tra tĩnh nên confidence tổng thể HIGH.

**Sửa trước tích hợp:** dùng session startup/activation hiện tại; tạo phòng chỉ tạo dữ liệu/transport. Robot authority do HardwareManager hiện tại quản lý. Test cần chặn mọi SDK write trước explicit activation, kể cả khi camera lỗi hoặc người chơi thoát phòng.

### F2 — HIGH / VERIFIED: đi thẳng vào robot, cho phép thiếu target và bỏ kiểm chứng giữa các bước ăn quân

**Vị trí:** donor `player_vs_player.py:L879-L887`, `L1032-L1041`; donor `src/hardware/robot_VIP.py:L766-L800`, `L813-L841`, `L627-L652`.

PvP dùng `get_visual_pick_targets()` rồi gọi `hardware.robot.move_piece()` trực tiếp. API lấy target cho phép trả `None`; lời gọi không truyền `require_visual_target=True`, không truyền callback kiểm tra quân bị ăn đã được dọn và callback lấy lại tâm quân nguồn. Donor `move_piece()` mặc định `require_visual_target=False`, nên nhánh fallback tâm ô vẫn chạy; sau khi bỏ quân địch không bắt buộc quét lại nguồn.

**Nguồn gốc:** **INTRODUCED BY PvP path** (consumer mới); khả năng fallback của helper là legacy có sẵn. Không có lỗi này trong luồng guarded hiện tại chỉ vì helper legacy vẫn tồn tại.

**Kịch bản/tác động:** mất ảnh hoặc không có tâm đáng tin vẫn dispatch; sau ăn quân có thể dùng target trước khi dọn quân. Lời gọi cũng bỏ qua manager lock, telemetry/stop gates, execution binding và move identity của target. Low-level target vẫn có một số guard riêng; điều đó không thay thế các gate bị bỏ qua ở manager.

**Kiểm chứng:** mock xác nhận PvP gọi robot khi target `None`; chính `move_piece()` donor chạy cả hai lượt pick capture/source với target `None` khi tất cả phương thức cơ học được mock. Không có chuyển động thật.

**Sửa:** chuyển yêu cầu phòng thành lệnh semantic qua coordinator/executor hiện tại; full-board precheck, target bắt buộc, capture-clearance và source-refresh giữ nguyên. Test missing-target, stale-frame, capture-removed, stop và calibration-change phải chặn dispatch hoặc phục hồi đúng stage.

### F3 — HIGH / VERIFIED: cập nhật bàn/lượt trước khi camera xác nhận, lại giữ truth ở một LocalRoom riêng

**Vị trí:** donor `player_vs_player.py:L897-L910`, `L923-L980`, `L1066-L1078`; `LocalRoom:L202-L215`.

Sau khi lời gọi robot trả về, code gán `room.board = expected_board`, đổi turn/game-over trước khi quét hậu kiểm. Nếu cả ba mẫu không khớp, `physical_sync=False` nhưng bàn và lượt đã đổi. `LocalRoom` giữ riêng board/turn/pending retry trong RAM, không đi qua GameState/journal/commit/projection của target. Kết quả trả về của `move_piece()` cũng không được kiểm tra `success`.

**Nguồn gốc:** **INTRODUCED BY PvP implementation**; không phải bằng chứng rằng GameState hiện tại gặp cùng lỗi.

**Kịch bản/tác động:** lỗi camera tạo trạng thái màn hình đi trước bàn thật; đóng ứng dụng làm mất pending retry. Khi ghép với API trả structured rejection của target, một kết quả bị từ chối có thể bị xử lý như đã hoàn thành. Mô hình này không giữ được các bảo đảm fresh-start/recovery và lịch sử thực thi hiện tại.

**Kiểm chứng:** mock camera luôn trả bàn trước nước đi: cả ba lần nhận diện đều thấy board đã đổi và lượt đã là Đen; cuối hàm board vẫn đổi dù physical_sync false. Probe riêng tái hiện structured rejection bị bỏ qua.

**Sửa:** chỉ commit qua GameState sau execution result thành công và hậu kiểm; lưu pending intent, stage và receipt vào journal. Transport chỉ gửi projection từ committed truth. Test postcheck fail/timeout/restart phải bảo toàn pending và không commit hai lần.

### F4 — HIGH / VERIFIED: verifier PvP yếu hơn chuẩn FEN của target

**Vị trí:** donor `player_vs_player.py:L914-L950`; donor `src/hardware/hardware_manager.py:L837-L878`.

Verifier riêng chỉ cần `success` và board bằng expected, cộng đủ 2/3 mẫu. Không kiểm `quality_ok`, confidence, timestamp/frame identity hoặc hai mẫu liên tiếp. Mẫu 1 khớp, mẫu 2 lỗi, mẫu 3 khớp vẫn mở khóa. Đối soát recovery của donor cũng cộng số mẫu khớp thay vì giữ chuỗi xác thực có provenance như target.

**Nguồn gốc:** **INTRODUCED BY PvP-specific verifier**; cách đếm recovery legacy là **PRE-EXISTING helper** được donor tiếp tục dùng.

**Kịch bản/tác động:** frame cũ/lặp, confidence bằng 0 hoặc chất lượng không đạt vẫn có thể được chấp nhận; lấy nguyên code sẽ làm yếu chuẩn FEN hiện tại thay vì giải quyết nguyên nhân startup FEN.

**Kiểm chứng:** cung cấp hai kết quả có cùng frame identity, timestamp cũ, `quality_ok=False`, confidence 0, xen giữa một mẫu thất bại: donor vẫn đặt physical_sync true và xóa retry pending. Camera hoàn toàn mock.

**Sửa:** dùng verifier và board_diagnostics hiện tại, không duy trì verifier PvP riêng. Thêm case match/fail/match, duplicate, stale, low-confidence, sanity failure và deadline.

### F5 — HIGH / VERIFIED: chuyển động/nhận diện chặn luồng giao diện

**Vị trí:** donor `main.py:L147-L153`, `L196-L201`; donor `player_vs_player.py:L287-L300`, `L614`, `L661-L700`, `L842-L981`, `L983-L1064`.

`poll_remote()` và `handle_event()` chạy trong main loop. Cả hai gọi `_perform_move()` đồng bộ; hàm gọi robot, baseline, ba lần camera và sleep trước khi trả về. Pick test và retry cũng tương tự. Chỉ scan phục hồi test gắp là đã chuyển sang thread.

**Nguồn gốc:** **INTRODUCED BY PvP path**.

**Kịch bản/tác động:** khi robot/network/camera chờ lâu, Pygame không xử lý F2/QUIT hay vẽ lại; có nguy cơ tái hiện kiểu cửa sổ Not Responding người dùng vừa gặp. Không gọi đây là nguyên nhân đã chứng minh của ảnh chụp cũ vì ảnh đó thuộc source/phiên khác.

**Kiểm chứng:** giả lập chuỗi click nguồn/đích: `move_piece` chạy trên đúng thread gọi handler. Không đo thời lượng robot thật; Windows Not Responding chỉ là hệ quả control-flow có confidence HIGH, không phải tái hiện native UI trong review này.

**Sửa:** dùng MotionWorker/startup worker, kết quả trả bằng queue/token; việc đóng/chuyển chế độ dùng SessionDisposal và controlled stop hiện tại. Test UI vẫn pump events khi fake robot bị giữ và không dispatch sau close.

### F6 — HIGH / VERIFIED: module donor chưa tương thích capability/API của source hiện tại

**Vị trí donor:** `player_vs_player.py:L686-L692`, `L1107-L1122`.

**Vị trí current:** `src/core/session_profile.py:L40-L57`; `src/hardware/hardware_manager.py:L32-L51`, `L1131-L1159`, `L345-L381`.

Target định nghĩa HUMAN_VS_HUMAN là virtual, AI/robot/camera disabled, input BOTH_PLAYERS; khi chọn PHYSICAL cho mode này, cấu hình đã resolve DRY_RUN true. `_initialize_robot_hardware()` donor sẽ từ chối ngay. Ngoài ra donor gọi `execute_pick_place_test(source,destination)` trong khi current yêu cầu keyword-only `move_context` và trả MotionExecutionResult, không phải GridTarget có col/row/confidence.

**Nguồn gốc:** **SEMANTIC INTEGRATION CONFLICT**, không quy là standalone donor sai chỉ vì khác contract của target.

**Kiểm chứng:** test mode hiện tại xác nhận Hvh vẫn virtual; gắn đúng method current vào fake hardware rồi chạy handler donor: bị khóa test với TypeError thiếu `move_context`. Không sửa DRY_RUN để lách capability.

**Sửa:** giữ Hvh local đang có; nếu cần hai người ra lệnh cho FR3, thêm capability/profile rõ nghĩa cho chế độ đó và dùng API semantic hiện tại. Test đủ tổ hợp local PvP, phòng PvP không robot, phòng PvP dùng robot, HvR và RvR trước tích hợp.

### F7 — MEDIUM / VERIFIED: vòng đời phòng chưa đóng/mở đúng và client mất kết nối vẫn tự đi tiếp

**Vị trí:** donor `player_vs_player.py:L338-L343`, `L766-L802`, `L804-L840`, `L847-L856`; branch same-window path `L789-L796`.

`_back_to_menu()` đóng socket/hardware nhưng không xóa `self.room`. Lần join phòng khác đi vào nhánh so mã phòng cũ thay vì đọc registry/connect. Khi client bị disconnected, code chỉ đặt room_client=None; room.joined_black vẫn true. Ở mode local, người Đen còn có thể click đi quân và `_perform_move()` xử lý như host, tự commit bàn riêng. Nhập lại mã trong cùng cửa sổ còn không đổi player_side khỏi Đỏ; chuyển TAB Đen rồi click bị chặn.

**Nguồn gốc:** **INTRODUCED BY PvP lifecycle**.

**Tác động:** không thể đổi phòng bằng một số đường UI, hoặc hai cửa sổ lệch bàn sau mất kết nối; lời hướng dẫn hai tab trong cùng cửa sổ không khớp quyền nhập hiện tại.

**Kiểm chứng:** ba probe riêng tái hiện stale room, same-window Black bị khóa, và commit offline sau disconnect. Loopback host/client transport cơ bản vẫn hoạt động.

**Sửa:** state machine phòng rõ ràng; reset room/role/pending khi leave; trạng thái disconnected không có quyền commit; reconnect có session ID/revision và snapshot authoritative. Chọn rõ sản phẩm dùng hai cửa sổ hay hai người chung một cửa sổ để điều chỉnh UX/test.

## 5. Tính năng nên lấy và phần nên giữ nguyên

| Tính năng/phần code | Quyết định | Cách tích hợp |
|---|---|---|
| Tạo/vào phòng bằng mã, chủ Đỏ/khách Đen | **Nên lấy ý tưởng và phần transport sau sửa lifecycle** | Tách service phòng; host dùng GameState hiện tại làm truth |
| Xoay bàn theo vai, chuyển đổi click/view | **Nên lấy** | View orientation không thay đổi tọa độ logic/robot |
| Màn hình chờ, trạng thái kết nối, hiển thị vai | **Nên lấy** | Ghép vào launcher/session flow hiện tại, không thay toàn bộ main.py |
| Hai người chung một bàn không robot | **Giữ implementation current** | Đã có Hvh + BOTH_PLAYERS và các test mode |
| Hai người chọn nước, một FR3 thực hiện cả hai bên | **Chỉ tích hợp sau khi sửa F1–F6** | Ai chọn nước và ai thực hiện nước là capability tách biệt; không tạo robot owner thứ hai |
| Retry phân loại bàn trước/sau | **Giữ coordinator current** | Mở rộng theo session/move ID; giữ partial-capture recovery |
| Log FEN expected/observed | **Giữ diagnostics current** | Đã có lý do, confidence, frame provenance và diff từng ô; chỉ bổ sung room_id/side nếu cần |
| Test gắp/thả trong module PvP | **Không copy** | UI hiện tại đã có isolated test board + move_context |
| robot_VIP.py/hardware_manager.py donor | **Không thay nguyên file** | Bảo toàn explicit enable, stop, telemetry, binding, worker, fixed user-0 |
| config/calibration/CAMERA npz | **Không lấy** | Donor có DRY_RUN=False và margin 10mm; máy hiện tại dùng env defaults an toàn, margin 6mm và profile user-0 đã chọn |
| Setup/visual-pick inherited | **Không merge kèm PvP** | Current đã có các luồng này được mở rộng; nếu cần thay riêng phải review riêng |
| Commit revert 75c1bc9 | **Không lấy** | Không đem lại tính năng yêu cầu và xóa module PvP |

**Giới hạn phòng hiện có:** host và client đều cố định `127.0.0.1`; port được tra trong registry temp của cùng máy. Đây là phòng giữa hai process/cửa sổ **trên cùng máy**, không phải phòng LAN/Internet hoặc điện thoại chỉ nhập mã là vào. Là giới hạn thiết kế hiện có, không tự gán thành lỗi nếu nhu cầu chỉ là localhost.

## 6. Thứ tự tích hợp đề nghị

1. Chốt/snapshot trạng thái runtime chưa commit thành baseline tích hợp riêng; không merge vào working tree đang bẩn và không đánh mất các bản sửa ngày 30/10.
2. Lấy service phòng và view orientation vào nhánh tích hợp; giữ local Hvh current hoạt động. Sửa leave/rejoin/disconnect trước. Thêm room/session ID, board revision, move ID, side/turn validation và chống replay ở host.
3. Mọi yêu cầu nước đi đi qua GameState/coordinator hiện tại; socket không sửa board/FEN trực tiếp. Project state đã commit ra client và viewer.
4. Nếu phạm vi yêu cầu có FR3, bổ sung profile dành cho hai người chọn nước nhưng robot thực hiện; AI false, robot execution có explicit activation. Camera, robot và disposal dùng cùng owner hiện tại; không gọi private `_init_robot()` từ PvP.
5. Kiểm thử local room end-to-end, disconnect/rejoin/replay; rồi mock toàn chuỗi robot/capture/FEN/restart/F2. Chạy regression tích hợp khi có bản tích hợp thật. Phần cứng chỉ kiểm tra trong tác vụ có ủy quyền riêng.

Đây là kế hoạch port chọn lọc, chưa phải branch đã merge hay patch production. Không cherry-pick mù `93fef3a` hoặc `73af0f1`: cả hai gắn với main/UI/API cũ và cần thay đổi contract như trên.

## 7. Bằng chứng thực thi và giới hạn

**Môi trường:** Windows, Python 3.12.10 trong `.venv312`, pytest 9.1.1, xdist 3.8.0. Đã đọc pytest.ini và project runners; dùng workflow fast-testing. Thread caps do runner thiết lập; hardware tests bị loại. Gate kiểm chứng cuối theo skill code-review, không dùng lời tuyên bố của donor làm bằng chứng.

Lệnh thứ nhất, PATH ưu tiên `.venv312/Scripts`, `PYTEST_ADDOPTS=-x`:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests reports/branch-reviews/pvp-20261030/test_donor_pvp_review.py,tests/unit/test_session_modes.py,tests/unit/test_game_modes_review.py,tests/unit/test_session_user_flows.py
```

**PASS, exit 0:** 55 parallel + 1 serial = 56, trong 16,08 giây theo runner. Gồm 45 test current mode/user-flow và phiên bản đầu 11 donor probe. Warnings websockets deprecation, không có test fail.

Sau khi thêm hai probe SDK/capture, chỉ chạy lại phạm vi donor:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests reports/branch-reviews/pvp-20261030/test_donor_pvp_review.py
```

**PASS, exit 0:** 12 parallel + 1 serial = 13, trong 8,87 giây theo runner. [Output](pvp-20261030/donor-probes-output.txt), [command/result](pvp-20261030/donor-probes-result.json), [probe source](pvp-20261030/test_donor_pvp_review.py).

**Cách đọc PASS:** 11 probe xác nhận hành vi lỗi thực sự xảy ra; 2 probe xác nhận local two-turn/orientation và socket loopback join/state/move hoạt động. PASS của probe lỗi không phải approval, không chứng minh donor an toàn. Có tổng 45 test current + 13 probe khác nhau; hai lượt chạy có probe trùng nhau.

| Phạm vi | Trạng thái |
|---|---|
| Metadata/ref/revert và mô phỏng conflict | VERIFIED |
| Source của hai commit PvP và direct dependencies nêu trên | Reviewed |
| Logic defect, current mode contract, loopback transport | Runtime verified bằng mocks/loopback |
| Native UI freeze thực tế và hiển thị mọi màn PvP | NOT RUN; control-flow static + same-thread probe |
| Full inherited visual/setup changes 29 commit | Chỉ kiểm tra phạm vi tích hợp/config; chưa audit toàn bộ từng thuật toán |
| Source donor chạy nguyên ứng dụng standalone | NOT RUN để tránh legacy auto-enable/HOME |
| CI của exact donor SHAs | NOT AVAILABLE trong review này; không suy từ local tests |
| Regression của bản merge | NOT RUN; chưa tồn tại bản merge và còn conflict |
| Real FR3/camera, enable, gripper, chuyển động | NOT RUN; không có lệnh phần cứng |

Graph MCP được dùng để định vị/trace các boundary current, rồi đọc source chính xác. Graph vẫn có bản baseline trong reports và metadata cũ. `detect_changes(scope=all,depth=1)` trả 797 changed files/0 impacted symbols; đó là drift toàn checkout so với graph, không phải blast radius riêng của review. Không dùng con số này làm chứng cứ an toàn; review chỉ thêm report/probe và ghi nhận trạng thái, không sửa runtime.

## 8. Merge gates và quyết định

| Gate | Trạng thái | Lý do |
|---|---|---|
| Correctness | FAIL | Commit-before-verify, lifecycle/disconnect |
| Regression safety | FAIL | Old main/session/API không tương thích current |
| Tests | FAIL | Không có donor feature tests; probe tái hiện defects |
| CI | UNKNOWN | Chưa có exact-head CI evidence |
| Architecture | FAIL | LocalRoom truth/robot owner riêng, bỏ coordinator |
| Vision integrity | FAIL | Nonconsecutive/quality/freshness gates bị thiếu |
| Coordinate integrity | UNKNOWN | Không thay/kiểm commissioning donor; view flip phải chỉ nằm ở presentation |
| Robot safety | FAIL | New entrypoint đi vào legacy auto-enable/HOME và direct dispatch |
| Configuration compatibility | FAIL | DRY_RUN/capabilities/target margin/profile khác |

**Kết luận: DO NOT MERGE nguyên nhánh.** Dùng `feature/nguoivsnguoifinal` làm nguồn tham khảo cho tính năng phòng và góc nhìn theo vai. `feature/player-vs-player` không còn tính năng PvP ở tip. Giữ nguyên các bản sửa FEN/fresh-start/F2/fixed user-0/worker và authority đang có; sửa các gate/lifecycle trên trong một bản port chọn lọc rồi mới xét merge.
