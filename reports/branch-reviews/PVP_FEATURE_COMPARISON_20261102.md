# Hai nhánh PvP bổ sung gì so với bản đang dùng?

Ngày đối chiếu: 2026-11-02. Đây là bản giải thích chức năng và lựa chọn tích hợp,
dựa trên audit 30/10, kiểm tra lại source/ref và chạy lại các kiểm thử liên quan.
Không thực hiện merge, sửa runtime, đổi calibration hay kết nối phần cứng.

## Phạm vi chính xác

| Bản | Commit được kiểm tra | Trạng thái |
|---|---|---|
| Bản đang dùng | need-review `18e67fc`, cộng source chưa commit | Đối tượng cần bảo toàn |
| feature/player-vs-player | `75c1bc9` | Commit cuối revert PvP |
| feature/nguoivsnguoifinal | `73af0f1` | Giữ PvP và phần sửa tiếp theo |

`git ls-remote --heads origin feature/player-vs-player feature/nguoivsnguoifinal`
ngày 02/11 xác nhận hai remote tip chưa đổi so với audit. Tám source donor được
đối chiếu với git show; tám source runtime trọng yếu của target vẫn khớp hashes
đã review. Không đồng nhất working tree hiện tại với riêng committed HEAD.

## 1. feature/player-vs-player

Tên nhánh dễ gây hiểu nhầm: từng có chức năng hai người, nhưng tip là
`Revert "feat: add local two-player Xiangqi mode"`. So với `fb0598d`, diff tại
tip rỗng. Do đó không còn module/phòng PvP mới để lấy từ tip này.

Nhánh vẫn mang nền người-vs-AI/robot, camera, visual pick và setup của dòng
visual-correction-v2 cũ. Điều này không có nghĩa nhánh rỗng hoàn toàn, nhưng
không phải nguồn để bổ sung PvP vào bản đang dùng. Nếu muốn xét nền vision/setup,
cần một phạm vi đánh giá riêng; không lấy kèm chỉ vì tên nhánh có player-vs-player.

## 2. feature/nguoivsnguoifinal

Phần riêng của tính năng nằm trong hai commit sau `fb0598d`, thay đổi sáu file,
1.299 dòng thêm / 36 dòng bỏ; chủ yếu là `player_vs_player.py` (1.122 dòng).

### Trải nghiệm người dùng

1. Mở màn VS NGƯỜI trong ứng dụng desktop Pygame.
2. Chọn phòng không robot hoặc phòng có robot; có thêm màn test gắp/thả FR3.
3. Chủ phòng nhận mã ngẫu nhiên sáu ký tự và chơi Đỏ.
4. Process/cửa sổ ứng dụng thứ hai nhập mã, được gán Đen.
5. Cửa sổ Đen nhìn bàn xoay 180 độ; click được quy đổi về tọa độ logic.
6. Hai người click chọn quân nguồn/đích; có kiểm tra lượt và luật nước đi.
7. Ở phòng không robot, host xử lý nước và gửi trạng thái bàn/lượt cho client.
8. Ở phòng có robot, host yêu cầu một FR3 gắp/đặt cho cả Đỏ lẫn Đen, sau đó
   camera đối chiếu bàn. Client gửi yêu cầu nước, không trực tiếp sở hữu FR3.
9. Khi camera chưa xác nhận, có nút quét/gắp lại nước lỗi; có màn trạng thái
   camera, người thắng, nước vừa đi, đóng phòng và quay menu.

Đây là code có chức năng và một số đường đã chạy được bằng mock/loopback;
không phải một tính năng hoàn thiện chỉ cần merge là vận hành ổn định.

### Giới hạn dễ hiểu nhầm

- Phòng dùng socket `127.0.0.1` và registry trong thư mục temp của cùng máy.
  Vì vậy đây là **hai cửa sổ/process trên một PC**, không phải phòng LAN/Internet.
- Mã phòng không phải link trình duyệt; điện thoại/máy khác không vào chỉ bằng mã.
- Vai cố định chủ Đỏ/khách Đen; các tab Đỏ/Đen không phải hai browser tab.
- Đường dùng cả hai vai trong cùng một cửa sổ có lỗi quyền chọn bên Đen.
- Chế độ robot là hai người chọn nước trên màn hình, robot thực hiện; không phải
  hai người tự di chuyển quân thật rồi camera tự ghi nhận cả hai lượt.
- Không có thuật toán AI, FK/IK hay cơ chế tránh va chạm mới trong phần PvP riêng.

## 3. Bảng so sánh chức năng

| Nhu cầu | need-review đang dùng | player-vs-player tại tip | nguoivsnguoifinal |
|---|---|---|---|
| Người vs AI | Có, virtual/physical theo profile | Giữ nền legacy | Giữ nền legacy; PvP không bổ sung AI |
| AI vs AI, một FR3 thực hiện | Có mode riêng | Không phải giá trị bổ sung của nhánh | Không phải giá trị bổ sung của PvP |
| Hai người click chung một bàn 2D | Có Hvh, BOTH_PLAYERS | PvP đã bị revert | Có ý đồ tab Đỏ/Đen nhưng đường một cửa sổ còn lỗi |
| Hai cửa sổ gán vai riêng | Chưa có luồng phòng này trong main/src | Không còn | Có host Đỏ/client Đen |
| Mã phòng sáu ký tự | Chưa có giao diện phòng PvP này | Không còn | Có |
| Đồng bộ hai cửa sổ qua phòng | Chưa có transport PvP này | Không còn | Có trên localhost; lỗi khi disconnect/rejoin |
| Góc nhìn Đen xoay 180 độ | Không có luồng hai client/vai riêng của donor | Không còn | Có, kèm đổi tọa độ click |
| Hai người click, một FR3 đi cả hai bên | Hvh hiện resolve virtual, không bật robot/camera | Không còn | Có implementation, chưa đủ điều kiện lấy nguyên |
| Hai người tự đi quân thật, camera ghi nhận cả hai bên | Chưa có Hvh physical theo profile hiện tại | Không có tính năng PvP mới | Không phải workflow mà phòng robot triển khai |
| Chơi hai PC/điện thoại qua mạng | Không được tính là tính năng phòng PvP đã có | Không có | Chưa có; loopback + registry cùng máy |
| Test gắp/thả | Có luồng hiện tại với move_context | Nền legacy | Thêm màn test riêng, trùng nhu cầu và khác API |
| Đối soát FEN, lý do/diff từng ô | Có verifier/diagnostics hiện tại | Không cung cấp bản nâng cấp đã xác minh | Thêm log nhưng verifier PvP yếu hơn |
| Phục hồi, lưu pending và trạng thái ván | Có GameState/journal/coordinator | Không nên thay bằng legacy | Room giữ board/turn riêng trong RAM |
| Mô phỏng và viewer 3D | Đã có hệ tích hợp | Không đem lại hệ tích hợp mới | LocalRoom chưa nối vào luồng committed-state/projection hiện tại |
| Giữ UI xử lý khi chờ robot/camera | Có worker và luồng đóng/chuyển phiên | Legacy cần review riêng | Đường chạy nước PvP còn đồng bộ trên UI thread |

"Có" ở target mô tả chức năng/contract hiện hữu, không phải chứng nhận toàn bộ
phần cứng vận hành đúng. Các lỗi physical sau mất điện/va chạm vẫn là vấn đề riêng.

Nguồn đối chiếu: target `src/core/session_profile.py:40`, main/UI hiện tại;
donor `player_vs_player.py:46` (transport), `:202` (room), `:378` (menu),
`:439` (ván), `:474`/`:522` (view), `:741` (phòng robot), `:766` (join),
`:804`/`:842` (nước), `:983` (retry). Snapshot nguồn nằm trong
`pvp-20261030/final/`; nội dung tám file đã được so với remote tip đã chốt.

## 4. Các phần kế thừa không nên nhầm là tính năng PvP mới

Diff từ merge-base đến donor còn gồm 69 file, 8.204 dòng thêm / 262 dòng bỏ,
và 29 commit riêng. Nó mang theo camera calibration/intrinsics, đo geometry,
top-face/top-rim/colored-ring pick, consensus, hover/test, debug và Windows setup.
Nhiều phân hệ cùng mục đích đã có và được mở rộng trong source hiện tại.

Không kết luận toàn bộ thuật toán trong 69 file đều đã được audit mới ngày 02/11.
Audit trước tập trung PvP, direct dependencies và rủi ro tích hợp. Đặc biệt không
chép calibration của máy donor, config DRY_RUN=False hay margin 10 mm sang bản
đang có profile user-0 và margin 6 mm chỉ để lấy một màn PvP.

## 5. Chức năng có rồi nhưng còn hỏng ở đâu?

| Vấn đề đã review | Biểu hiện đối với người dùng | Quyết định |
|---|---|---|
| F1: startup robot legacy | Tạo phòng có thể tự enable, tác động kẹp và HOME trước camera | Bắt buộc thay bằng startup/activation hiện tại |
| F2: gọi robot trực tiếp | Thiếu target camera vẫn có thể đi; không bắt buộc dọn quân ăn/quét lại nguồn | Nước phòng phải đi qua coordinator hiện tại |
| F3: đổi bàn/lượt trước hậu kiểm | Camera fail nhưng màn hình đã sang lượt kế tiếp; kết quả bị từ chối có thể bị bỏ qua | Chỉ commit sau kiểm chứng, lưu pending vào journal |
| F4: verifier yếu | Hai mẫu không liên tiếp, thiếu freshness/quality/confidence vẫn được nhận | Dùng verifier hiện tại |
| F5: chặn UI | Đang đi nước/chờ camera có thể không xử lý F2/đóng cửa sổ kịp | Dùng worker/disposal hiện tại |
| F6: API/profile khác | Hvh robot bị capability current chặn; test gắp khác chữ ký API | Thiết kế profile hai người chọn nước + robot thực hiện rõ ràng |
| F7: room lifecycle | Thoát rồi vào phòng khác lỗi; client disconnected có thể tự commit bàn riêng | Sửa leave/rejoin/disconnect và quyền commit |

Chi tiết nguồn gốc, line references và probes nằm trong báo cáo audit chính
`feature-nguoivsnguoifinal_vs_need-review_REVIEW_REPORT.md`. Không quy các lỗi
donor này thành lỗi đã xác minh trong current hoặc nguyên nhân va chạm đã xảy ra.

## 6. Nếu merge thì được gì, phải trả giá gì?

| Lựa chọn | Lợi ích | Chi phí/rủi ro | Khuyến nghị |
|---|---|---|---|
| Giữ nguyên hiện tại | Giữ Hvh một bàn, HvR, RvR và các bản sửa hiện có | Chưa có phòng/vai hai cửa sổ; Hvh chưa điều khiển FR3 | Hợp lý nếu chỉ cần hai người chơi chung một bàn 2D |
| Merge nguyên player-vs-player | Không lấy được PvP ở tip | Mâu thuẫn baseline và revert tính năng | Không chọn cho mục tiêu PvP |
| Merge nguyên nguoivsnguoifinal | Có code phòng và PvP+FR3 | 32 file conflict và các lỗi F1–F7; có nguy cơ thay các bản sửa bằng legacy | Không khuyến nghị |
| Port chọn lọc phòng/UI từ nguoivsnguoifinal | Có mã phòng, vai, góc nhìn và đồng bộ; giữ kiến trúc hiện tại | Phải sửa lifecycle, giao thức/session/revision và thêm tests tích hợp | Phù hợp cho hai cửa sổ cùng PC |
| Port phòng rồi thêm Hvh physical | Hai người chọn nước, một FR3 làm cả hai | Phải có profile mới, giữ duy nhất một owner robot, verifier/journal/stop và kiểm chứng vật lý riêng | Có giá trị nếu đúng nhu cầu, làm thành giai đoạn riêng |
| Làm phòng LAN/Internet/mobile | Chơi từ thiết bị khác | Thêm discovery/server/auth/reconnect, không chỉ đổi 127.0.0.1 | Một tính năng khác, donor chưa cung cấp |

Hai donor không phải hai bộ chức năng độc lập cần merge lần lượt. Một nhánh
revert module mà nhánh kia giữ, nên ghép chúng còn phát sinh modify/delete tại
player_vs_player.py. Giá trị mới tập trung ở nguoivsnguoifinal.

Khi port, giữ GameState làm nguồn bàn/lượt, đi nước qua coordinator hiện tại,
client gửi yêu cầu và nhận trạng thái đã commit; không đưa LocalRoom thành nguồn
bàn thứ hai. Giữ các bản sửa FEN/fresh-start/F2, fixed user-0, worker, stop và
projection. Giữ nguyên lỗi physical đang mở như vấn đề cần xử lý riêng, không
tuyên bố port PvP sẽ chữa lỗi HOME hoặc mất điện.

## 7. Kiểm chứng lại ngày 02/11

- Remote SHA: xác nhận bằng git ls-remote, exit 0, chưa đổi so với audit.
- 8 source donor/snapshot: nội dung khớp git show; 8 source target trọng yếu
  khớp hash audit. Không có production edit trong tác vụ này.
- Runner: PATH ưu tiên .venv312, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL,
  PYTEST_ADDOPTS=-x; Windows, Python 3.12.10, pytest 9.1.1, xdist 3.8.0.

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests @(
  'reports/branch-reviews/pvp-20261030/test_donor_pvp_review.py',
  'tests/unit/test_session_modes.py',
  'tests/unit/test_game_modes_review.py',
  'tests/unit/test_session_user_flows.py'
)
```

PASS, exit 0: 57 parallel + 1 serial = 58, runner 24,69 giây. Output:
`pvp-20261030/decision-recheck-20261102.txt`. Gồm 45 test current + 13 donor
probe; 11 probe PASS bằng cách tái hiện lỗi, 2 probe kiểm tra đường local game /
view và socket loopback. Không suy PASS này thành bản merge đã hoàn thiện.

Mô phỏng merge 30/10: mỗi donor với target committed có 32 file conflict;
refs không đổi. Đây chưa bao gồm toàn bộ việc xử lý source chưa commit.
Full regression bản tích hợp, giao diện native đầy đủ, CI exact-head và robot
thật: NOT RUN / NOT AVAILABLE như ghi trong audit. Không có bản merge thực tế.
