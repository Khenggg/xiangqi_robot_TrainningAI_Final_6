# Lựa chọn tích hợp visual-correction-v2 — 09/10/2026

**Trạng thái: ĐÃ DUYỆT C01–C10 = A. User xác nhận “ok làm theo khuyến nghị đi”.**

Patch chọn lọc đã đưa về repo chính sau kiểm tra worktree, chưa commit/push. Hướng dẫn hiện hành: [VISUAL_V2_INTEGRATION.md](VISUAL_V2_INTEGRATION.md); bằng chứng: [báo cáo tích hợp](../reports/visual-integration-20261009/REPORT.md). Các phần dưới đây giữ lại nội dung quyết định trước tích hợp để truy vết.

File này là phiếu lựa chọn cho đợt tích hợp mới, không thay thế calibration và không cho phép chuyển động robot thật. Điền cột **Bạn chọn** bằng `A`, `B` hoặc ghi yêu cầu riêng. Cột khuyến nghị chỉ là đề xuất, chưa phải quyết định của bạn.

## 1. Hai bản mã đang so sánh

- Dự án hiện tại: `feature/unified-robot-vs-robot`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e` **cộng các thay đổi chưa commit hiện có**.
- Nguồn mới: đã fetch `origin/feature/visual-correction-v2`, HEAD `fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09`.
- Visual có thêm **19 commit / 54 file** so với `652af26` đã được tích hợp chọn lọc trước đây.
- Diff từ merge-base `e6bb632` tới visual: **64 file**. HEAD hai nhánh có 145 commit chỉ ở unified và 26 commit chỉ ở visual; số này không có nghĩa phải lấy lại toàn bộ 26 commit.
- Git báo **10 file xung đột** khi so HEAD đã commit; khi tính cả source/docs/tests chưa commit hiện tại, snapshot phân tích báo **17 file xung đột**.

Snapshot tạm `da703237561c5264d96886514852bd958e613409` chỉ phục vụ `merge-tree`, không commit lên nhánh của bạn và không thay đổi index chính. Báo cáo/ignored files không nằm trong snapshot đó. Thông tin chi tiết và phạm vi: [báo cáo kỹ thuật](../reports/branch-reviews/feature-visual-correction-v2_vs_feature-unified-robot-vs-robot_REVIEW_REPORT.md).

## 2. Visual mới có gì đáng lấy?

| Bổ sung | Lợi ích | Điều kiện để dùng |
|---|---|---|
| Hình học camera và mặt trên quân | Bù sai lệch phối cảnh do quân cao hơn mặt bàn | Intrinsics đúng camera/resolution, kích thước bàn và chiều cao quân đúng phép đo |
| Consensus mặt trên quân | Chọn nhóm quan sát nhất quán bằng mm, chặn kết quả thiếu/không rõ | Ghép vào resolver hiện tại; không lấy số mm thử nghiệm làm sai số kẹp đã đo |
| Wizard calibration camera | Đo intrinsics, lưu mẫu checkerboard, báo lỗi fit | Chạy độc lập, không điều khiển robot |
| Quét nhiều frame + debug + hover | Dễ xem điểm gắp được đo và thử tiếp cận | Hover vẫn là chuyển động; phải qua quyền điều khiển và executor |
| Retry đúng nước đang chờ | Thử đo lại khi chưa gắp hoặc sau khi đã bỏ quân bị ăn | Không thực hiện lại bước ăn quân đã hoàn tất; không retry lỗi motion như lỗi camera |
| Worker cho thao tác vật lý | GUI tiếp tục đáp ứng khi đang lấy mẫu/chạy arm | Một chủ sở hữu motion; đóng/restart không tranh camera/SDK |
| Colored-ring pick | Thử tìm tâm vòng mực màu trên quân | Opt-in; cần dữ liệu quân và ánh sáng thực tế |
| Cho phép tâm gắp ngoài lưới 10 mm | Nhận quân lệch ra phần mép trang trí | Chỉ là giới hạn nhận diện; không chứng minh quỹ đạo ngoài lưới an toàn |
| Setup Windows/Python 3.12 | Chuẩn hóa môi trường vision | Lock của visual chưa có đủ dependency simulation hiện tại |

## 3. Những phần đã yêu cầu giữ từ trước

Đề xuất tiếp tục giữ simulation/viewer, R1–R4/BoardPoseProvider, hình học kẹp, collision guard, typed executor, identity quân, đồng bộ world, ba chế độ chơi, launcher/logging và bản sửa telemetry ở dự án hiện tại. Những file không conflict về chữ vẫn cần kiểm tra logic khi nối với vision mới.

Đặc biệt, **không lấy nguyên `main.py`, `hardware_manager.py`, `robot_VIP.py`, `input_handler.py` của visual**: chúng chứa đường chạy legacy khác dự án đang dùng.

## 4. Phiếu lựa chọn

| ID | Điểm cần quyết định | A | B | Khuyến nghị | Bạn chọn |
|---|---|---|---|---|---|
| C01 | Cách tích hợp | Ghép chọn lọc tính năng visual vào kiến trúc hiện tại | Chỉ lấy module toán/calibration trước, hoãn UI/retry/worker | A | **A — ĐÃ DUYỆT** |
| C02 | Chế độ gắp mặc định | Giữ strict center hiện tại; thêm height/top-face/ring dưới dạng tùy chọn, chưa tự bật | Chọn height làm mặc định physical sau khi xác minh calibration của máy bạn | A | **A — ĐÃ DUYỆT** |
| C03 | Khi không tìm được tâm hợp lệ | Dừng và cho phép đo lại ở checkpoint phù hợp | Giữ fallback center → foot của visual trong chế độ legacy, chỉ bật riêng khi bạn chủ động chọn | A | **A — ĐÃ DUYỆT** |
| C04 | Vùng ngoài lưới | Tích hợp khả năng 10 mm nhưng mặc định tắt; bật theo profile đã kiểm chứng | Giữ giới hạn hiện tại và hoãn tính năng ngoài lưới | A | **A — ĐÃ DUYỆT** |
| C05 | Retry và worker | Tích hợp cả hai qua state machine/executor hiện tại, áp dụng đúng actor của ba chế độ | Tích hợp retry trước, giữ thực thi tuần tự hiện tại và hoãn worker | A | **A — ĐÃ DUYỆT** |
| C06 | Tham số robot thật | Giữ thông số hiện tại; lưu thông số visual thành profile ứng viên riêng | Dùng bộ thông số visual làm ứng viên thay thế và kiểm chứng riêng trước khi kích hoạt | A | **A — ĐÃ DUYỆT** |
| C07 | Camera và intrinsics được commit | Giữ camera hiện tại, lấy công cụ calibration; không tự dùng profile camera 0 của máy khác | Nhập profile visual như ứng viên riêng nếu bạn xác nhận cùng camera/lens/resolution | A | **A — ĐÃ DUYỆT** |
| C08 | Setup Windows | Ghép dependency vision vào môi trường có đủ PyBullet/WebSocket và kiểm tra khởi động | Giữ môi trường hiện tại, hoãn SETUP_WINDOWS/lock mới | A | **A — ĐÃ DUYỆT** |
| C09 | GUI và công cụ đo | Giữ resize/fullscreen, mapping chuột và fault latch; thêm nút retry/hover và diagnostic mới | Giữ GUI/công cụ đo hiện tại, hoãn nút mới | A | **A — ĐÃ DUYỆT** |
| C10 | Tài liệu và metadata | Ghép hướng dẫn tính năng đã chọn; giữ cảnh báo tài liệu tương lai; bỏ session-data/token-count của visual | Chỉ thêm phụ lục hướng dẫn mới, giữ nguyên README và metadata hiện tại | A | **A — ĐÃ DUYỆT** |

Bạn có thể trả lời trong chat, ví dụ: `C01=A, C02=A, C03=A, C04=B, các mục còn lại=A`. Hoặc sửa trực tiếp cột cuối rồi báo tôi đọc lại file. Để chọn chế độ cụ thể ở C02, ghi thêm `HEIGHT`, `TOP_FACE` hoặc `RING`; cần dữ liệu calibration trước khi bật physical.

## 5. Thông số khác nhau ở C06/C07

Các số sau là **giá trị trong code**, không phải xác nhận số đo phù hợp với phần cứng bạn đang dùng.

| Thông số | Dự án hiện tại | Visual `fe3faa8` |
|---|---|---|
| `SAFE_Z`, mm theo config physical | 210 | 220 |
| `MOVE_SPEED`, % | 70 | 50 |
| `ROTATION`, độ | `[-179,-1.5,-11.3]` | `[180,0,-73.2]` |
| Xung mở tối đa, giây | 0.30 | 0.25 |
| Xung đóng, giây | 0.80 | 0.20 |
| Camera mặc định | 1, có override rõ ràng | 0, backend any, yêu cầu 640×480 |
| Vùng giao điểm cho height geometry, mm | Chưa có cấu hình vision height này | 324×368 |
| Chiều cao quân cho height compensation, mm | Chưa có cấu hình vision height này | 7, comment ghi chiều cao đo 9 |
| Bộ top-face độc lập, mm | Chưa có | Bàn 250×281.25, quân cao 10 |
| Gắp ngoài lưới | Theo hợp đồng hiện tại | Biên 10 mm |

Không dùng bộ kích thước camera/top-face này để thay trực tiếp model bàn/kẹp/R1–R4. Khi tích hợp phải tách hình học đo camera với hình học robot và chỉ dùng dữ liệu có nguồn gốc rõ ràng.

## 6. Điều kiện kỹ thuật phải sửa khi ghép

Đây là điều kiện giữ chức năng đúng, không phải lựa chọn cho phép bỏ qua lỗi:

1. Giữ xử lý mã SDK khác 0 thành failure, dừng trước các stage/kẹp tiếp theo. Probe donor SDK Mock trả 112 cho 7 motion vẫn có 3 lệnh kẹp sau lỗi đầu và hàm manual test trả target; lỗi wrapper này đã tồn tại từ bản visual cũ.
2. Không thay strict center hiện tại bằng fallback legacy ngầm. Fallback mới **chỉ nằm ở nhánh legacy** khi height/top-face/ring không được chọn; height mặc định của donor không chạy fallback đó.
3. Ghép retry với move identity, epoch, actor, checkpoint và typed result hiện tại. Coordinator donor chỉ phục vụ lượt AI đen; không chép vào tự đấu hai màu như một executor chung.
4. Giữ kiểm tra toàn bộ bàn trước/sau motion thật và cơ chế lỗi chặn chạy tiếp. Verify riêng ô nguồn/đích của donor không thay cho kiểm tra toàn bộ bàn hiện tại.
5. Worker không được mở thêm chủ sở hữu simulation/SDK hoặc commit FEN từ kết quả lỗi thời; hủy/đóng phải có kết quả rõ ràng.
6. Setup mới phải có đủ `pybullet`, `websockets` và dependency launcher; smoke import vision riêng của donor chưa kiểm chứng stack hiện tại.

## 7. Kế hoạch sau khi bạn chọn

1. Chốt lựa chọn và xác nhận SHA/source hiện tại chưa thay đổi.
2. Tạo worktree tích hợp từ snapshot đầy đủ source hiện tại, ghép theo từng nhóm đã chọn.
3. Chạy tests mới của visual và các tests hiện có cho executor, identity, R1–R4, game/camera sync, recovery, launcher và telemetry.
4. Probe failure/retry/capture bằng SDK/camera giả; kiểm tra không lặp motion hoặc commit FEN sai.
5. Chạy system/GUI simulation theo ba chế độ, nước thường và ăn quân, reconnect viewer, manual test/hover tương ứng phần đã chọn.
6. Đưa patch đã kiểm chứng về repo chính, kiểm tra không mất các thay đổi đang dở và cập nhật tài liệu.

**Chưa merge, chưa cherry-pick và chưa sửa production trong đợt chuẩn bị này.** Đã chạy 168 tests / 200 subtests của donor trong worktree, không phải test của bản tích hợp chưa tồn tại; chưa chạy camera/FR3 thật.
