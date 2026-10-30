# Spec: Hoàn tác vật lý cycle Đỏ–Đen gần nhất

**Date:** 2026-10-28
**Status:** Implemented offline; updated user requirement 2026-10-30 below takes precedence.

## Yêu cầu bổ sung 2026-10-30 — chỉ kích hoạt bằng Z

Trước khi nhấn Z, giữ nguyên luồng chơi vsc-v3 và baseline thông thường. Chỉ ghi
S0/S1/S2 và ledger trong RAM lúc commit; không ghi journal rollback mới, quét toàn bàn, kiểm tra controller hay
seal cycle để chuẩn bị Z. Cycle đủ hai nước cho phép yêu cầu Z; kiểm tra an toàn,
baseline rollback và seal READY bắt đầu trong worker sau thao tác Z, trước mọi
motion hoàn tác. Chuẩn bị lỗi được thử lại bằng V/E hoặc hủy X khi chưa có motion.
Journal cũ chưa có coordinator/pending rollback FEN không được kích hoạt recovery
hay thay bàn của ván mới khi mở app. Transaction đã chạy vẫn giữ checkpoint và
phục hồi nghiêm ngặt. Điều này thay thế các mô tả kiểm tra/seal trước Z ở bên dưới.
Sau transaction, nước chơi mới phải lưu việc thu hồi authority cũ một lần để
không khôi phục transaction đã bị thay thế khi mở app lại.

Proof toàn bàn dùng occupancy theo mode gắp đang chọn (PvP: foot/homography;
height/ring: piece-height), không yêu cầu tâm của mọi quân đều gắp được. Target
đo mới trong giới hạn gắp chỉ bắt buộc với quân nguồn trước mỗi transfer. Vẫn giữ
đủ 90 ô đúng loại/màu, confidence, ô trống, ảnh mới và ổn định. Theo yêu cầu người
dùng, confidence layout chấp nhận khi **lớn hơn 0.7**, không chấp nhận bằng 0.7
hay NaN/Inf. Quy tắc này thay thế ràng buộc piece-height cho
mọi mode và safe-pick offset cho mọi quân trong bản đặc tả cũ bên dưới.

---

## Problem Statement

Rollback hiện tại khôi phục một snapshot trong RAM trước nước người chơi và yêu
cầu sửa bàn bằng tay; chưa phải transaction hoàn tác một cycle bằng arm. Cần cho
người chơi nhấn Z sau một cycle đã hoàn tất để arm trả các quân còn trên bàn về
vị trí cũ, hướng dẫn phục hồi quân bị ăn, xác minh toàn bàn rồi mới commit FEN.

---

## User Stories

- **[P1]** Là người chơi, tôi chỉ có thể hoàn tác cycle Đỏ–Đen gần nhất đã hoàn tất.
  Accepted when: Z chỉ mở sau khi nước Đỏ và nước Đen đã commit, arm đã về vị trí
  nghỉ, controller idle, bàn khớp state và baseline đã sẵn sàng. Không được lùi
  sang cycle cũ hơn sau khi hoàn tác hoặc khi cycle mới đang diễn ra.
- **[P1]** Tôi muốn arm tự đưa quân còn trên bàn về: ưu tiên Đỏ trước, Đen sau.
  Accepted when: nếu Đen đang ở ô xuất phát cũ của Đỏ, thứ tự đổi thành Đen trước,
  Đỏ sau theo lựa chọn người dùng; mỗi bước đều đo tâm và xác minh lại.
- **[P1]** Tôi muốn tự đặt lại quân bị ăn mà phần mềm kiểm tra đúng vị trí.
  Accepted when: arm không vào bãi ăn; phần mềm chỉ rõ màu/loại/ô cần phục hồi,
  phát hiện sai ô/sai quân/thay đổi ngoài danh sách và chưa cho chơi khi chưa khớp.
- **[P1]** Tôi muốn biết rollback đang ở bước nào và phục hồi được khi có lỗi.
  Accepted when: log lưu các bước, checkpoint, lỗi và hoàn tất; mất phản hồi
  không tự gửi lại motion; đã di chuyển một phần thì không mở khóa chơi bình thường.

---

## Functional Requirements

1. **FR-01 — Đơn vị rollback là một cycle, không phải một nước đơn.**
   Một cycle gồm đúng một nước Đỏ được chấp nhận và một nước Đen được thực hiện,
   xác minh và commit. Gọi ba bố trí bất biến là S0 (trước Đỏ), S1 (sau Đỏ), S2
   (sau Đen). Mục tiêu rollback luôn là S2 → S0. Hỗ trợ tối đa một cycle khả dụng.
   Các hướng dẫn dưới đây là thiết kế mới, không mô tả chức năng đã triển khai.

2. **FR-02 — Ghi cycle bằng sự kiện commit, không bằng thao tác SPACE/poll.**
   Khi commit Đỏ, tạo cycle BUILDING với S0 và S1, bản ghi nước Đỏ. Khi commit
   Đen sau physical verification, bổ sung S2 và bản ghi nước Đen. Chỉ seal cycle
   thành READY sau khi arm parked/idle, không lỗi, không còn pending motion,
   bàn khớp S2 và baseline S2 đã được cài. SPACE thất bại, ảnh nhiễu và poll không
   có nước mới không được ghi đè S0 hoặc tạo cycle. Emergency/pick-test/DRY_RUN
   không tự tạo quyền rollback vật lý.

3. **FR-03 — Dữ liệu cần lưu.**
   Mỗi cycle có cycle_id, game_epoch, revision, S0/S1/S2, FEN tương ứng, lượt và
   bộ đếm trước cycle, captured inventories, hai bản ghi lịch sử và phần log.
   Mỗi nước ghi side, nguồn, đích, loại quân di chuyển, tham chiếu quân logic,
   quân bị ăn hoặc null, ô quân bị ăn, trạng thái physical verification.
   Tham chiếu logic được lấy từ ledger; không khẳng định là ID nhận diện vật lý.
   Transaction rollback ghi transaction_id, cycle_id, chữ ký snapshots, kế hoạch
   có thứ tự, checkpoint đã xác minh, danh sách cần đặt tay, phase và lỗi.

4. **FR-04 — Điều kiện nút Z.**
   Nút hiển thị “HOÀN TÁC LƯỢT — Z”, enabled chỉ khi latest cycle READY, vẫn là
   cycle gần nhất, đến lượt Đỏ, game đang chơi, không busy/thinking/pending/retry,
   không manual override/test hoặc physical fault. Disabled phải có lý do như
   “Chờ máy đi xong”, “Chưa có lượt hoàn tất”, “Arm đang xử lý”, “Lượt này đã hoàn tác”.
   Nhấn phím khi disabled cũng hiện lý do, không im lặng chạy fallback cũ.
   Nếu đã xác nhận một nước Đỏ mới, quyền cycle trước bị thu hồi ngay, dù máy
   chưa trả lời xong. Khi người chơi mới di tay nhưng chưa commit, preflight phát
   hiện bàn khác S2 và từ chối Z; không tự lấy trạng thái đó làm baseline.

5. **FR-05 — Nhấn Z chỉ tạo một transaction.**
   Ghi log `ROLLBACK_REQUESTED`, khóa điều khiển làm đổi state, dừng auto-confirm
   người chơi và AI scheduling, vô hiệu hóa job AI cũ bằng generation/epoch.
   Giữ board/FEN đã commit là S2; dùng rollback_target=S0 và expected_board riêng
   cho các bước trung gian. Không dùng lại handle_rollback hiện tại để commit
   S0 ngay, và không đổi turn giả thành Đen để gọi AI motion coordinator.

6. **FR-06 — Preflight trước motion đầu tiên.**
   Xác nhận controller kết nối, idle và không có completion unknown; gripper
   outputs LOW; homography/intrinsics/height geometry hợp lệ. Quét ảnh mới và
   đòi bố trí đầy đủ khớp S2, không ô unknown/thiếu/sai quân. Đánh giá cả kế hoạch
   và thứ tự, các đích cần trống và tồn tại của quân nguồn trước khi chạy.
   Không lấy ảnh cache/diagnostic làm bằng chứng. Bàn thay đổi phải báo expected
   và observed theo ô, không tự chỉnh FEN để hợp thức hóa.
    Preflight và mỗi checkpoint dùng cùng gate ít nhất ba frame mới liên tiếp,
    trải ít nhất một giây như FINAL_VERIFY; một ảnh đúng riêng lẻ không đủ.

7. **FR-07 — Tính các quân sống sót từ ledger.**
   Quân Đen thực hiện nước cuối cycle phải còn trên bàn; nếu không thấy, dừng.
   Quân Đỏ di chuyển còn sống trừ khi chính nó là quân bị nước Đen ăn. Khi Đen
   ăn quân Đỏ vừa đi, bỏ bước arm gắp Đỏ và đưa nó vào danh sách đặt tay tại nguồn
   Đỏ trong S0. Không gắp một quân Đỏ cùng loại khác để thay thế quân đã mất.

8. **FR-08 — Chọn thứ tự, bao gồm quyết định đã chốt của người dùng.**
   Gọi Rsrc/Rdst là nguồn/đích nước Đỏ, Bsrc/Bdst là nguồn/đích nước Đen.
   - Đỏ sống và Rsrc trống: arm Rdst → Rsrc, rồi Bdst → Bsrc.
   - Đỏ sống và Bdst == Rsrc: arm Bdst → Bsrc trước để giải phóng Rsrc;
     sau đó Rdst → Rsrc. Ghi rõ lý do đổi thứ tự trong log/status.
   - Đỏ đã bị ăn: arm chỉ Bdst → Bsrc; Đỏ được phục hồi bằng tay sau đó.
   - Bất kỳ đích nào bị một quân ngoài kế hoạch chiếm hoặc bố trí không khớp
     checkpoint: dừng, không bịa ô đệm hoặc đẩy quân khác vào bãi ăn.
   Đây là đảo các thao tác được cycle cấp quyền, không phải một nước cờ tiến
   mới; không dùng luật đi tiến để từ chối tốt lùi về ô cũ.

9. **FR-09 — Transaction thực thi và xác minh từng bước.**
   State machine:

   ```mermaid
   flowchart TD
     A[READY: cycle gần nhất hoàn tất] -->|Z| B[PREFLIGHT: bàn khớp S2, controller idle]
     B --> C[PLAN: Đỏ–Đen hoặc Đen–Đỏ khi bị chặn]
     C --> D[Đo mới tâm và xác minh quân/đích của bước kế]
     D --> E[Arm gắp, đặt, về vị trí nghỉ]
     E --> F[Quét toàn bàn: khớp expected checkpoint]
     F -->|Còn bước arm| D
     F -->|Đã hết bước arm| G{Có quân cần phục hồi tay?}
     G -->|Có| H[WAIT_PLAYER: arm nghỉ, chỉ rõ quân và ô]
     H --> I[Player đặt quân, rút tay, xác nhận quét]
     I -->|Thiếu quân| H
     I -->|Sai quân/ô hoặc ô khác bị thay đổi| J[Báo mismatch, giữ khóa chơi]
     J --> H
     I -->|Đủ và đúng| K[FINAL_VERIFY: toàn bàn bằng S0]
     G -->|Không| K
     K --> L[COMMIT S0, ghi log rollback, đồng bộ FEN, tạo baseline]
     L -->|Baseline thành công| M[CONSUMED: đến lượt Đỏ, Z khóa]
     L -->|Baseline thất bại| O[COMMITTED_WAIT_BASELINE: chỉ thử lại baseline]
     O -->|Baseline mới đúng S0| M
     B -->|Lỗi| N[PAUSED_FAULT]
     D -->|Lỗi| N
     E -->|Lỗi| N
     F -->|Không khớp| N
     K -->|Không khớp| N
     N --> Q[Đối soát controller và checkpoint]
     Q -->|Còn bước arm được cấp quyền| D
     Q -->|Đã hết bước arm| G
     Q -->|Chưa xác định được checkpoint| N
   ```

   Trước mỗi bước, xác minh danh tính màu/loại/ô bằng layout và đo tâm thật bằng
   pipeline visual pick hiện tại. Chiếu về cùng piece-height plane như picking.
   Đích phải trống. Gọi thao tác chuyển quân với capture=False: rollback không
   dùng chu trình ăn quân hoặc bãi ăn. Sau mỗi bước arm về nghỉ rồi xác minh
   toàn bàn theo expected checkpoint, chưa commit FEN chính.

10. **FR-10 — Danh sách phục hồi quân bị ăn.**
    Sau tất cả bước arm, dừng ở WAIT_PLAYER và hiển thị target S0 cùng highlight
    các ô cần đặt. Danh sách gồm đúng các quân bị ăn trong hai nước:
    - Đỏ đã ăn quân Đen X: phục hồi X tại Rdst.
    - Đen đã ăn quân Đỏ Y, Y không phải quân Đỏ vừa đi: phục hồi Y tại Bdst.
    - Đen đã ăn chính quân Đỏ vừa đi: phục hồi quân Đỏ đó tại Rsrc.
    Mỗi entry có màu, loại quân, tọa độ đọc được như a6, tình trạng chưa đặt/đúng/sai.
    Một cycle có tối đa hai entry. Chỉ cho người chơi can thiệp khi arm parked;
    rút tay và bấm “Đã đặt / Quét lại” hoặc SPACE để xác minh. V cũng đối soát,
    không phát motion mới trong phase chờ đặt tay.

11. **FR-11 — Ma trận xử lý ăn quân.**

    | Hai nước trong cycle | Arm hoàn tác | Người chơi phục hồi |
    |---|---|---|
    | Không ăn quân | Đỏ rồi Đen; nếu Bdst=Rsrc thì Đen rồi Đỏ | Không |
    | Đỏ ăn X; Đen không ăn | Đỏ rồi Đen, có ngoại lệ xung đột như trên | X Đen tại Rdst |
    | Đỏ không ăn; Đen ăn Y khác quân Đỏ vừa đi | Đỏ rồi Đen | Y Đỏ tại Bdst |
    | Cả hai ăn; Đen ăn Y khác quân Đỏ vừa đi | Đỏ rồi Đen | X Đen tại Rdst; Y Đỏ tại Bdst |
    | Đen ăn chính quân Đỏ vừa đi, Đỏ trước đó không ăn | Chỉ đưa Đen về Bsrc | Đỏ tại Rsrc |
    | Đỏ ăn X rồi Đen ăn lại quân Đỏ đó | Chỉ đưa Đen về Bsrc | Đỏ tại Rsrc; X Đen tại Rdst |

    Vị trí phục hồi dựa trên S0 và ledger; không mặc định quân bị ăn luôn được
    đặt ở đích nước Đen. Khi Đỏ đã bị ăn thì không có thao tác gắp Đỏ giả.

12. **FR-12 — Đối chiếu trong WAIT_PLAYER.**
    Gọi P là checkpoint sau arm, M là tập ô được phép bổ sung quân.
    Với mọi ô ngoài M, observed phải đúng bằng P. Với ô trong M, chỉ chấp nhận
    trống hoặc đúng quân yêu cầu của S0. Chấp nhận người chơi đặt một hoặc nhiều
    quân đúng cùng lúc; còn thiếu thì tiếp tục chờ. Đặt sai màu/loại/ô, đặt thêm
    quân hoặc di chuyển quân khác phải nêu rõ từng mismatch và giữ khóa.
    Unknown/che khuất/độ tin cậy thấp là “chưa xác minh được”, không kết luận gian
    lận. Lần quét tiếp theo có thể sửa lỗi; nút xác nhận không được bỏ qua kiểm tra.

13. **FR-13 — Xác minh cuối.**
    Toàn bộ 90 ô phải khớp S0, không unknown, dựa trên ít nhất ba frame mới liên
    tiếp trải trên ít nhất một giây; mismatch reset chuỗi. Áp dụng ngưỡng nhận
    diện màu/loại đã commissioning; không dùng confidence YOLO như bằng chứng
    loại quân. Các quân mới đặt phải nằm trong vùng ô và ngưỡng lệch tâm hợp lệ
    của pipeline visual pick hiện tại, kể cả quy tắc margin ở biên.

14. **FR-14 — Commit và trở lại chơi.**
    Chỉ sau FINAL_VERIFY mới thay board/FEN/captured inventories và bộ đếm bằng
    snapshot S0, cập nhật UI và queue đúng một FEN rollback mới. Khôi phục lượt Đỏ,
    không tạo nước AI đáp lại rollback. Tạo lại baseline/arbiter từ ảnh mới đúng
    S0, xóa candidates cũ, pending/retry AI cũ; consume toàn bộ quyền AI thuộc
    cycle vừa hoàn tác. Chỉ mở chơi khi baseline mới thành công. Snapshot cũ
    không được dùng để mở khóa nếu camera chưa xác minh được.
    Thành công đánh dấu cycle CONSUMED, Z disabled. Chỉ một cycle Đỏ–Đen mới
    hoàn tất mới cấp quyền Z tiếp theo; không được lấy cycle cũ hơn từ log.
    Commit có commit_id bền/idempotent: journal chứa commit intent, authoritative
    snapshot S0 và marker đã áp dụng. Outbox dùng cùng logical commit_id để
    không tạo thêm một lần cập nhật chỉ vì recovery chạy lại; HTTP retry của
    cùng bản ghi vẫn được phép. Nếu baseline thất bại sau commit, chuyển riêng
    COMMITTED_WAIT_BASELINE: authoritative state đã là S0, cycle đã consumed,
    vẫn khóa play và chỉ xây lại baseline/arbiter. Không chạy lại arm, không
    apply lịch sử/captured inventories hoặc tạo logical FEN update lần hai.

15. **FR-15 — FEN remote và revision.**
    Revision đồng bộ luôn tăng dù FEN quay về bàn cũ và move counter nhỏ hơn.
    Outbox tuần tự phải bảo đảm request S2 đang chạy kết thúc trước request S0;
    không gửi một FEN S2 cũ sau S0. Lỗi remote chỉ retry đồng bộ dữ liệu, không
    replay arm. UI phân biệt “Bàn đã phục hồi; FEN máy chủ đang chờ đồng bộ”.
    Việc server nhận FEN đi ngược hoặc hỗ trợ endpoint rollback cần acceptance
    riêng trước khi tuyên bố đồng bộ online đầy đủ. Không giả định API FEN hiện
    tại chắc chắn chấp nhận undo; nếu từ chối, giữ local S0 đã xác minh và báo
    lỗi remote rõ ràng, không thay local theo server hoặc gửi motion để chữa lỗi.

16. **FR-16 — Log và trạng thái.**
    Giữ log append-only. Hai nước cũ được đánh dấu “đã hoàn tác”, không xóa khỏi
    audit. Thêm nhóm `ROLLBACK cycle_id` gồm requested, plan/order, từng bước
    started/verified, missing/manual placement, mismatch, fault/resumed và done.
    Không gọi rollback thành một nước Đỏ mới trong move_history dùng cho luật/AI.
    Active move_history khôi phục prefix S0; audit log giữ bằng chứng rollback.
    Sau hoàn tất, log ví dụ:
    `↶ Đã hoàn tác lượt #12: Đỏ a6→a5; Đen a3→a4. Đến lượt Đỏ.`
    Trong UI luôn có phase và progress, dùng cùng phong cách thanh trạng thái AI.

17. **FR-17 — Thông báo lỗi bắt buộc.**

    | Tình huống | Nội dung mẫu / tác động |
    |---|---|
    | Máy chưa xong cycle | “Chờ máy hoàn tất lượt; chưa thể hoàn tác.” |
    | Đổi thứ tự do xung đột | “Quân Đen đang chặn ô a6; sẽ đưa Đen về trước, rồi Đỏ.” |
    | Không thấy nguồn đúng | “Không xác nhận được Tốt Đỏ tại a5; chưa phát lệnh.” |
    | Đích bị chiếm ngoài kế hoạch | “Ô a6 cần trống nhưng đang có Xe Đen; hãy kiểm tra bàn.” |
    | Đang chạy | “Rollback 1/2: đưa Tốt Đỏ a5 → a6.” |
    | Cần đặt tay | “Đặt lại Pháo Đen tại b2, rút tay rồi bấm Quét lại.” |
    | Sai quân | “b2 cần Pháo Đen; camera đang thấy Mã Đen.” |
    | Sai ô | “Quân cần tại b2 còn thiếu; phát hiện thay đổi ngoài danh sách tại c2.” |
    | Chưa rõ ảnh | “Chưa nhìn rõ b2; chờ ảnh ổn định, chưa xác nhận.” |
    | RPC mất phản hồi | “Chưa biết arm đã hoàn tất bước nào; không tự chạy lại. Kiểm tra controller rồi V.” |
    | Hoàn tất | “Đã hoàn tác lượt gần nhất; đến lượt Đỏ.” |

18. **FR-18 — Lỗi giữa chừng, resume và cancel.**
    Mỗi bước có started và verified checkpoint lưu bền. Một lỗi motion/inference
    hoặc nonzero controller status chuyển PAUSED_FAULT. Không gửi lại một lệnh
    chỉ vì timeout. Sau khi controller idle và outputs LOW được xác minh bằng
    phản hồi mới, quét toàn bàn để phân loại: còn ở checkpoint trước bước, đã ở
    checkpoint sau bước, hoặc không thuộc checkpoint nào. Đã ở sau bước thì ghi
    nhận verified và bỏ qua bước đó. Ở trước bước thì chỉ cho retry khi không
    còn command đang chạy và người dùng yêu cầu. Không khớp thì yêu cầu phục hồi
    bằng tay, không tự suy đoán. Resume sau khi hết bước arm phải đi WAIT_PLAYER
    hoặc FINAL_VERIFY, không phát một bước arm không tồn tại.
    Cancel trước motion có thể trả READY nếu bàn vẫn bằng S2. Cancel sau bất kỳ
    bước arm hoặc manual placement nào chỉ dừng tiến trình và giữ RECOVERY_REQUIRED;
    không tự quay lại play hoặc lặng lẽ tự thực hiện rollback ngược lần nữa.
    Trước commit, recovery cho hai đích rõ ràng: tiếp tục hoàn tất S0 và consume,
    hoặc người chơi chủ động khôi phục S2 bằng tay rồi xác minh full-board để
    đánh dấu ABORTED_VERIFIED và trả cycle đó về READY. Không chạy arm tự redo
    để hủy rollback. Sau commit S0 không có nhánh abort về S2; chỉ hoàn tất
    baseline/remote sync đang dở.

19. **FR-19 — Khóa đồng thời, crash recovery và điều khiển.**
    Trong rollback chặn nhận nước mới, AI, test gắp, Emergency sửa FEN và Z lặp.
    New Game/đổi mode không được bỏ khóa một bàn đang thay đổi; yêu cầu hoàn tất
    hoặc phục hồi an toàn. Live camera và status luôn cập nhật; scanner chỉ xác
    minh checkpoint rollback, không gọi normal auto-confirm.
    Lưu transaction journal trước lệnh, sau verified và khi chờ người chơi.
    Khi app mở lại có transaction chưa xong: không tự chạy arm hoặc tự gửi S0;
    vào RECOVERY_REQUIRED, đối chiếu journal/controller/bàn trước khi resume.
    Journal và outbox khác vai trò: FEN outbox hiện tại không thay thế rollback journal.
    Cleanup phải hiểu rollback: đóng app khi transaction chưa hoàn tất không
    tự end_match(OTHER), không xóa journal, không ghi đè committed FEN bằng ảnh
    trung gian. Sau khi arm an toàn, lưu phase/checkpoint/commit marker/room_id
    và account scope rồi thoát. Khi mở lại, journal quyết định committed state
    là S2 trước commit hay S0 sau commit, thay vì mặc định INITIAL_FEN. Không
    phát motion hoặc tạo một game/room mới thay cho recovery. Room hết hạn ở
    server phải được báo riêng; vẫn cho phục hồi bàn local an toàn.

20. **FR-20 — Điểm tích hợp phải thay đổi khi triển khai.**
    GameState cần latest completed cycle và pending rollback riêng; input Z/GUI
    dùng cùng eligibility gate; renderer thêm disabled reason, log nhóm và target
    highlights; một rollback coordinator điều phối ledger/checkpoints/arm/manual.
    Tái sử dụng geometry, measured pick, nonzero motion guard, communication fault
    latch và fresh-idle proof. Không dùng nguyên AI coordinator vì nó cấp quyền
    theo turn Đen/pending AI, và không dùng nguyên handle_rollback vì nó commit
    FEN trước khi bàn thật được hoàn tác. Nâng verifier để trả mismatch theo ô,
    không chỉ bool, và áp dụng same-plane occupancy. Không thêm polling tự thay state.

---

## Non-Functional Requirements

- Performance: UI/camera không chờ RPC hoặc inference trên UI thread; mục tiêu
  cập nhật trạng thái giao diện ít nhất 10 Hz trong thao tác rollback. Hiện trạng
  camera/CPU thực tế phải đo lại khi commissioning, không suy ra từ unit tests.
- Security: mỗi motion phải gắn transaction/cycle/epoch/signature và checkpoint;
  nhấn Z nhiều lần tạo tối đa một transaction, không phát motion trùng. Không có
  logical-center fallback khi không đo được tâm thật. Loại/màu/ô không xác minh
  được thì không chuyển bước. Không cho người chơi xác nhận bỏ qua mismatch.
- Availability: giữ timeout transport hiện tại 10 giây, reconnect wait 5 giây;
  motion timeout không phải bằng chứng arm chưa chạy. Journal ghi atomic trước
  motion; partial failure trước final proof không commit S0 hoặc mở lượt. Sau
  commit, lỗi baseline giữ COMMITTED_WAIT_BASELINE, không đảo lại commit. Không cần Internet để
  phục hồi local; lỗi server phải hiển thị riêng và giữ outbox bền.

---

## Success Criteria

- [ ] Z chỉ enabled sau cycle seal READY; disabled ở BUILDING/busy/fault/test,
  giữa nước Đỏ–Đen, sau CONSUMED và khi chưa có cycle; nguyên nhân hiển thị rõ.
- [ ] Cycle không ăn: đúng hai lần chuyển quân Đỏ→Đen; camera mới trước từng pick và
  full-board verification sau từng bước; đúng một commit S0 cuối cùng.
- [ ] Bdst=Rsrc: đúng hai lần chuyển quân Đen→Đỏ, không ô đệm, không đặt lên ô đang có quân.
  Một lần chuyển quân gồm nhiều lệnh SDK gắp/đặt/về nghỉ; không phải chỉ một RPC.
- [ ] Cả sáu hàng của ma trận FR-11 có test ledger và expected checkpoints;
  arm chỉ chuyển các quân thực sự sống sót, không có lệnh vào bãi ăn.
- [ ] Black recapture Red mover: không có pick Đỏ; đúng một reverse motion Đen,
  rồi đủ một/hai quân phục hồi tay đúng vị trí S0 mới có thể commit.
- [ ] Mỗi sai màu/loại/ô, thiếu quân, thêm quân, sửa quân ngoài tập restoration,
  ảnh unknown hoặc confidence thấp đều không mở chơi/commit; status chỉ rõ nguyên nhân.
- [ ] Người chơi đặt nhiều quân đúng một lần được chấp nhận; đặt một phần đúng
  vẫn giữ checkpoint và danh sách còn thiếu. Camera không thể chứng minh ID vật
  lý của hai quân cùng màu/cùng loại; UI/tài liệu không hứa khả năng đó.
- [ ] Timeout/mất phản hồi giữa hai bước, hoặc sau chuyển quân trước ACK: không
  replay tự động; kiểm tra controller và full-board checkpoint mới cho resume.
- [ ] Đã verified một bước thì retry/restart không chạy lại bước đó; restart
  chỉ vào recovery. Z double-click không tăng số motion vượt kế hoạch.
- [ ] Thử hủy sau motion đầu: vẫn khóa play và giữ journal; FEN chính chưa thành S0.
- [ ] Trước final proof, board/FEN chính vẫn S2; sau proof là đúng S0 cùng turn,
  captured inventories và active move_history; audit có cả hai nước đã hoàn tác.
- [ ] Sau rollback chỉ một nước Đỏ mới được xác nhận mới tạo một AI job;
  Z lần nữa không thể lùi cycle cũ hơn. False SPACE/poll không ghi đè cycle.
- [ ] Baseline và arbiter reset từ ảnh S0 mới; baseline thất bại thì chưa mở chơi.
- [ ] Baseline lỗi sau commit chuyển COMMITTED_WAIT_BASELINE; retry/restart
  không tăng số lần chuyển quân, không apply commit/lịch sử hoặc logical FEN lần hai.
- [ ] Đóng app giữa rollback không end room mặc định; restart dùng đúng S2/S0
  theo marker, không INITIAL_FEN và không tự phát motion. Abort trước commit
  chỉ mở lại READY sau khi người chơi phục hồi S2 và full-board proof đạt.
- [ ] API transient retry, HTTP từ chối undo và S2 đang in-flight được test;
  không stale S2 sau S0, không replay arm vì API fail. Online acceptance phải
  xác nhận endpoint có thể nhận rollback trước khi tuyên bố hỗ trợ server đầy đủ.
- [ ] Physical acceptance bao gồm nguồn/đích ở bốn biên/góc, lệch tâm, camera
  nghiêng hợp lệ, bắt quân/recapture và mất kết nối ở từng checkpoint; test mock
  không được báo thành kết quả gắp/controller thật.

---

## Out of Scope

- Hoàn tác nhiều cycle, chọn một cycle cũ bất kỳ, undo stack không giới hạn, redo tự động.
- Arm tự tìm/gắp quân ở bãi ăn; dùng ô đệm khi xung đột (đã chọn đổi thứ tự thay thế).
- Phân biệt danh tính vật lý hai quân cùng màu/cùng loại mà không có marker/ID.
- Triển khai source hoặc chạy arm thật trong bước thiết kế này.
- Tự reopen room đã kết thúc, rollback sau game over hoặc tự sửa backend ngoài repo.
  Đây là phạm vi phiên bản đầu; nếu cần terminal-cycle rollback phải mở rộng chính sách
  game-over và protocol server riêng.

---

## Assumptions

- Người dùng đã chốt ngoại lệ Bdst=Rsrc: đưa Đen về Bsrc trước, rồi Đỏ về Rsrc;
  đây vẫn là một lần hoàn tác toàn cycle gần nhất.
- Ván khởi đầu từ state đã xác nhận. S0/S1/S2 và metadata capture nhất quán;
  trạng thái mất/không đầy đủ thì chặn rollback tự động.
- Camera có thể kiểm tra màu/loại/ô qua CChess, đo tâm qua best.pt/geometry; độ tin
  cậy thực tế và ngưỡng cần kiểm chứng trên camera thật. Đây là kiểm tra bố trí,
  không phải bảo đảm phát hiện mọi hình thức gian lận.
- Người chơi chỉ can thiệp tay khi UI ở WAIT_PLAYER hoặc bước phục hồi tay được
  chỉ dẫn trong RECOVERY_REQUIRED, sau khi arm parked/an toàn và outputs LOW đã
  được xác nhận; sau đó rút tay và xác nhận quét. Camera ổn định không tự chứng minh không có tay/vật lạ; stack
  hiện tại chưa có obstruction detector đã commissioning để bảo đảm điều đó.
- Bãi ăn có thể chứa quân từ các cycle trước: phần mềm chỉ yêu cầu màu/loại của
  những quân cần cho S0, không yêu cầu lấy theo một tọa độ bãi ăn chưa được theo dõi.
- API rollback online chưa được xác nhận. Local rollback phải an toàn và quan sát
  được ngay cả khi server không nhận FEN đi ngược; hỗ trợ online đầy đủ là một
  acceptance gate riêng, không phải tính năng mặc nhiên đã có.
