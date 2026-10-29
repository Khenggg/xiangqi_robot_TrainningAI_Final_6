# Plan: Rollback vật lý cycle Đỏ–Đen gần nhất

Date: 2026-10-28
Branch: `feature/visual-correction-v2` — checkout local có các sửa lỗi đã stage
Status: **Đã triển khai và kiểm chứng offline; chờ nghiệm thu phần cứng/provider thật**
Mode: bb-plan Hard; triển khai theo TDD sau khi người dùng xác nhận
Risk: high-risk — thay đổi quyền phát motion, state/FEN, recovery và API undo

## 1. Phạm vi xác nhận

Một lần nhấn Z hoàn tác **toàn bộ cycle gần nhất**: một nước Đỏ và một nước Đen.
Z chỉ mở sau khi máy đã hoàn tất, controller/arm đã nghỉ, bàn và baseline đúng.
Hoàn tác xong không được lùi tiếp cycle cũ; chỉ một cycle mới hoàn tất mới cấp Z.

Luồng đã thống nhất:

1. Lưu state và hai nước của cycle bằng sự kiện commit hợp lệ.
2. Nhấn Z → khóa nhận nước mới/AI, kiểm tra lại toàn bàn và controller.
3. Đo tâm thực tế, arm trả quân Đỏ về trước, Đen về sau.
4. Nếu Đen đang chiếm ô cũ của Đỏ: trả Đen trước rồi Đỏ, không dùng ô đệm.
5. Quân đã bị ăn không được arm gắp từ bãi ăn: player đặt lại đúng quân/ô được chỉ dẫn.
6. Camera xác minh toàn bàn; sai/thiếu/chưa nhìn rõ thì báo cụ thể và tiếp tục khóa.
7. Toàn bàn đúng mới commit state/FEN, cập nhật log, tạo lại baseline và mở lượt Đỏ.
8. Lỗi giữa chừng thì giữ checkpoint, đối soát để resume, không gắp lại bước đã xong.

Đây là plan triển khai hợp nhất. Toàn bộ 44 case và giải pháp nằm ngay trong
file này; `spec.md` và `rollback-cases.md` là tài liệu nguồn đối chiếu.

## 2. State và các quy tắc không được phá

- Giữ ba snapshot bất biến: S0 trước Đỏ, S1 sau Đỏ, S2 sau Đen. Cycle lưu
  nguồn/đích, màu/loại quân, victim của từng nước, FEN, lượt, captured inventories,
  history prefix, cycle_id, epoch và revision.
- Capture metadata phải lấy **trước khi mutate board**. Tạo cycle chỉ sau commit
  hợp lệ; SPACE/poll thất bại không được ghi đè snapshot hoặc quyền rollback.
- Chỉ seal READY sau verified Black move + controller idle/arm parked +
  full-board S2 + baseline S2 thành công. Black commit đơn thuần chưa đủ.
- Một nước Đỏ mới được commit thu hồi quyền cycle trước. Emergency/test không
  được tạo cycle rollback vật lý; đường Emergency Đỏ cần phân biệt với normal
  `process_human_move()` dù hiện dùng chung hàm.
- Rollback giữ main board/FEN ở S2 trong phần di chuyển. Các expected checkpoint,
  target S0 và observed board nằm riêng. Không biến một ảnh scan thành state mới.
- Nhận dạng màu/loại/ô bằng layout và đo tâm thật bằng visual geometry. Mọi
  transfer rollback có `capture=False`, đích trống, không dùng bãi ăn, không
  chọn một quân cùng loại khác để thay quân đã mất. Không dùng luật đi tiến để
  chặn phép đảo tốt về ô cũ đã được ledger cấp quyền.
- Chỉ **một** transaction active, gắn cycle/epoch/signature; giữ GUI live,
  khóa normal AI/auto-confirm/test/Emergency/New Game làm đổi state trong lúc dở.

## 3. Thứ tự arm và quân bị ăn

Rsrc/Rdst là nguồn/đích nước Đỏ; Bsrc/Bdst là nguồn/đích nước Đen.

| Tình huống | Arm chuyển quân | Player phục hồi |
|---|---|---|
| Không ăn quân | Đỏ rồi Đen | Không |
| Đen chặn Rsrc, Đỏ vẫn sống | Đen rồi Đỏ | Victim Đen nếu nước Đỏ đã ăn |
| Đỏ ăn X, Đen không ăn | Đỏ rồi Đen, trừ ngoại lệ chặn Rsrc | X Đen tại Rdst |
| Đen ăn Y khác quân Đỏ vừa đi | Đỏ rồi Đen | Y Đỏ tại Bdst |
| Cả hai ăn, Y không phải quân Đỏ vừa đi | Đỏ rồi Đen | X Đen tại Rdst; Y Đỏ tại Bdst |
| Đen ăn chính quân Đỏ vừa đi | Chỉ đưa Đen về Bsrc | Đỏ tại Rsrc |
| Đỏ ăn X rồi Đen ăn lại quân Đỏ đó | Chỉ đưa Đen về Bsrc | Đỏ tại Rsrc; X Đen tại Rdst |

Mỗi “chuyển quân” là một thao tác gắp/đặt/về nghỉ gồm nhiều RPC, không phải một
lệnh SDK duy nhất. Survivor và victim được suy từ ledger S0/S1/S2, không từ một
label cùng màu/cùng loại đơn lẻ.

## 4. State machine và xác minh

```text
BUILDING → READY
Z → PREFLIGHT → PLAN → TRANSFER_1 → VERIFY_CHECKPOINT
                    → TRANSFER_2 nếu còn → VERIFY_CHECKPOINT
                    → WAIT_PLAYER nếu có victim → FINAL_VERIFY
                    → COMMIT_S0 → BASELINE → DONE/CONSUMED

Lỗi trước commit → PAUSED_FAULT / RECOVERY_REQUIRED
Lỗi baseline sau commit → COMMITTED_WAIT_BASELINE
```

- Preflight, checkpoint và final proof: ít nhất **3 frame mới liên tiếp trong
  ít nhất 1 giây**, toàn bộ 90 ô đúng, không unknown; mismatch reset chuỗi.
  Ngưỡng nhận dạng dùng cấu hình được kiểm chứng, không lấy YOLO confidence
  làm bằng chứng loại quân. Tất cả geometry cùng piece-height plane.
- Trước từng pick: quét lại source đúng quân và đích trống, đo tâm mới, xác minh
  calibration/offset/confidence, rồi mới cho arm chạy. Sau transfer: arm parked,
  kiểm tra lại toàn bàn đúng expected checkpoint trước bước sau.
- WAIT_PLAYER: chỉ các ô trong danh sách restoration được chuyển từ trống thành
  đúng quân S0; các ô khác giữ checkpoint sau arm. Có thể đặt từng quân hoặc
  nhiều quân đúng cùng lúc. Sai ô/sai loại/thêm quân/thay đổi ngoài danh sách
  phải được nêu rõ; ảnh mờ/che khuất là chưa xác minh được, không kết tội gian lận.
- Player chỉ can thiệp khi arm parked/an toàn và DO LOW, ở WAIT_PLAYER hoặc bước
  phục hồi tay được chỉ dẫn. Rút tay rồi SPACE/Quét lại; V đối soát, không bypass.
- Tái sử dụng controller fault latch, timeout transport và fresh-idle proof.
  Timeout/lost ACK/112 không chứng minh một bước chưa xảy ra và không được replay.
- Idle và DO LOW không chứng minh kẹp đã rỗng. Đặc biệt sau lỗi, phải xác nhận
  TCP ở pose parked/an toàn và kẹp không giữ quân trước khi cho retry. Không giả
  định có jaw sensor; nếu pose/quân đang giữ chưa rõ thì cần operator/pendant
  recovery và xác nhận kẹp rỗng, không tự re-pick hoặc mở kẹp làm rơi quân.

## 5. Commit, log và phục hồi

### Commit cuối

Chỉ FINAL_VERIFY thành công mới áp dụng S0: board/FEN, lượt Đỏ, captured
inventories, bộ đếm và active history. Revision tăng dù FEN quay về bố trí cũ.
Journal ghi commit intent/commit_id/authoritative S0/marker idempotent. Tạo đúng
một logical FEN update có commit_id; HTTP retry không phải một lần rollback mới.
Consume cycle, hủy AI authority/result/candidate cũ, không tự phát một nước Đen.

Baseline/arbiter phải được dựng từ ảnh mới đúng S0 trước khi mở chơi. Nếu baseline
lỗi sau commit: COMMITTED_WAIT_BASELINE chỉ thử lại baseline; không arm, không
apply history/capture/commit hoặc thêm logical FEN event lần hai.

### Log và trạng thái UI

- Nút Z có enabled/disabled và lý do; không chỉ vẽ nút luôn hoạt động.
- Hiển thị target S0, highlight source/đích và danh sách victim cần đặt tay.
- Status cùng phong cách thanh AI: “Đang đưa Đỏ về”, “Đổi thứ tự: Đen đang chặn
  ô cũ Đỏ”, “Đặt lại Pháo Đen tại b2”, “b2 cần Pháo Đen nhưng thấy Mã Đen”.
- Audit append-only ghi request/order/started/verified/manual/mismatch/fault/
  resume/done; hai nước cũ đánh dấu đã hoàn tác. Active move history lùi về
  prefix S0; audit không bị xóa và rollback không thành nước Đỏ mới.

### Pause, cancel và restart

- Sau lỗi: fresh controller idle, TCP parked/an toàn, kẹp rỗng đã được xác nhận
  và full-board proof mới phân biệt checkpoint trước/sau bước. Nếu thiếu bằng
  chứng pose/kẹp rỗng, yêu cầu operator/pendant recovery trước, không suy từ DO LOW.
  Bước đã xong thì bỏ qua; bước chưa chạy chỉ retry theo yêu cầu khi controller
  chắc chắn đã dừng. Không khớp checkpoint thì yêu cầu phục hồi tay.
- Hết bước arm thì resume tới WAIT_PLAYER/FINAL_VERIFY, không dựng thêm bước giả.
- Cancel trước motion có thể trả READY nếu bàn vẫn S2. Sau partial motion chỉ
  pause; hoặc hoàn tất S0, hoặc player phục hồi S2 và full-board verified-abort.
  Sau commit S0 không có abort tự quay S2; chỉ hoàn tất baseline/sync.
- Journal atomic lưu trước lệnh và sau proof, gồm room/account scope. Cleanup
  khi transaction dở không tự `end_match(OTHER)` hoặc xóa dữ liệu. Restart vào
  recovery, tải đúng committed S2/S0 theo marker; không INITIAL_FEN, không arm tự chạy.

### Remote FEN

Outbox giữ thứ tự: request S2 đang chạy phải xong trước S0; không stale S2 sau
S0. Remote lỗi chỉ retry dữ liệu, không arm; UI báo pending/rejected riêng.
Khả năng server nhận FEN đi ngược/endpoint rollback chưa được xác minh; nếu
server từ chối vẫn giữ local S0 đã verified và báo lỗi. Không tuyên bố online
acceptance hoặc tự sửa backend ngoài repo chỉ từ test mock.

## 6. Các phase sửa code sau khi xác nhận

| Phase | Công việc | File/phần chính | Điều kiện qua phase |
|---|---|---|---|
| 1 | Cycle ledger, metadata capture, eligibility và seal READY | `game_state.py`, `human_move_commit_coordinator.py`, hook normal Black finalizer; model rollback mới | Snapshot immutable, false SPACE không ghi đè, Z chỉ đúng latest complete cycle |
| 2 | Planner đảo nước, survivor/victim và verifier chi tiết | Module planner mới, `board_reconciler.py`, `hardware_manager.py` | Sáu nhóm capture + conflict order; mismatch theo ô; stable fresh-frame gate |
| 3 | Coordinator physical riêng, worker và manual restore | Module rollback coordinator mới; primitive camera/robot hiện tại | Đỏ→Đen/ngoại lệ Đen→Đỏ; đo trước mỗi bước; không capture-bin, không giả turn Đen |
| 4 | Journal atomic, idempotent commit, cancel/resume/restart | Module journal mới, `game_state.py`, `main.py`, `simulation_client.py` | Lost ACK không replay; COMMITTED_WAIT_BASELINE; cleanup giữ room/journal |
| 5 | Phím/nút Z, highlight, audit log, status và trở lại gameplay | `input_handler.py`, `board_renderer.py`, `main.py` | Một gate chung; lỗi rõ; một commit; baseline mới; không tự chạy AI sau rollback |
| 6 | Kiểm tra tích hợp/regression, review và tài liệu vận hành | `tests/test_rollback*.py`, runner offline, docs | 44 case có trace kiểm chứng; suite cũ không regress; báo rõ giới hạn physical/provider |

TDD theo hành vi ở từng phase: viết test chứng minh lỗi/thiếu tính năng trước,
sửa nhỏ trong phạm vi phase, chạy kiểm tra liên quan rồi tích hợp. Không dùng
test chỉ đếm cấu trúc code hoặc sửa expectation để che regression.

Lệnh kiểm tra offline dự kiến:

```powershell
& .\.venv312\Scripts\python.exe -X utf8 scripts/run_offline_tests.py --pattern 'test_rollback*.py'
& .\.venv312\Scripts\python.exe -X utf8 scripts/run_offline_tests.py
& .\.venv312\Scripts\python.exe -m compileall -q main.py src scripts tests
& .\.venv312\Scripts\python.exe -X utf8 scripts/check_runtime.py
git diff --check
```

HTTP phải được mock/deny trong suite. Test camera/arm dùng mock và synthetic
projections; acceptance trên camera/controller/arm/provider thật là bước riêng,
không tự chạy thiết bị trong phiên lập plan hoặc mặc định coi xác nhận sửa code
là lệnh vận hành arm thật.

## 7. Ma trận 44 case và giải pháp

### A. Cases bàn cờ trong một cycle hoàn tất

| ID | Case | Kế hoạch arm | Cần đặt tay | Điều kiện hoàn tất |
|---|---|---|---|---|
| A01 | Hai nước không ăn, không xung đột | Rdst→Rsrc rồi Bdst→Bsrc | Không | Full board=S0, baseline mới đạt |
| A02 | Đen đang ở Rsrc sau cycle | Bdst→Bsrc rồi Rdst→Rsrc | Theo capture Đỏ nếu có | Đích trống trước mỗi bước; không dùng ô đệm |
| A03 | Đỏ ăn X Đen, Đen không ăn | Đỏ→Đen, hoặc A02 nếu bị chặn | X tại Rdst | X đúng màu/loại, toàn bàn=S0 |
| A04 | Đen ăn Y Đỏ khác quân Đỏ vừa di | Đỏ→Đen | Y tại Bdst | Y đúng màu/loại, toàn bàn=S0 |
| A05 | Đỏ ăn X và Đen ăn Y khác quân Đỏ vừa di | Đỏ→Đen | X tại Rdst, Y tại Bdst | Có thể đặt từng quân hoặc cả hai; chỉ commit khi đủ |
| A06 | Đen ăn chính quân Đỏ vừa di, Đỏ không ăn trước đó | Chỉ Bdst→Bsrc | Quân Đỏ tại Rsrc | Không có pick Đỏ giả hoặc gắp một quân Đỏ khác |
| A07 | Đỏ ăn X rồi Đen ăn lại quân Đỏ vừa ăn | Chỉ Bdst→Bsrc | Quân Đỏ tại Rsrc, X Đen tại Rdst | Hai victim khác nhau; đối chiếu ledger và S0 |
| A08 | Quân ở lệch tâm nhưng vẫn đúng ô và trong giới hạn visual pick | Đo tâm mới trước bước; thực hiện kế hoạch tương ứng | Không nếu không có capture | Geometry cùng piece-height plane, confidence/offset đạt |
| A09 | Camera thấy quân Đỏ/Đen đúng loại nhưng sai ô dự kiến | Chưa phát bước mới | Player sửa theo checkpoint | Không suy đoán một quân cùng loại khác là quân cần gắp |
| A10 | Một đích phục hồi có quân ngoài kế hoạch | Chặn, không bắt quân đó | Player phục hồi đúng checkpoint | Không tự đẩy quân vào bãi ăn hoặc tự đổi state |

Ràng buộc hữu ích: Bdst=Rsrc chỉ có thể là nước Đen **không ăn**, vì sau nước
Đỏ, Rsrc trống. Quân Đỏ vẫn sống trong case này. Nếu Đen ăn chính quân Đỏ vừa
di thì Bdst=Rdst, không phải Rsrc. Black mover luôn sống ở cuối một cycle hợp lệ;
nếu không thấy nó thì đây là mismatch/fault, không phải một case bỏ qua bình thường.

### B. Cases được hoặc không được nhấn Z

| ID | Thời điểm/hành động | Hành vi thiết kế |
|---|---|---|
| B01 | Vừa mở game/chưa có cycle | Z disabled, báo chưa có lượt hoàn tất |
| B02 | Đỏ mới di bằng tay nhưng chưa được xác nhận | Không tự tạo cycle; nếu Z được yêu cầu thì preflight khác S2 sẽ chặn |
| B03 | Đỏ đã commit, AI đang nghĩ | Z disabled; chưa đủ cycle |
| B04 | Máy đã có bestmove nhưng chưa gắp | Z disabled; không lấy pending AI làm cycle hoàn tất |
| B05 | Máy đang ăn/gắp/đặt/về home | Z disabled; không chèn arm job khác |
| B06 | Arm đã đặt nhưng post-check hoặc baseline chưa đạt | Z disabled; tiếp tục normal physical recovery, không seal cycle |
| B07 | Đỏ+Đen hoàn tất, idle, bàn/baseline đúng S2 | Z enabled cho đúng latest cycle |
| B08 | Cycle mới đã commit Đỏ nhưng máy lỗi/chưa xong | Không lùi cycle cũ; phải xử lý cycle hiện tại |
| B09 | Đã rollback thành công, nhấn Z lại | Không lùi thêm cycle trước; báo lượt đã hoàn tác |
| B10 | Nhấn Z liên tiếp khi rollback bắt đầu | Chỉ một transaction; không nhân đôi motion |
| B11 | SPACE sai/no-move hoặc poll nhiễu sau cycle hoàn tất | Không ghi đè cycle S0/S1/S2 hoặc quyền rollback |
| B12 | Test gắp, Emergency chỉnh state, New Game hoặc game over | Không dùng lịch sử giả làm cycle physical hợp lệ; game-over rollback ngoài scope v1 |

### C. Cases đặt lại quân bị ăn và xác minh

| ID | Tình huống | Hành vi thiết kế |
|---|---|---|
| C01 | Chưa đặt quân nào hoặc còn thiếu một quân | Chờ, highlight từng ô còn thiếu; chưa commit |
| C02 | Có hai quân cần phục hồi, đặt đúng cùng lúc | Chấp nhận, không bắt buộc thao tác đúng thứ tự danh sách |
| C03 | Đặt đúng ô nhưng sai màu/loại | Chỉ rõ expected/observed, giữ WAIT_PLAYER |
| C04 | Đặt đúng quân nhưng sai ô | Chỉ rõ ô còn thiếu và ô ngoài danh sách bị thay đổi |
| C05 | Đặt thêm quân hoặc thay đổi quân không thuộc restoration | Báo mismatch ngoài danh sách, không mở chơi |
| C06 | Quân bị tay che, confidence thấp hoặc unknown | Báo chưa xác minh được; không kết luận gian lận |
| C07 | Quân đúng nhưng quá lệch tâm/vượt giới hạn an toàn | Yêu cầu chỉnh tâm, không cho tiếp tục ở vị trí không thể gắp an toàn |
| C08 | Dùng quân khác cùng màu/cùng loại, bố trí hoàn toàn giống | Stack camera hiện tại không phân biệt được ID vật lý; không được hứa chống tráo quân tuyệt đối |

Arm luôn ở vị trí nghỉ khi chờ đặt tay. Camera so sánh toàn bàn: chỉ những ô
trong danh sách restoration được từ trống chuyển thành đúng quân của S0;
mọi ô khác giữ checkpoint sau arm. Nhấn xác nhận không được bỏ qua mismatch.

### D. Cases lỗi, checkpoint, pause và resume

| ID | Tình huống | Hành vi thiết kế |
|---|---|---|
| D01 | Camera/geometry/nhận diện lỗi trước bước đầu | Không motion, không commit; giữ cycle và báo lỗi |
| D02 | Gắp không thành công, bàn còn checkpoint trước | Controller phải idle; người dùng retry mới đo lại và chạy bước chưa thực hiện |
| D03 | Arm chuyển quân rồi response mất | Không gửi lại; fresh controller state, TCP parked, kẹp rỗng được xác nhận + full-board proof quyết định bước đã xong hay chưa |
| D04 | Xong bước đầu, bước thứ hai lỗi | Không chạy lại bước đầu; giữ checkpoint và khóa normal play |
| D05 | Quân rơi/đặt nhầm hoặc có thay đổi lạ, không khớp checkpoint nào | Không suy đoán; xác nhận arm parked/kẹp rỗng rồi phục hồi bàn bằng tay; nếu còn giữ quân cần operator/pendant recovery |
| D06 | RPC/controller lỗi 112, safety fault, DO chưa LOW hoặc trạng thái realtime cũ | Giữ recovery lock; không motion mới/commit sớm; idle+DO LOW chưa đủ nếu TCP/kẹp vẫn chưa xác minh |
| D07 | Hủy trước motion | Nếu full board vẫn S2 có thể trả READY; không mất quyền vì một preflight fail |
| D08 | Hủy sau khi đã di chuyển một phần | Chỉ pause; hoặc tiếp tục tới S0, hoặc player phục hồi S2 rồi verified-abort. Không mở chơi ngay |
| D09 | Đóng app/crash giữa rollback | Giữ journal, không tự end room; mở lại recovery đúng checkpoint và committed state |
| D10 | Physical S0 đã verified và commit, nhưng baseline lỗi | COMMITTED_WAIT_BASELINE: chỉ rebuild baseline, không replay arm/commit/FEN event |
| D11 | Mạng lỗi hoặc server từ chối FEN rollback | Giữ local S0 đã xác minh, báo remote pending/rejected; không chạy arm để chữa API |
| D12 | Request S2 cũ đang gửi khi rollback xong | Gửi theo revision/worker order; không cho S2 cũ tới sau S0 |
| D13 | Job AI/camera result của epoch cũ trả về muộn | Bỏ result; không phát nước mới hoặc ghi đè rollback checkpoint |
| D14 | Phục hồi đủ rồi normal auto-confirm nhìn thấy các thay đổi đảo nước | Rollback scanner không được gọi normal human commit; không mở một AI reply ngoài ý muốn |

## 8. Điều kiện hoàn thành và giới hạn

- Mỗi case trong bảng có test hoặc acceptance mapping cụ thể; ưu tiên conflict,
  recapture, double Z, lost ACK, partial failure, post-commit baseline, crash,
  stale AI và outbox ordering. Không đánh dấu case physical pass chỉ từ mô phỏng.
- Bộ luật hiện tại đã được dùng kiểm tra 4.106 cycle chưa kết thúc ván ở 13 thế
  lấy mẫu: phép đảo đề xuất đều về đúng S0, bao gồm 32 cycle cần Đen→Đỏ và 13
  cycle chỉ trả Đen. Đây là bằng chứng logic trong RAM, không phải implementation
  rollback hay acceptance thiết bị.
- V1 không rollback sau game over/room đã đóng, không undo nhiều cycle, không
  redo tự động, không tự gắp quân ở bãi ăn, không dùng ô đệm.
- Kiểm tra chống đặt sai dựa trên **màu/loại/ô**; không thể xác minh hai quân
  vật lý cùng màu/cùng loại bị tráo nếu không có marker/ID.
- Calibration, nhận dạng, khoảng hở arm, fresh controller status và API undo
  cần acceptance thật trước tuyên bố chức năng đã vận hành đạt trên thiết bị.
- Giữ nguyên README, preview và các file ngoài phạm vi. Không reset/unstage
  hoặc ghi đè các sửa lỗi đã stage từ trước. Không đổi token, weights hoặc
  calibration để làm test pass. Không tự push/deploy.
- Giai đoạn lập plan trước xác nhận chỉ tạo tài liệu; phần triển khai sau xác
  nhận được ghi riêng ở Session Notes dưới đây. Không đổi `feature_list.json`
  vì không có entry tương ứng với các phase này.

## 9. Phê duyệt và bắt đầu

Người dùng đã trả lời **confirm** ngày 2026-10-28. Xác nhận này cho phép triển
khai toàn bộ phase trên branch hiện tại, kiểm tra và review theo từng phần.
Không bao gồm push hoặc phát lệnh vào phần cứng/provider thật để nghiệm thu.

## Session Notes

**Last active:** 2026-10-28
**Phase in progress:** Cả sáu phase source/offline hoàn tất
**Status:** 409 tests pass; compile/runtime preflight/whitespace pass; independent review APPROVE trong phạm vi offline.

- [x] Phase 1: cycle ledger/snapshot/capture metadata và latest-only eligibility.
- [x] Phase 2: inverse planner, restoration và full-board stable measured proof.
- [x] Phase 3: coordinator/worker riêng, checkpoint và manual restore.
- [x] Phase 4: atomic journal, idempotent commit/outbox, restart/read-only recovery.
- [x] Phase 5: Z/buttons, status/target guides, append-only audit, gameplay gates.
- [x] Phase 6: kiểm chứng cuối, review và tài liệu trong phạm vi offline.

### Decisions made this session

- Thêm dấu clean-close để không phục hồi Z/room đã đóng; giữ riêng journal của
  transaction chưa xong. Archive audit trước khi xóa move feed của game cũ.
- Chưa enqueue durable S0 thì khóa nước mới để không ghi đè remote bằng FEN cũ.
- Journal phải có typed metadata, FEN khớp board/lượt/bộ đếm, pending payload
  khớp committed authority và inner/outer cycle khớp nhau.
- Giữ nguyên index sửa lỗi cũ: patch SHA256 trước/sau triển khai trùng nhau.
- Không commit/push, không dùng camera/controller/arm/provider thật.

### Next immediate action

Nghiệm thu với camera/controller/gripper thật và provider trước khi xác nhận
vận hành thực tế. Chưa commit/push.

### Verification evidence

- `scripts/run_offline_tests.py`: **409 tests, OK**, serial run 25.050 giây.
- Trong đó 64 test thuộc `test_rollback*.py`; bao gồm subcase capture/eligibility,
  stale authority, geometry, journal, worker, manual restore và restart.
- `compileall main.py src scripts tests`: exit 0.
- `scripts/check_runtime.py`: Runtime preflight OK, không kết nối camera/robot.
- `git diff --check`: exit 0; chỉ cảnh báo LF/CRLF thông thường.
- Independent review APPROVE: `outputs/reviews/2026-10-28/rollback-code-review.md`.
- UI đã render và xem ảnh preview tổng hợp; không phải camera/hardware acceptance.
- Hai exploratory run khi chạy đồng thời gặp timeout ở fixture engine cũ;
  target engine chạy riêng pass14/14 và serial full suite cuối pass409/409.
  Fixture async rollback luôn release/join worker trước khi dọn temporary journal.
- Mapping 44 case/giới hạn: `verification.md`; không coi 44 case là đã nghiệm
  thu từng case trên phần cứng thật.
