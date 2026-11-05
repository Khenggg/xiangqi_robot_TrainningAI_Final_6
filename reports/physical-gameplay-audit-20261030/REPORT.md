# Rà luồng chơi với kết nối robot thật — 2026-10-30

## Kết luận thực tế

Lỗi chặn nước đi trong log vật lý không phải lúc nào cũng là lỗi FEN. Log
`logs/20261028_194959_184ae968/events.jsonl:217-232` ghi rõ:

1. Nước AI dùng backend `PHYSICAL`, Pháo Đen `(7,2) → (4,2)`.
2. Hai ảnh liên tiếp khớp FEN, `quality_ok=true`, `board_diff_count=0`.
3. Ba lần đo tâm đều đạt; confidence khoảng 0.85, lệch khoảng 3.1 mm.
4. Nước đi bị chặn tại PREPOSITION vì:
   `HOMECHESS: tool/user frame differs from R1-R4 or metadata is missing`.

Đây là bằng chứng lịch sử về cấu hình waypoint chặn vận hành. Không có phép đo
online trong lượt rà này để xác định waypoint trên controller hiện đã được sửa chưa.

Các probe chạy trực tiếp code PHYSICAL, không mở socket/camera/controller. API
được thay bằng mock; SDK là fake; calibration là fixture. Không sửa production,
calibration hay config. Không dùng skill hoặc subagent cho lượt rà này.

## Những điểm chính cần xử lý

### P1 — Chưa kiểm tra đủ waypoint trước khi cho bắt đầu ván

**Code:** `src/hardware/robot_VIP.py:166-190`, `365-448`, `875-889`.

Activation kiểm tra bốn góc và cấu hình kẹp, nhưng chưa xác nhận HOMECHESS và
R_Trash sẵn sàng cho cả ván. HOMECHESS được kiểm tra khi đã bắt đầu xử lý nước
robot. R_Trash được load optional; thiếu nó vẫn có thể bật và đi các nước thường,
nhưng nước ăn đầu tiên sẽ bị chặn.

**VERIFIED qua probe:** HOMECHESS khác user frame vẫn enable thành công, nước
đầu thất bại trước khi MoveCart được gọi. Thiếu R_Trash vẫn enable/đi thường được,
đến nước ăn thì thất bại, không gửi thêm motion. Việc từ chối tọa độ sai là đúng;
khoảng trống nằm ở thông báo readiness của toàn ván.

**Sửa cần thiết:** preflight read-only đầy đủ R1-R4, HOMECHESS, R_Trash, metadata
tool/user và dữ liệu pose/joints trước khi chấp nhận enable cho ván bình thường.
Thông báo chính xác point/frame thiếu hoặc lệch. Không bỏ kiểm tra frame để cho
robot chạy qua. Chỉnh/dạy lại point trên controller cần người vận hành xác minh.

**Kiểm chứng sau sửa:** waypoint thiếu/sai phải báo trước khi vào lượt đầu;
waypoint hợp lệ phải qua được nước thường, ăn quân, quay về HOME và tiếp tục lượt.

### P2 — Deadline quét FEN không giới hạn được lần đọc camera đang bị kẹt

**Code:** `src/hardware/hardware_manager.py:1334-1368`;
`src/vision/camera_monitor.py:426-431`, `453-463`, `478-489`.

Verifier kiểm tra thời gian giữa các lần thử, nhưng bên trong gọi camera read và
inference đồng bộ. Nếu driver/model chậm hoặc treo, vòng ngoài không thể thực thi
kiểm tra deadline cho tới khi lời gọi đó trả về. Lock inference/camera cũng không
có hạn chờ ở các đường gọi này. Cửa sổ retry 2 giây không phải giới hạn tổng thời
gian hoàn thành thao tác. Worker giữ lượt hoặc giữ pending trong lúc chờ.

**VERIFIED qua probe:** dùng `CameraMonitor.get_fresh_observation` thật và fake
camera có `read` bị chặn bằng Event. Budget thu nhỏ còn 0.02 giây; sau 0.08 giây
verifier vẫn chưa xong. Chỉ sau khi giải phóng fake read nó mới trả kết quả.
Probe không khẳng định camera thật hiện đang treo.

**Sửa cần thiết:** acquisition/inference có owner riêng; worker game chờ kết quả
mới bằng deadline và token hủy. Nhận diện/camera không sẵn sàng phải cho trạng thái
chờ/khôi phục rõ ràng, không giữ một lời gọi thiết bị vô hạn. Không giải quyết
bằng chấp nhận ảnh cũ hoặc chỉ tăng timeout.

**Kiểm chứng sau sửa:** chặn read/inference và tranh chấp lock; xác nhận UI vẫn
nhận yêu cầu dừng, kết quả muộn không được dùng, không đóng thiết bị dưới worker
còn chạy và không tự phát lại lệnh robot.

### P2 — “Xóa phiên lỗi” chưa nói rõ cần F5 để khởi động lại lượt AI

**Code:** `src/ui/input_handler.py:1124-1148`;
`src/core/game_state.py:438-470`; F5 tại `main.py:685-686`.

Khi Đỏ đã đi, AI đã bắt đầu nhưng lỗi xảy ra trước gắp, xác nhận lại bàn cũ rồi
xóa phiên lỗi sẽ bỏ pending và báo “đã tiếp tục quét”. Tuy nhiên generation AI
đã bị tiêu thụ và retry flag vẫn false. Đây vẫn là lượt Đen, nên camera cũng không
nhận lượt Đỏ tiếp theo. AI không tự bắt đầu lại cho tới khi có thao tác retry.

**VERIFIED qua probe GameState thật:** sau xóa lỗi, `physical_sync_fault=false`,
pending rỗng, `turn=b`, generation=1 và consumed=1, `can_start_ai_turn=false`.
Đặt retry flag như handler F5 thì `can_start_ai_turn=true`.

**Giới hạn finding:** có F5 để tiếp tục, không phải deadlock không thể phục hồi.
Không tự replay chuyển động sau lỗi là hành vi cần giữ. Điểm thiếu là trạng thái
và hướng dẫn thao tác sau khi đã xác nhận bàn/robot.

**Sửa cần thiết:** tách “đã xác nhận bàn” và “được phép thử lại lượt AI”; hiện nút
hoặc hướng dẫn F5 rõ ràng, chỉ cho phép retry khi các gate recovery/idle/enable
đã đạt. Pending đã hoàn tất trên bàn thật phải commit, không đi lại.

**Kiểm chứng sau sửa:** lỗi trước gắp, sau gắp, sau đặt và sau bỏ quân bị ăn phải
có đường tiếp tục riêng, không tiêu thụ sai lượt và không nhân đôi nước đi.

### P1 đã xác nhận từ lượt rà trước — Mẫu camera cuối lỗi vẫn dùng tâm cũ

`src/hardware/hardware_manager.py:983-1056` vẫn giữ nguyên. Nhánh center chấp nhận
hai mẫu tốt trước đó dù lần đọc cuối báo mất camera; dispatch có thể dùng target
đó. Đây là lỗi ảnh hưởng trực tiếp từng nước trong ván và chưa có bản sửa.

Bằng chứng chi tiết, probe và hai lỗi activation/stop còn OPEN ở
`../physical-flow-audit-20261030/REPORT.md`. Không tính lại chúng là finding mới.

## Các đường đã chạy được và các giới hạn

Lệnh kiểm chứng:

```powershell
.\.venv312\Scripts\python.exe -X utf8 reports/physical-gameplay-audit-20261030/probe_gameplay.py
```

Môi trường Windows / Python 3.12.10, `.venv312`. **PASS, exit 0**, nghĩa là
assertions của các phép tái hiện và replay đạt, không có nghĩa lỗi đã được sửa.
Chi tiết ở `evidence.json`, `probe-console.txt`, `probe-errors.txt`.

- Replay hợp lệ từ bàn khai cuộc: **240 lượt đi, 120 nước robot, 12 nước ăn của
  robot**, 240 durable commits trong journal tạm. FEN/board, lượt, revision và
  pending khớp sau mỗi nước.
- Đi qua `execute_ai_move` → `execute_pending_ai_motion` → `HardwareManager` →
  `FR5Robot` stage sequence → camera verification → commit. Cả trước và sau nước
  robot đều dùng verifier production trên dữ liệu camera giả đầy đủ.
- Chèn một lần mất tâm quân nguồn sau khi đã bỏ quân bị ăn: pause ở
  `capture_removed`; retry cùng nước hoàn tất, không bỏ quân bị ăn lần thứ hai.
- Fake SDK mất phản hồi MoveCart: code trả failure sau đúng một lần gọi, không
  tự gửi lại motion. Đây là hành vi đúng cần giữ khi Ethernet chập chờn.

**Không gọi đây là một ván vật lý hoàn tất:** replay dừng theo giới hạn 240 lượt,
`game_over=false`. Nước đi được chọn tất định từ các nước hợp lệ, không chạy engine
AI thật. Mô hình nhận diện, calibration, kẹp, đường đi, độ lệch đặt quân, thiết bị
và latency thực tế không được đo. Replay không chứng minh gắp/đặt thành công.

Full regression và test phần cứng: **NOT RUN**. Không có skill nào được gọi trong
lượt này; dùng script probe tập trung, không chạy lại suite không liên quan.

## Thứ tự xử lý đề xuất

1. Xử lý blocker HOMECHESS đã thấy trong log; preflight đầy đủ waypoint trước ván.
2. Sửa lỗ hổng stop/enable và mẫu center cuối lỗi đã tái hiện ở báo cáo trước.
3. Giới hạn chờ camera và làm rõ các checkpoint tiếp tục sau lỗi/F5/Y/V.
4. Sau sửa, mới kiểm chứng trên FR3 được ủy quyền: đo gắp/đặt lặp lại, nước ăn,
   độ lệch tích lũy, bỏ quân, quay HOME, mất mạng và phục hồi trong một ván thực.

Hiện chưa có bằng chứng để cam kết robot thật vận hành mượt suốt ván. Không giảm
điều kiện đối chiếu FEN hoặc biến “đủ 32 quân” thành quyền gửi motion để đạt điều đó.
