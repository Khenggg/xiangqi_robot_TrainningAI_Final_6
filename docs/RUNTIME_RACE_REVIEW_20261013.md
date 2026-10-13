# Rà soát thứ tự sự kiện, worker và retry — 13/10/2026

## Phạm vi và cách kiểm tra

Tiếp tục từ `docs/GAME_MODE_REVIEW_20261013.md`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e` cộng các thay đổi chưa commit. Dùng lại worktree kiểm chứng riêng; `reports/runtime-race-review-20261013/baseline.json` và bản source trước sửa xác nhận snapshot của các file đích khớp repo chính.

Truy vết đường gọi thực tế trong main, controller, handler, worker và ranh giới commit. Chủ động đảo lịch sự kiện: thread đã kết thúc nhưng UI chưa nhận kết quả; QUIT trước một phím khác trong cùng hàng đợi; thao tác UI chạy cùng self-play; camera thất bại sau khi nước đã được xác nhận. Các giả thuyết được chạy trên mã trước sửa, không lấy kết quả test cũ làm căn cứ kết luận.

Không dùng camera/FR3, SDK hoặc HTTP thật. Không đổi calibration, tọa độ/Z visual-correction-v2, hình học, collision, IK hoặc thuật toán quỹ đạo. Executor cánh tay và nhận diện camera trong các fault probes đều giả lập. Các test matrix kế thừa chạy PyBullet thật cho reconciliation bàn/quân, nhưng vẫn giả lập executor.

## Các lỗi đã tái hiện

| ID | Mức | Hành vi trước sửa | Thay đổi |
| --- | --- | --- | --- |
| RACE-01 | HIGH | main nhận QUIT, chỉ đặt `running=False`, vẫn xử lý các sự kiện còn lại. Cùng batch QUIT/F7 vẫn gọi request nước; QUIT/F6 vẫn khởi động controller | `main.py:278`: thoát ngay vòng xử lý sự kiện khi nhận QUIT |
| RACE-02 | HIGH | F6 chỉ kiểm tra thread còn sống. Khi thread đã xong nhưng `tick` chưa xử lý kết quả, start chuyển THINKING/MOVING về READY, tăng epoch và bỏ qua kết quả. Với MOVING, executor đã chạy một lần nhưng FEN còn cũ, pending vẫn còn | `src/core/self_play_controller.py:124`: từ chối start ở trạng thái đang sở hữu kết quả hoặc khi còn pending move; không đổi epoch/trạng thái/checkpoint |
| RACE-03 | HIGH | F6 có thể thay PICK_PAUSED bằng READY, kể cả đang giữ checkpoint đã dọn quân bị ăn | Cùng start guard giữ nguyên pause/checkpoint. Y tiếp tục retry đúng nước; F8 hoặc đối soát là đường kết thúc/phục hồi hiện hữu |
| RACE-04 | HIGH | Step/Continuous và THINKING completion không kiểm tra worker UI đang làm một job khác. Scheduler vẫn nhận nước hoặc chuyển MOVING trong khi job enable/startup/reconciliation còn chạy | `_ui_worker_busy` và guard tại `request_next_move`, `retry_visual_pick`, `tick`: trì hoãn dispatch, giữ kết quả cho đến khi worker UI được poll xong |
| RACE-05 | HIGH | Retry đã commit nhưng lấy baseline trả False/exception chỉ bị bỏ qua hoặc hiện dòng trạng thái. Mirror đã từ chối mà retry vẫn gọi capture baseline | `src/ui/input_handler.py:231`: giữ commit, dừng refresh khi mirror lỗi; camera baseline thất bại trong physical mode tạm dừng quét, yêu cầu V đối soát; không replay motion. Log `camera.baseline_rejected` có FEN/reason |
| RACE-06 | MEDIUM | Retry chiếu bí chỉ đặt winner Black, không gửi spectator end; nhánh gọi chung cho Red cũng bị gán sai winner | Dùng màu của pending move, đánh dấu game_over với CHECKMATE và gửi FEN trước end một lần; không lấy baseline sau terminal |

Các lỗi có sẵn trong snapshot trước vòng này. Chưa quy lỗi cho commit/nhánh nào vì không có bằng chứng lịch sử đủ rõ. Mức tin cậy **VERIFIED trong phạm vi lịch sự kiện và boundary phần mềm đã tái hiện**. RACE-04 chứng minh scheduler dispatch khi worker khác đang bận; không khẳng định đã quan sát hai chuyển động FR3 vật lý đồng thời.

## Bằng chứng ngoài bộ test kế thừa

`reports/runtime-race-review-20261013/probe_worker_schedule.py` chạy trực tiếp, không qua pytest. Nó nạp controller từ snapshot trước sửa và từ mã sau sửa, điều khiển lịch bằng join thread rồi gọi F6 trước tick. `worker-schedule.json` ghi từng bước: trạng thái, FEN, pending, số lần executor và số nước commit.

Baseline: cả THINKING và MOVING đều cho restart. Ở MOVING, executor đã chạy 1 lần nhưng commit 0 lần và pending còn tồn tại sau tick. Sau sửa: restart bị từ chối, kết quả cũ được commit đúng một lần. Thêm 100 lần replay lịch này đều giữ kết quả và commit đúng một lần. Đây là **mock executor**, không chứng minh gắp/đặt, motion completion firmware hoặc an toàn hình học.

Các ca QUIT chạy real main.py/Pygame headless với batch sự kiện thật; startup/devices/API đều thay bằng doubles. Đây là kiểm tra đường dispatch thực của GUI, không phải quan sát desktop/browser thật.

## Gates và giới hạn

Evidence ở `reports/runtime-race-review-20261013/`.

| Gate | Kết quả | Evidence |
| --- | --- | --- |
| Fault probes trên baseline | FAIL: 11 ca, exit 1 | `red.log` |
| Worker ownership trước guard bổ sung | FAIL: 3 ca, exit 1 | `owner-red.log` |
| Focused sau sửa ban đầu | PASS: 38 ca, exit 0 | `focused.log` |
| Subsystem trước guard bổ sung | PASS: 186 ca, exit 0 | `subsystem.log` |
| Bản source cuối, subsystem liên quan | PASS: 189 ca, exit 0; gồm 15 ca mới | `final-subsystem.log` |
| Standalone replay trước/sau và 100 lịch | PASS: exit 0 | `worker-schedule.log`, `worker-schedule.json` |
| Full regression trên source cuối | PASS: 1.044 song song + 8 tuần tự = 1.052 ca, exit 0; 547,66 giây | `full.log` |
| Parity/compile repo chính | PASS: 7 file source/test/docs khớp hash, compileall exit 0 | `delivery-verification.json`, `primary-compile.log` |

Các lệnh được ghi trong `commands.json`; Python 3.12.10, pytest 8.4.2, xdist 3.8.0, Windows. Runtime dùng thư viện môi trường hiện hữu; pytest chạy trong test venv của worktree, không cài thêm vào venv chính.

## Review và bàn giao

Delta production giới hạn ở 3 file: main, self-play controller và InputHandler. `production-delta.patch` so sánh với snapshot bắt đầu vòng này, không trộn patch kế thừa. Kiểm tra tuần tự callers, kết quả retry, trạng thái pending, shutdown, startup và API FIFO; không dùng subagents theo yêu cầu người dùng. Những thao tác start từ worker UI vẫn hợp lệ; chỉ dispatch tự chơi phải chờ worker UI nhả job.

Graph được dùng cho discovery/trace, sau đó đọc source thực: một số offsets của snippet đã cũ. `detect_changes` trả 397 đường dẫn kế thừa và 0 impacted symbols, không coi số 0 là không có ảnh hưởng. `code-locations.json` dùng số dòng từ file thật.

`tested-hashes.json` khóa production/test trước full gate. Copy về repo chính chỉ sau khi toàn bộ hash đích khớp baseline; xác minh lại hash và compile. Không commit/push, không xóa hoặc reset thay đổi cũ.

## Chưa kiểm chứng

Camera/FR3 thật, firmware trả completion, hạ kẹp/ăn/gắp/thả thật, calibration/parity đo thực, viewer/browser thật và spectator remote ACK đều **NOT RUN trong vòng này**. Lệnh SDK đã gửi trước QUIT không được hủy bởi patch này; UI dừng scheduling không chứng minh cánh tay đã dừng vật lý. Không suy ra toàn dự án hết lỗi từ các gates trên.
