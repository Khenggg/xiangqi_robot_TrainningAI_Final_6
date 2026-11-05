# Đọc tư thế hiện tại và đánh giá tiếp tục — 2026-10-30

**READ-ONLY. Không có lệnh servo/Mode/Move*/gripper/ResetAllError/StopMotion.**

Đây là phép đọc sau khi user đã mở lại ứng dụng: phiên log mới
`20261030_202855_7a8a6252`, game session `31e809eb2960402795207b3eca6c40c4`.
Không trộn sự cố LAND/112 lúc 20:31 với sự cố APPROACH/14 lúc 20:03 của phiên cũ.

## 1. Tư thế đã đọc

Mẫu cuối được kiểm chứng lúc **20:40:28.817 +07:00**. Năm mẫu PHYSICAL mới, connected,
joints_valid và tcp_valid true; tuổi mẫu lớn nhất 0,107 giây. Dao động khớp trong
cửa sổ này dưới 0,00023°. Nguồn: [latest-verified-state.json](latest-verified-state.json).

| Đại lượng | Giá trị |
|---|---|
| J1–J6, độ | `[39.336060, -193.810791, 66.309341, -74.555618, -87.618248, -46.047291]` |
| TCP X/Y/Z, mm | `[348.601471, 148.442383, 395.615723]` |
| TCP Rx/Ry/Rz, độ | `[-59.304497, -42.691784, 109.979523]` |
| Trạng thái controller qua telemetry | `ERROR / Controller E-Stop active` |
| Quyền lệnh qua ứng dụng | `commands_allowed=false` |

Tọa độ TCP được đối chiếu bằng phép tính read-only `GetForwardKin(J1..J6)` của
controller, trả cùng pose tới sai số làm tròn khoảng 0,00001 mm/độ. Vì vậy đây
không phải vị trí quân/tay giả lấy từ world_state của mô phỏng. Dùng hệ quy chiếu
base cho các phép FK/IK type=0; đơn vị mm/độ; gốc và trục theo robot base controller.

Lệnh `GetRobotErrorCode()` riêng trả `[0,5,1]`: RPC thành công, main=5/sub=1.
Không tự diễn giải cặp main/sub bằng bảng SDK return-code. Truy vấn trực tiếp
GetActual* trong trạng thái này trả code 14 và các số 0; các số 0 đó **bị loại**,
không được dùng làm pose. Nguồn: [direct-read-queries.json](direct-read-queries.json).

## 2. Đích mà chương trình vừa yêu cầu

Phiên mới bắt đầu nước Pháo Đen `(col,row)=(7,2)→(4,2)` lúc 20:30:56.758.
Camera đo tâm nguồn `(7.025340,2.013013)`. Tính lại bằng đúng công thức bilinear,
fixed profile, OFFSET và rotation của source hiện tại cho:

| Giai đoạn | TCP đích trong robot base, mm/độ |
|---|---|
| Tiếp cận | `[-115.468451, 506.924275, 220.0, 180.0, 0.0, -73.2]` |
| Hạ gắp | `[-115.468451, 506.924275, 178.0, 180.0, 0.0, -73.2]` |

Đây là **đích tái dựng offline**, không phải một lệnh được gửi trong điều tra.
Live tool/user ID chưa đọc độc lập được vì GetActualTCPNum/GetActualWObjNum trả 14;
lệnh của ứng dụng dùng tool 0/user 0 theo profile đã ghi log. Không đổi frame.

Từ pose đọc được tới đích tiếp cận, chênh lệch tịnh tiến là
`[-464.070,+358.482,-175.616] mm`, khoảng cách endpoint **612,136 mm**. So sánh
orientation bằng ma trận `Rz @ Ry @ Rx`, không trừ Euler thô: góc tương đối
**141,585°**. Đây không phải chỉ một thao tác hạ thẳng 42 mm trong tư thế hiện tại.

## 3. Tính nghiệm chỉ đọc trên controller

Tất cả hàm dưới chỉ tính toán, không gọi motion. Kết quả được lặp lại với mẫu
khớp mới ở trên; [analysis.json](analysis.json) lưu đầy đủ args/result/thời điểm.

| Phép tính | Kết quả |
|---|---|
| FK của khớp hiện tại | Code 0, khớp TCP telemetry |
| IKRef type=0 tới tiếp cận, tham chiếu khớp hiện tại | **112**, không nhận nghiệm |
| IKRef type=0 tới hạ gắp, tham chiếu khớp hiện tại | **112**, không nhận nghiệm |
| IK config=-1 tới tiếp cận/hạ, lần đọc 20:39 | **112** cả hai |
| IKRef tới tiếp cận, tham chiếu khớp HOMECHESS lưu | Code 0; nghiệm `[-88.482109,-52.254395,62.189110,-99.934715,-90.0,74.717888]` |
| IKRef tới hạ, tham chiếu khớp HOMECHESS lưu | Code 0; nghiệm `[-88.482109,-49.928982,68.458206,-108.529228,-90.0,74.717888]` |

FAIRINO mô tả code 112 là “The given pose cannot be reached”. Không đổi nghĩa thành
"không tồn tại bất kỳ nghiệm hình học nào": chính phép thử tham chiếu HOME tìm
được nghiệm, trong khi tham chiếu hiện tại không tìm được.
[Bảng mã lỗi chính hãng](https://manual.fairino.support/latest/SDKManual/errcode.html),
[API IK/FK và ý nghĩa tham chiếu](https://manual.fairino.support/latest/SDKManual/PythonRobotStatusInquiry.html).

**Giới hạn:** IK thành công chỉ xác nhận có nghiệm điểm đích theo phép tính đó,
không xác nhận đường từ tư thế hiện tại tới nghiệm/HOME an toàn. Không gửi nghiệm
này cho robot, không tự chuyển config, không tự chạy HOME.

## 4. Vì sao có thể cho ra tư thế khác

**VERIFIED trong source:**

- `src/hardware/robot_VIP.py:L618-L640`, `move_safe_pose()` gọi
  `MoveCart(...config=-1)`; không đưa vào một nghiệm khớp tham chiếu đã được kiểm
  chứng và không kiểm đích feedback sau lời gọi.
- `src/hardware/robot_VIP.py:L667-L687`, **`movel_pose()` cũng gọi MoveCart**,
  dù tên/comment hàm thể hiện chuyển động thẳng/đứng. Vì vậy bước LAND không có
  bảo đảm tuyến tính từ việc đặt tên hàm.
- FAIRINO phân loại MoveCart là point-to-point; `config=-1` dùng current joints
  làm tham chiếu. MoveL là API linear riêng. Không suy từ đây rằng đổi sang MoveL
  một cách máy móc sẽ an toàn từ tư thế bất kỳ.
  [Tài liệu chuyển động](https://manual.fairino.support/latest/SDKManual/PythonRobotMovement.html).
- Trước lệnh đầu, startup/activation chưa xác nhận robot ở cấu hình khớp khởi đầu
  và tuyến tiếp cận đã được kiểm chứng. Điều tra trước nêu chi tiết tại
  `reports/powerloss-incident-20261030/REPORT.md`.

**VERIFIED trong log phiên mới:** APPROACH bắt đầu 20:30:58.854, hàm trả thành
công lúc 20:31:01.431; LAND bắt đầu 20:31:01.432 rồi trả MoveCart **112** lúc
20:31:01.449. Log không lưu measured endpoint/joints tại thời điểm đánh dấu
APPROACH completed; return code 0 tự nó chưa phải bằng chứng robot đã đạt pose đích.
Nguồn: [latest-session-events.json](latest-session-events.json), source events dòng
172–178 của phiên `20261030_202855_7a8a6252`.

**Suy diễn có căn cứ, chưa chứng minh:** tư thế hiện tại có thể là tư thế trung
gian sau một chuyển động PTP hoặc thao tác dừng/khởi động lại; cách gập tay phụ
thuộc cấu hình khớp xuất phát, thay vì giữ một nhánh đã được kiểm chứng. Nó khác
HOME đáng kể, ví dụ J1 lệch khoảng +128,8°, J2 lệch khoảng -65,2°. Không tự gán
J2<-180° là vượt giới hạn: phải dùng giới hạn controller thực tế, không chuẩn hóa
góc tùy tiện để che vòng quay của khớp.

**Chưa xác định được nguyên nhân lịch sử duy nhất:** không có chuỗi actual joints,
planned intermediate path, thời điểm nhấn E-Stop hoặc video ở sự cố. Không thể
khẳng định controller đã chọn chính xác nhánh nào hay khâu nào chạm vật gì.

## 5. Các điểm lưu cố định có bị lệch số không

Tính FK của bộ joints lưu cho HOMECHESS và R1–R4 trên controller rồi so với pose
lưu trong cùng artifact: sai số XYZ lần lượt khoảng 0,00268; 0,00221; 0,00250;
0,00106; 0,00490 mm. [reference-cross-check.json](reference-cross-check.json).

Điều này xác nhận bộ số pose/joints đang nhất quán động học, không cho thấy một
sai lệch số lớn do F12 hoặc dọn phiên. Nó không chứng minh bàn/gá/TCP vật lý vẫn
đúng sau va chạm, và không chứng minh đường HOME từ tư thế hiện tại an toàn.

## 6. Nếu tiếp tục

1. **Giữ trạng thái hiện tại:** E-Stop/fault và `commands_allowed=false` đang
   chặn ứng dụng; không có chuyển động tiếp theo được cho phép trong trạng thái đọc.
2. **Nếu xóa lỗi/bật lại rồi cố gửi cùng kiểu lệnh:** các phép IK chỉ đọc từ
   tư thế đang đo đã trả 112; không có cơ sở bảo đảm sẽ trở lại tư thế gắp cũ.
   Ghi đè config/ép một nhánh khác có thể đòi hỏi quay khớp rất lớn và chưa có
   kiểm chứng va chạm trên đường. Không thực hiện để "thử xem".
3. **Muốn phục hồi để chơi:** cần xác minh cơ khí/payload/frame và tuyến phục hồi
   có giám sát; sau đó mới xét chuyển động game. Đây không phải lý do để tự chạy
   HOME hoặc nhả E-Stop từ công cụ điều tra.

## 7. Phương pháp và phạm vi kiểm chứng

- Đầu tiên thử nghe cổng state 20004 trực tiếp nhưng không nhận đủ frame hợp lệ;
  đã loại kết quả này, không gán số 0 thành tư thế thật.
- Đọc WebSocket telemetry của ứng dụng đang chạy, chỉ receive, không gửi command.
- XML-RPC chỉ dùng allowlist `GetActual*`, `GetRobotErrorCode`, `GetForwardKin`,
  `GetInverseKin`, `GetInverseKinRef`, bounded single-attempt transport. Không tạo
  SDK owner/FR5Robot connection để điều khiển. Model FR5Robot dùng dry_run và chỉ
  load file cố định để tái dựng số mục tiêu offline.
- Direct GetActual* bị từ chối được lưu nguyên, không dùng làm giá trị hiện tại.
- Không mở lại journal đã dọn, không sửa runtime/calibration, không chạy app,
  không thay đổi E-Stop/servo/controller/gripper, không phát motion.
- **NOT RUN:** physical replay, validation đường đi thật, collision simulation
  tương đương phần cứng, full regression. Các phép toán điểm đích không thay thế
  các kiểm chứng đó. Không tuyên bố robot an toàn để tiếp tục.
