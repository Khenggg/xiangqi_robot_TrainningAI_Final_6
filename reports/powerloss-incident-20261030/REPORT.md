# Sự cố chuyển động sau mất nguồn / khởi động lại — 2026-10-30

**Trạng thái: điều tra read-only; chuyển động vật lý chưa được xác minh an toàn.**

User xác nhận robot đổi sang tư thế khác thường rồi **va chạm với vật thật** khi thực hiện nước đi sau restart/F12. Đây không chỉ là một thông báo collision của controller. Không suy rằng controller đã phát hiện/chặn va chạm chỉ từ return code 14.

Kết luận có bằng chứng: F12 đã giải quyết khóa đối soát của phiên mới, sau đó nước AI đầu tiên thất bại tại `APPROACH / MoveCart`, trước bước hạ xuống gắp. FEN và tâm quân đã đạt các kiểm tra camera. Có lỗ hổng kiểm soát đường tiếp cận đầu tiên: code dispatch `MoveCart(config=-1)` mà không có contract xác minh tư thế khớp khởi đầu/đường đi sau gián đoạn. Đây là cơ chế có thể giải thích chuyển động khác sau restart, **chưa phải bằng chứng xác định duy nhất nguyên nhân cơ học của lần va chạm**.

## Phạm vi và bảo toàn bằng chứng

- Múi giờ trong bảng: Asia/Saigon, UTC+07. JSON gốc ghi UTC.
- Kiểm tra cửa sổ user yêu cầu quanh 20:01–20:04, mở rộng về phiên trước để nối nguyên nhân khóa sau restart và so sánh nước từng chạy được.
- Log hiện tại: `logs/20261030_195909_fa166362/`; phiên trước: `logs/20261030_194752_c0bda222/`.
- Bản chụp log theo bytes và manifest SHA-256: `logs/incident_20261030_2008/`. Snapshot nằm trong vùng logs, không sửa log nguồn.
- Journal PHYSICAL được backup bằng SQLite read-only source vào `logs/incident_20261030_2008/physical-journal-snapshot.sqlite3`; không sửa DB đang chạy, không lấy lock để ghi lên DB nguồn.
- Event chọn lọc: [selected-events.json](selected-events.json). Hash runtime/calibration lúc kiểm tra: [source-hashes.json](source-hashes.json).
- HEAD runtime trong cả hai log: `18e67fc9006a91a2a32c4c861974760089a687de`, tracked changes true. Tám file runtime của review trước vẫn cùng SHA-256 trong kiểm tra hiện tại. Không merge donor PvP và không sửa production trong điều tra này.

## Chuỗi sự kiện được xác minh

| Giờ địa phương | Bằng chứng | Ý nghĩa |
|---|---|---|
| 19:49:38–19:49:49 | Phiên trước events dòng 74, 131 | Nước Pháo Đen `(7,2)→(4,2)` đã chạy và commit. Đây cũng là nước sẽ lỗi sau restart. |
| 19:53:33.338 | Phiên trước events dòng 402 | Nước khác `(4,6)→(4,5)` bị chặn: `Robot telemetry stale/faulted; no new command dispatched`. Log chứng minh mất/không đạt telemetry; riêng dữ liệu này không phân biệt mất điện với mất link. Mất điện là thông tin user cung cấp. |
| 19:56:39.003 | Phiên trước events dòng 425 | `StopMotion: controller reply unavailable; outcome unknown, do not resend`; yêu cầu recovery. |
| 19:59:59.349 | Phiên mới events dòng 10 | Tạo session mới/FEN khai cuộc; `operator_inspection_required=true`. Không nạp lại ván cũ. |
| 20:00:00.466 | Phiên mới events dòng 19 | Load cùng fixed profile `fr3-fixed-user0-20261028`, tool 0/user 0. |
| 20:01:54.732 | Phiên mới events dòng 60 | F9/F10 bị từ chối: `Resolve pending motion or board synchronization first`. Đây là khóa recovery, không phải camera đếm thiếu quân. |
| 20:02:30.142 | Phiên mới events dòng 68 | `session.cleared_failed`, revision 0: tương ứng thao tác F12. Trước đó có xác thực bàn thành công. |
| 20:02:57.831 | Phiên mới events dòng 72 | `physical.enabled`: quyền chuyển động được bật sau xác nhận. |
| 20:03:48.906 | Phiên mới events dòng 81 | Nước người Tốt Đỏ `(4,6)→(4,5)` được commit. |
| 20:03:49.380 | Phiên mới events dòng 88 | Nước AI Pháo Đen `(7,2)→(4,2)`, ID `fedd5d75ff254759a989604abd14e12f`, bắt đầu. Đây là lệnh mới, không phải replay nước chờ cũ `229b6379...`. |
| 20:03:49.999 | Phiên mới events dòng 89–91 | Hai mẫu liên tiếp khớp FEN; confidence quân thấp nhất xấp xỉ 0,883. |
| 20:03:50.971 | Phiên mới events dòng 99 | Ba mẫu tâm nguồn ổn định: `(6.947635,1.940940)`, confidence khoảng 0,852, spread khoảng 0,00120 ô. |
| 20:03:51.006–20:03:51.726 | Phiên mới events dòng 106–108 | Mở ngàm ban đầu, stage PREPOSITION hoàn tất. |
| 20:03:51.734 | Phiên mới events dòng 109 | Bắt đầu APPROACH qua `move_safe_pose`. |
| 20:03:54.567 | Phiên mới events dòng 111 | `Robot MoveCart error code: 14`, stage APPROACH, last completed PREPOSITION, payload NONE. Không có LAND/GRIP thành công cho nước này. |

Nguồn trực tiếp dễ xem: `logs/20261030_195909_fa166362/run.log:L184-L251`, `errors.log:L11-L24`, `errors.log:L31-L63`. Line trong bảng events trỏ tới bản snapshot đã chốt; log nguồn tiếp tục được append có thể dài hơn.

## F12 đã làm gì, và chưa chứng minh điều gì

`src/ui/input_handler.py:L1100-L1149` xác minh bàn/FEN qua `_verify_recovery_board()` (`L695-L710`), rồi xóa giao dịch/latch lỗi và lấy baseline mới. Việc approve recovery tại `src/core/game_persistence.py:L510-L528` kiểm tra idle telemetry và stop barrier. Vì vậy không đúng nếu nói F12 hoàn toàn bỏ qua camera/stop; các gate đó có chạy.

Tuy nhiên idle telemetry chỉ chứng minh robot đang đứng yên với dữ liệu mới, **không chứng minh tư thế đó thích hợp để bắt đầu đường tới quân**. F12 không kiểm nghiệm đường quét của các khâu tay từ tư thế hiện tại đến mục tiêu; không phải thao tác khôi phục tư thế robot hay xác minh toàn bộ không gian chống va chạm.

`activate_physical_game()` (`src/hardware/hardware_manager.py:L501-L564`) tiếp tục kiểm pending, telemetry idle, board và stop generation, rồi bật robot. Nó cũng không có gate yêu cầu tư thế khởi đầu hoặc first-approach path đã được xác minh. `MOTION_PROFILE_VERIFIED=False` hiện chỉ tạo warning tại `_init_robot()` (`L195-L202`), không phải một cổng riêng chặn first approach sau mất nguồn.

Nhận định **VERIFIED (software behavior):** khóa ban đầu giữ lại trạng thái cần recovery từ phiên trước; sau F12 và F9/F10 app cho phép một lệnh AI mới. Không có bằng chứng F12 đổi R1–R4, sửa user frame, gửi MoveCart hay tự chạy lại lệnh cũ.

## Lỗ hổng đường tiếp cận và tư thế

**Vị trí:** `src/hardware/robot_VIP.py:L618-L640`:

```python
err = self.robot.MoveCart(
    desc_pos=pose, tool=self.tool_num, user=self.user_num,
    vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
)
```

Comment/docstring ở hàm này tuyên bố MoveCart bảo đảm đường thẳng. Tài liệu FAIRINO phân biệt rõ `MoveL` là Cartesian linear motion, còn `MoveCart` là Cartesian point-to-point; `config=-1` giải theo vị trí khớp hiện tại. Do đó không thể dùng comment đó làm bảo đảm quỹ đạo thẳng hoặc đường quét các khâu tay không va vào vật cản. Nguồn: [FAIRINO Python Movement, mục 4.6 và 4.9](https://manual.fairino.support/latest/SDKManual/PythonRobotMovement.html).

`pick_at()` (`L835-L866`) tạo mục tiêu trên quân ở Z tuyệt đối `SAFE_Z=220mm`, rotation `[180,0,-73.2]`, rồi gọi hàm trên. Z của TCP tại đích không chứng minh độ hở của mọi khâu tay trên cả đường. `_validate_pose()` (`L249-L256`) chỉ kiểm sáu số hữu hạn và giới hạn XY; nó không kiểm quỹ đạo hoặc tư thế khớp.

`_move_piece_sequence()` (`L976-L980`) đọc/kiểm frame HOMECHESS trước lệnh, nhưng chưa đưa tay về HOME và cũng chưa xác nhận tay đang ở vùng khởi đầu được phép. HOME chỉ là bước retreat sau khi đặt xong. Đây là lựa chọn read-only startup có chủ đích; **không khắc phục bằng cách tự chạy HOME từ một tư thế chưa xác minh**.

**Mức độ: HIGH safety gap; confidence HIGH về control-flow, MEDIUM về vai trò gây ra lần va chạm cụ thể.** Nếu sau mất nguồn/di chuyển thủ công tư thế khớp khởi đầu khác trước, việc giải từ current joints có thể dẫn tới cách gập/xoay khác. Chưa có ghi hình/góc khớp trước và trong sự cố để chứng minh controller đã chọn một nghiệm IK khác, cổ tay lật hay khâu nào va vào đâu.

## Các yếu tố đã đối chiếu

- Cùng nước Pháo từng chạy được ở 19:49 và thất bại ở 20:03; không phải AI đưa ô nguồn/đích hoàn toàn mới.
- Journal execution bindings của hai phiên có cùng `calibration_token=60392b55757fc7e7a70269615362bce202c2017cf69f792e9e53495464ace31c` và cùng camera calibration token `5417d66bc23538ff450e835dae0ff784083e8a309fe459f38803a9f3cf98c257`.
- Bù camera nguồn trước sự cố xấp xỉ `(-2.440,-2.138)mm`; ở lần trước là `(-0.950,-0.687)mm`. Chênh lệch bù giữa hai lần khoảng `(-1.489,-1.451)mm`. Không thấy sự thay đổi lớn về tâm từ log. Các số này không tự chứng minh calibration vật lý đang đúng sau va chạm.
- Cả hai phiên đều báo mirror chưa có measured dimensions/provenance/surface Z. Viewer không cung cấp bằng chứng đã kiểm chứng đường đi physical; không suy rằng PyBullet đã chặn lệnh thật này.
- Journal hiện còn pending nước `fedd5d75...`, phase RECOVERY_REQUIRED, chưa có committed move tương ứng. Giữ nguyên receipts, không xóa để thử chạy lại.

## Mã 14 và dữ liệu còn thiếu

FAIRINO SDK 3.9.2 mô tả mã 14 là **Interface execution failed**, cần kiểm lỗi trên WebApp/state feedback. Đây là mã thất bại chung, không đủ để gán nhãn collision, singularity hay mất zero. Nguồn: [bảng mã lỗi FAIRINO](https://fairino-doc-en.readthedocs.io/3.9.2/SDKManual/errcode.html). Chưa có firmware version/controller main_code/sub_code của thời điểm sự cố nên không ép ánh xạ từ một bảng SDK sang nguyên nhân vật lý chắc chắn.

Log này không giữ được current J1–J6/TCP lúc bắt đầu APPROACH, actual intermediate joint trajectory, IK branch được controller chọn, controller fault/subfault ngay khi trả 14 hoặc video va chạm. Không thể tái tạo đường thực tế từ endpoint/FEN một cách đáng tin cậy. User cũng xác nhận vấn đề là va chạm ngoài đời, không cung cấp một alarm collision.

## Hướng sửa cần thiết trước khi chạy lại

1. Tách "bàn/FEN đã xác nhận" khỏi "robot đã được phục hồi tư thế/payload sau gián đoạn". Sau restart/mất link cần latch phục hồi robot riêng; F12 không được dùng làm bằng chứng quỹ đạo an toàn.
2. Chỉ cho phép chuyển động đầu tiên sau khi có trạng thái khớp/TCP mới, frame/tool/payload hợp lệ và đường từ start đến mục tiêu đã được kiểm chứng. Nếu thiếu bằng chứng, chặn lệnh và yêu cầu kiểm tra thủ công. Không tự giả định HOME luôn tiếp cận được.
3. Dùng chính sách route/IK branch và kiểm giới hạn/va chạm phù hợp cho physical. Không thay mù `MoveCart` bằng `MoveL`, không cố định một giá trị config 0–7 chưa được xác minh, không tắt chống va chạm để thử.
4. Ghi structured dispatch evidence: actual start joints/TCP, full commanded target, tool/user, motion primitive/config, speed và fault/main/sub ngay khi lỗi. Khả năng ghi log không được phụ thuộc truy vấn mạng chặn vô hạn.
5. Trước thử nghiệm có chuyển động: kiểm tra tình trạng robot/ngàm/bàn/gá sau va chạm, commissioning lại đường khởi đầu theo quy trình có giám sát. Không coi profile cũ hoặc 32 quân đúng là xác nhận cơ khí vẫn giữ nguyên.

Đây là đề nghị sửa, **chưa áp dụng production patch**. Không xác nhận robot hiện tại an toàn và không thực hiện bất kỳ lệnh robot/gripper nào.

## Kiểm chứng offline

Workflow `fast-testing`, gate evidence trước kết luận theo `code-review`:

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv312\Scripts') + ';' + $env:PATH
$env:PYTEST_ADDOPTS = '-x'
.\tools\test_fast.ps1 -Workers 2 -Tests reports/powerloss-incident-20261030/test_incident_boundaries.py
```

**PASS, exit 0:** 3 parallel probes, không có test serial; runner 14,8 giây. Windows/Python 3.12.10, pytest 9.1.1, xdist 3.8.0. [Probe source](test_incident_boundaries.py), [output](probe-output.txt), [command/result](probe-result.json).

Các probe xác nhận (1) helper chuyển lệnh MoveCart với config -1 mà không có joint/path-query trên fake SDK; (2) enable gate chấp nhận idle+board match mà không có start-pose/path contract; (3) lỗi ở APPROACH không chạy LAND/GRIP. PASS xác nhận hành vi phần mềm hiện tại, không xác nhận quỹ đạo an toàn và không tái hiện va chạm vật lý.

**NOT RUN:** hardware calls, physical movement, controller reconnect/query, full regression, production fixes. Trạng thái cần giữ: **NO MOTION — MANUAL VERIFICATION REQUIRED**.
