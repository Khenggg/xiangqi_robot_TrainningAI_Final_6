# Rà soát bổ sung vòng đời game — 12/10/2026

## Snapshot và phạm vi

- Repo chính: `D:/OJT/xiangqi_robot_TrainningAI_Final_6`, nhánh `feature/unified-robot-vs-robot`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e` cộng các thay đổi chưa commit hiện có.
- Reuse worktree `D:/OJT/_reliability_fix_20261012`. Hash các file liên quan khớp repo chính trước sửa; baseline mới là `reports/reliability-fixes-20261012/edge-baseline.json`.
- Chỉ thay `main.py`, `src/core/game_state.py`, `src/ui/input_handler.py`, thêm test và tài liệu. Không đổi API robot, mapping visual, chiều cao gắp, calibration, geometry, kinematics hoặc collision guard.
- Mock toàn bộ camera, robot và API spectator trong các ca mới. Không kết nối hay điều khiển FR3; không tạo phòng trên dịch vụ thật.

## Năm nhóm lỗi đã tái hiện và sửa

| Nhóm | Lỗi và tác động trước sửa | Sửa / vị trí mã | Bằng chứng và độ tin cậy |
| --- | --- | --- | --- |
| Kết thúc ván người đi | `process_human_move` chỉ nhận tướng biến mất, không kết thúc khi đối phương còn tướng nhưng hết nước hợp lệ. Khi ăn tướng, game local kết thúc nhưng spectator thiếu end. HUMAN_VS_HUMAN không có vòng AI để phát hiện thay. Emergency Đen có cùng thiếu sót | `_finish_human_committed_move`, `src/core/game_state.py:489`: dùng luật hiện hữu, ghi winner và gửi FEN trước end; dùng cho human và Emergency | Thế chiếu bí thật qua `is_valid_move`/`find_all_valid_moves`, hai màu; ăn tướng; duplicate coordinator không phát end lần hai. **VERIFIED bằng thực thi logic**, chưa phải camera thật |
| Điều kiện tiếp nhận nước đi | Gọi trực tiếp các entrypoint có thể tiếp tục sau game_over; Emergency Đen thiếu kiểm tra luật và sửa FEN dù nước sai. Yêu cầu xác nhận lượt chưa được chặn độc lập. Emergency Đỏ bị từ chối do fault vẫn có thể xóa pending recovery | `process_human_move` ở dòng 443 và `process_emergency_move` ở dòng 496: kiểm tra trạng thái/lượt/luật trước thay đổi; giữ pending nếu từ chối | Các ca bất biến board, identities, history, pending và API sau rejection. **VERIFIED** |
| Rollback / undo | Snapshot trước SPACE không chứa stack undo. Rollback khôi phục board nhưng để lại snapshot của nước đã hủy; undo sau đó có thể nhảy tới nhánh cũ. Trạng thái winner/game_over không được khôi phục cùng snapshot | `save_rollback_state` dòng 230, `handle_rollback` dòng 251: lưu và khôi phục bản sao lịch sử và trạng thái kết thúc | Chuỗi Red đi → lưu snapshot → Black đi → rollback → undo trở lại bàn ban đầu với stack rỗng. **VERIFIED cho chuỗi lịch sử**; các trường kết thúc được review trực tiếp |
| Emergency / lỗi mirror | Emergency Đen bỏ qua kết quả sync; GUI coi mọi lời gọi Emergency là thành công và có thể lấy baseline sau rejection | Update FEN trước mirror, giữ sync fault và trả False nếu mirror từ chối; chỉ lấy baseline nếu entrypoint trả True; `src/ui/input_handler.py:246` | Ca mirror từ chối giữ nước đã ghi local cùng lỗi, không gửi spectator; ca click mouse Emergency bị từ chối không capture baseline. **VERIFIED** |
| Thoát bằng Q của camera | Camera Q chỉ đặt running=False rồi vẫn chạy auto-confirm/AI trong cùng frame. Khi AI result đã sẵn sàng, dispatcher vẫn xếp một lệnh sau yêu cầu thoát | `main.py`, ngay sau `cam_monitor.update_display`: break trước các khối xác nhận/AI | Chạy `main.py` và vòng lặp Pygame headless thật; Q sau startup khi worker rảnh và AI result sẵn sàng. Trước sửa dispatcher fake bị gọi 1 lần; sau sửa 0. **VERIFIED ở ranh giới dispatch**, không mô tả việc dừng một lệnh robot đã chạy trước Q |

Các lỗi trên tồn tại ở baseline trước vòng rà soát này. Không quy lỗi cho commit mới nào khi không có bằng chứng lịch sử. F6 ở chế độ người chơi được giữ vì giao diện hiện tại công bố đó là shortcut self-play; vòng này không tự đổi hành vi đó.

## Kiểm chứng

Môi trường: Windows, Python 3.12.10, pytest 8.4.2 / xdist 3.8.0 trong `.testvenv` riêng của worktree, thư viện runtime từ `.venv312` hiện hữu. Các test phần cứng thật luôn bị loại trừ.

| Lệnh / gate | Kết quả | Evidence trong `reports/reliability-fixes-20261012/` |
| --- | --- | --- |
| 10 ca mới trước sửa | FAIL: 9 lỗi, 1 pass; fixture Q ban đầu chưa đợi worker rảnh nên chưa bắt được lỗi | `edge-red.log` |
| Q với fixture đã đợi đúng boundary | FAIL: dispatcher gọi 1 lần sau Q, exit 1 | `edge-quit-red-2.log` |
| Marker tên test dùng nhầm `-m` | NOT RUN, exit 5; sửa lựa chọn bằng node id, không sửa production để né test | `edge-quit-red.log` |
| Gate tập trung sau sửa | PASS: 50 test, exit 0 | `edge-focused.log` |
| Gate subsystem trên bản cuối | PASS: 142 test, exit 0; gồm 15 ca mới và regression camera/game/rollback/recovery/self-play/spectator | `edge-subsystem.log` |
| Hồi quy cuối | PASS: 1.011 song song + 8 tuần tự = 1.019 test; exit 0; 492,23 giây | `edge-full.log` |
| Compile / parity repo chính | PASS: compileall exit 0; 7 file bàn giao khớp hash | `edge-primary-compile.log`, `edge-delivery-verification.json` |

Lệnh chạy từ worktree (runner giới hạn numerical threads và tách serial/hardware):

```powershell
$env:PATH=(Join-Path (Get-Location) '.testvenv/Scripts')+';'+$env:PATH
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/edge-subsystem --tb=short'
./tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_review_lifecycle_edges.py,tests/unit/test_reliability_recheck.py,tests/unit/test_reliability_audit_fixes.py,tests/unit/test_self_play_merge_contract.py,tests/unit/test_self_play_twin_contract.py,tests/unit/test_spectator_lifecycle.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_physical_camera_commit_gate.py,tests/unit/test_board_profile_recovery.py,tests/unit/test_pikafish_and_undo.py,tests/test_human_commit_ai_handoff.py,tests/test_capture_fen_sync.py,tests/test_emergency_client_move.py,tests/test_human_move_confirmation.py
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/edge-full --tb=short'
./tools/test_fast.ps1 -Mode Balanced -Tests tests
```

## Review / bàn giao

Review trực tiếp `edge-delta.patch` so với bản repo chính trước vòng này, không dùng toàn bộ diff kế thừa với HEAD làm delta của task. Các điều kiện dừng và sync fault còn được giữ. Return False của mirror có thể xảy ra sau khi board local đã thay đổi; không được hiểu là permission gửi lại một lệnh robot. GUI dùng kết quả đó để giữ recovery, không làm mới baseline thành công giả.

Graph index hiện có đã được dùng cho discovery/tracing trước sửa, nhưng có symbol cũ và snapshot trong reports. `detect_changes` sau sửa ở worktree trả 396 changed paths gồm thay đổi kế thừa và 0 impacted symbols; không lấy số 0 làm bằng chứng không có ảnh hưởng. Source trên đĩa và 142 ca subsystem là bằng chứng chính. Không phát hiện blocker trong delta đã review.

Hash source tại gate cuối: `edge-tested-source-hashes.json`. Bàn giao có preflight hash tất cả đích trước khi copy và đối chiếu sau copy: `edge-delivery-manifest.json`, `edge-delivery-verification.json`. Các thay đổi giữ ở trạng thái chưa commit; không ghi đè calibration hoặc thay đổi của người khác.

## Giới hạn thực tế

- **NOT RUN:** camera/FR3 thật, chuyển động vật lý, gắp/ăn quân thật, HTTP spectator thật và độ khớp bàn/quân với ngoài đời.
- Q ngăn dispatch mới trong frame sau yêu cầu thoát; Q không chứng minh controller dừng chuyển động đã được gửi trước đó. Cơ chế chờ worker/cleanup hiện hữu vẫn áp dụng.
- Test terminal ăn tướng kiểm chứng game logic; không chứng minh detector/camera thật chấp nhận board thiếu tướng. Các gate fresh frame, quality và sanity trong vision không được nới ở vòng này.
- Đây là rà soát các boundary đã nêu, không phải bằng chứng mọi kịch bản đều không lỗi. Cảnh báo WebSocket legacy API vẫn có; không đổi dependency.
