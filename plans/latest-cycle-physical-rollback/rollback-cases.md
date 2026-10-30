> Historical design: rollback has been removed. This document does not describe the current runtime.

# Cases rollback: đối chiếu spec với feature/visual-correction-v2

Ngày: 2026-10-28. Đây là phân tích thiết kế, không phải báo cáo các case đã
được triển khai hoặc chạy trên arm thật.

Source hiện tại có logical rollback một checkpoint, không có latest_cycle,
pending_rollback, cycle_id, rollback journal hay coordinator tự trả quân.
`GameState.handle_rollback()` thay FEN ngay rồi yêu cầu xếp lại bàn thật;
không được dùng nguyên handler này cho thiết kế physical rollback mới.

Quy ước: Rsrc/Rdst = nguồn/đích Đỏ; Bsrc/Bdst = nguồn/đích Đen;
S0 = trước Đỏ, S1 = sau Đỏ, S2 = sau Đen. Một lần Z thành công hoàn tác cả
cycle S2→S0, chỉ cycle mới nhất. Thông thường Đỏ trước; Bdst=Rsrc thì Đen trước.

## A. Cases bàn cờ trong một cycle hoàn tất

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

## B. Cases được hoặc không được nhấn Z

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

## C. Cases đặt lại quân bị ăn và xác minh

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

## D. Cases lỗi, checkpoint, pause và resume

| ID | Tình huống | Hành vi thiết kế |
|---|---|---|
| D01 | Camera/geometry/nhận diện lỗi trước bước đầu | Không motion, không commit; giữ cycle và báo lỗi |
| D02 | Gắp không thành công, bàn còn checkpoint trước | Controller phải idle; người dùng retry mới đo lại và chạy bước chưa thực hiện |
| D03 | Arm chuyển quân rồi response mất | Không gửi lại; fresh controller state + full-board proof quyết định bước đã xong hay chưa |
| D04 | Xong bước đầu, bước thứ hai lỗi | Không chạy lại bước đầu; giữ checkpoint và khóa normal play |
| D05 | Quân rơi/đặt nhầm hoặc có thay đổi lạ, không khớp checkpoint nào | Không suy đoán; yêu cầu phục hồi bàn bằng tay đến checkpoint rõ ràng |
| D06 | RPC/controller lỗi 112, safety fault, DO chưa LOW hoặc trạng thái realtime cũ | Giữ recovery lock; không motion mới, không commit sớm |
| D07 | Hủy trước motion | Nếu full board vẫn S2 có thể trả READY; không mất quyền vì một preflight fail |
| D08 | Hủy sau khi đã di chuyển một phần | Chỉ pause; hoặc tiếp tục tới S0, hoặc player phục hồi S2 rồi verified-abort. Không mở chơi ngay |
| D09 | Đóng app/crash giữa rollback | Giữ journal, không tự end room; mở lại recovery đúng checkpoint và committed state |
| D10 | Physical S0 đã verified và commit, nhưng baseline lỗi | COMMITTED_WAIT_BASELINE: chỉ rebuild baseline, không replay arm/commit/FEN event |
| D11 | Mạng lỗi hoặc server từ chối FEN rollback | Giữ local S0 đã xác minh, báo remote pending/rejected; không chạy arm để chữa API |
| D12 | Request S2 cũ đang gửi khi rollback xong | Gửi theo revision/worker order; không cho S2 cũ tới sau S0 |
| D13 | Job AI/camera result của epoch cũ trả về muộn | Bỏ result; không phát nước mới hoặc ghi đè rollback checkpoint |
| D14 | Phục hồi đủ rồi normal auto-confirm nhìn thấy các thay đổi đảo nước | Rollback scanner không được gọi normal human commit; không mở một AI reply ngoài ý muốn |

## E. Những khoảng trống trong source hiện tại

1. `src/core/game_state.py:196`: chỉ có `_pre_space_state`, chưa có cycle ledger
   S0/S1/S2, latest-cycle eligibility hoặc journal. `handle_rollback():213`
   commit board/FEN và queue remote trước khi bàn thật được hoàn tác.
2. `src/ui/input_handler.py:754`: SPACE lưu rollback trước khi biết có nước hợp
   lệ. SPACE/no-move có thể ghi đè checkpoint. Đây khác hẳn yêu cầu B11.
3. `src/ui/input_handler.py:568` và renderer: Z nối thẳng logical handler;
   chưa có gate “chỉ sau cycle máy đã xong”, disabled reason hay log transaction.
4. `src/core/visual_move_coordinator.py`: chỉ cấp quyền pending AI turn Đen;
   không phải coordinator rollback hai màu. Không được đổi turn giả để tái sử dụng.
5. `src/hardware/hardware_manager.py:808`: full-board verifier hiện trả bool và
   dùng count khớp; cần mismatch theo ô và gate liên tiếp theo thời gian cho
   preflight/checkpoint/final. Không đủ để báo chính xác C03–C05 bằng UI hiện tại.
6. `main.py:_cleanup_all`: bình thường gọi end_match(OTHER); cần rollback-aware
   close để D09 không tự đóng room đang có transaction dở.
7. Chưa có COMMITTED_WAIT_BASELINE hoặc marker idempotent cho D10; FEN outbox
   hiện tại lưu đồng bộ HTTP, không lưu bước arm/rollback transaction.
8. `move_log` hiện là log nước đi đi theo snapshot; chưa có audit append-only
   đánh dấu hai nước đã hoàn tác và các bước physical/manual như spec.
9. API bên ngoài chưa được xác minh chấp nhận undo FEN; chưa thể coi D11/D12 là
   online acceptance đã đạt dù local outbox có thứ tự.

## F. Độ ưu tiên kiểm thử khi triển khai

- P0: A02, A06/A07, D03/D04, D06, D10, D13/D14 — sai xử lý có thể gắp sai,
  replay motion, commit sai board hoặc tạo AI reply ngoài ý muốn.
- P1: các case còn lại về eligibility, capture restoration, mismatch, pause và
  startup/close recovery; tất cả phải có kiểm tra offline trước commissioning.
- Acceptance thật: camera/controller/gripper, bốn biên/góc, ảnh bị che, đặt tay,
  mất kết nối và API undo phải xác minh riêng. File này không phải bằng chứng
  các case đã chạy pass trên phần cứng hoặc provider thật.

## G. Kiểm tra tính khả thi bằng luật cờ hiện tại

Đã dùng `src/core/xiangqi.py` của checkout hiện tại, seed cố định 20261028,
lấy mẫu 13 thế bàn và xét 4.106 cycle hợp lệ chưa kết thúc ván. Với mỗi cycle,
mô phỏng các phép chuyển quân đảo theo thứ tự đã chọn, rồi phục hồi các victim
theo ledger. Cả 4.106 trường hợp đều trở lại chính xác S0; mỗi đích arm đều trống
trước khi chuyển. Đây là kiểm tra toán học trong bộ nhớ, không gọi production
rollback handler, camera, SDK/arm hoặc provider.

| Nhóm cycle | Số trường hợp được xét |
|---|---:|
| Không bên nào ăn | 3.621 |
| Đỏ không ăn, Đen ăn quân Đỏ khác | 168 |
| Đỏ ăn, Đen không ăn | 287 |
| Cả hai ăn, Đen ăn quân Đỏ khác | 17 |
| Đỏ không ăn, Đen ăn chính quân Đỏ vừa đi | 11 |
| Đỏ ăn rồi Đen ăn lại quân Đỏ đó | 2 |

Thứ tự có 4.061 cycle Đỏ→Đen, 32 cycle cần Đen→Đỏ do Bdst=Rsrc, và 13 cycle
chỉ có quân Đen để arm trả về vì quân Đỏ đã bị ăn. Mẫu này chứng minh cả sáu
nhóm capture và ngoại lệ thứ tự đều có thể xuất hiện theo luật hiện tại; không
chứng minh đã bao phủ mọi thế cờ có thể đạt tới hoặc mọi lỗi thiết bị.

Dữ liệu:
[rollback-case-enumeration-20261028.json](D:/Projects/xiangqi_robot_TrainningAI_Final_6/outputs/reviews/2026-10-14/rollback-case-enumeration-20261028.json).
