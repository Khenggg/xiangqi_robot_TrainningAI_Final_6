# Kiểm tra ảnh hưởng chéo các chức năng ngày 04–05/10/2026

## Kết luận

Đã tìm và sửa hai lỗi tương tác mới của launcher game-only với thao tác tạo ván mới/rollback, cùng một lỗi cũ giữ snapshot SPACE từ ván trước. Trong phạm vi đã chạy, chưa thấy logging, R1–R4, đồng bộ quân và capture làm hỏng nhau. **Regression toàn bộ chưa xanh**: còn một test Python và ba test Node lỗi giống bản nền sạch. Không suy ra khả năng chơi mọi nước hoặc an toàn FR3 thật từ kết quả này.

## Phạm vi và bản mã

- Nhánh chính: `feature/unified-robot-vs-robot`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e`.
- Đối chiếu thay đổi đã commit từ merge `56abf61` đến HEAD: giao diện cửa sổ, thao tác offline, tuyến approach, capture/disposal, settling, quyền sở hữu world và ngàm mở 27,5 mm.
- Đối chiếu thêm thay đổi đang làm ngày 05/10: launcher, logging, đồng bộ camera/game/robot, điều khiển quyền phần cứng và GUI R1–R4. Thay đổi chưa commit được kiểm tra như mã đang phát triển, không gán là bằng chứng của HEAD sạch.
- Thực thi tại worktree `D:/OJT/_simple_launch_sync_20261005`; đối chứng HEAD sạch tại `D:/OJT/_simple_launch_baseline_20261005`.
- Không kết nối/điều khiển FR3 thật; kiểm tra phần cứng chỉ dùng mock. Không thay đổi tab viewer 8088 của người dùng.
- Graph MCP được dùng để tìm/đối chiếu module và `detect_changes`. Graph còn cũ, trả khoảng 357 file so với mốc index; phạm vi thực tế lấy từ Git diff và đọc source, không coi kết quả graph là 357 file vừa sửa hôm nay.

## Lỗi tìm được và cách sửa

| Nhận định | Bằng chứng | Sửa | Mức tin cậy |
|---|---|---|---|
| `--virtual` + Ván mới bị khóa vì yêu cầu camera | Test trước sửa: `[True-reset]` lỗi; `reset_game` coi mọi `simulation_runtime=None` là phần cứng | Chỉ nhận game-only khi đồng thời `GAME_ONLY is True`, `ROBOT_BACKEND=VIRTUAL`, `dry_run is True`; bỏ yêu cầu camera trong trường hợp này | Cao, tái hiện và kiểm tra lại |
| `--virtual` + Z rollback bị khóa tương tự | Test trước sửa: `[True-rollback]` lỗi | Dùng cùng điều kiện; game-only không phục hồi baseline camera. Undo game-only đi theo nhánh đồng bộ logic, không hiện yêu cầu xác minh camera | Cao |
| Ván mới còn snapshot SPACE của ván trước; Z kéo bàn cũ trở lại | Test `test_new_game_discards_previous_space_rollback` lỗi trước sửa; probe trên HEAD sạch cũng tái hiện | Xóa `_pre_space_state` trong `reset_game` | Cao; đây là lỗi đã có tại HEAD, không do logging |

Vị trí: `src/core/game_state.py`, các hàm `_is_game_only`, `reset_game`, `handle_rollback`, `undo_round`. Regression thêm tại `tests/unit/test_simple_launch_sync.py`: sáu tổ hợp reset/rollback/undo × game-only/physical mock và một trường hợp snapshot qua ván mới. Nhánh physical vẫn yêu cầu xác minh; không dùng việc thiếu simulator để bỏ qua gate.

## Ma trận ảnh hưởng chéo

| Giao điểm | Kết quả thực thi/đọc mã | Giới hạn |
|---|---|---|
| Launcher → Human-vs-Robot game-only | Startup `main.py` thực sự bằng SDL dummy, nước người e6→e5 và nước AI a3→a4 thành công; không tạo camera/simulator/viewer | Không phải ván GUI đầy đủ |
| Launcher → Robot-vs-Robot | Test self-play game-only commit thành công qua adapter logic; camera/motion không gọi phần cứng | Engine và SDK được mock ở test này |
| Launcher → simulation + web + WebSocket + quân | Startup thực sự, HTTP viewer/geometry/STP trả 200, bridge cells khớp game sau nước người; shutdown đóng engine/server | UI smoke dùng SDL dummy; không kiểm tra bằng chuột ở đợt này |
| R1–R4 → capture + gripper + collision + live polling | Probe PyBullet: dịch X +10 mm, quay 3°, placement version 2; live bridge chạy trong khi Xe ăn Pháo | Một vị trí/một capture, không phải mọi tuyến |
| Capture → FEN/quân | Trước commit: quân bị ăn nằm ngoài bàn, Xe ở cell (7,7), sai số XY 0,152152 mm; sau commit quân bị ăn bị loại khỏi world và identities | Sai số mô phỏng, không phải tolerance phần cứng |
| Capture → Undo → Ván mới → pose R1–R4 | Undo phục hồi victim và cells; Ván mới có 32 quân; placement object/version đã dạy được giữ nguyên | R1–R4 vẫn chỉ có hiệu lực phiên chạy |
| Logging → các luồng game/motion/twin | Startup hai chế độ kết thúc sạch; 8 test serial về log, redact, rotate, lỗi file/console, diagnostics và lọc packet DEBUG đạt | Python logging không bao trùm mọi output native SDK |
| Camera → commit → AI → physical/twin | Suite unit kiểm tra chất lượng ảnh, token/identity, trước/sau motion, failure không commit; thêm 45 test tầng ứng dụng visual/game đạt | Camera thực, extrinsic và FR3 chưa được chạy |
| GUI cửa sổ → vị trí click | Các test game-window/offline-mouse trong full unit đạt; contract viewer transform/ruler/gripper đạt | Không chứng minh toàn bộ thao tác màn hình thật |
| Collision → rejected motion → game | Full unit bao gồm direct PyBullet contact, payload, trajectory, failure/recovery và capture | Không chứng minh mọi tuyến hoặc mọi pose bàn |

## Lệnh và kết quả

Python thực thi: `C:/Users/Ken/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`. Test runner dùng wrapper `python`, `PYTHONIOENCODING=utf-8`, basetemp riêng trong `D:/OJT`, giữ thread caps của `test_fast.ps1`. Mặc định loại `slow` và `hardware`.

| Lệnh / nhóm | Kết quả | Exit |
|---|---|---|
| `./tools/test_fast.ps1 -Workers 4` trước các fix nhỏ của audit | 658 passed, 1 failed, 687,93 giây; Part B không chạy vì Part A lỗi | 1 |
| `./tools/test_fast.ps1 -Workers 4 -SerialOnly` bổ sung | 8 passed | 0 |
| Target sau fix: `test_simple_launch_sync.py`, `test_self_play_merge_contract.py`, `test_game_twin_integration.py`, `test_project_logging.py` | 43 parallel + 8 serial = **51 passed** | 0 |
| Visual/game: human handoff, human confirmation, capture FEN, emergency client, difficulty, move log, turn completion, typed robot result | **45 passed**, 8 file ngoài `tests/unit` | 0 |
| `node tests/unit/<test>.mjs`, 9 module chọn ô/transform/camera/ruler/gripper/placement/profile/authority | 6 đạt, 3 lỗi assertion; từng exit ghi trong log | 0 hoặc 1 theo module |
| Startup probe `main.py` game-only và simulation | Cả hai có `[SMOKE PASS]`, cleanup hoàn thành | 0 / 0 |
| Probe `capture_after_teaching_probe.py` trong worktree | Actual capture + undo + reset giữ pose R1–R4 đạt | 0 |

Không cộng các test chồng lặp thành một con số coverage. Full regression là snapshot trước sửa; sau sửa chạy lại phần ảnh hưởng cụ thể và probe thực, không tuyên bố đã có full regression cuối hoàn toàn xanh.

## Bốn lỗi assertion còn lại

Tất cả đều tái hiện trên HEAD sạch `7d8c5de`; không phải regression từ thay đổi launcher/logging/R1–R4 chưa commit ngày 05/10.

1. `test_phase3_final_g90_corrective.py::...test_shortened_tool_rejects_unreachable_near_center_critical_routes`: test kỳ vọng reject nhưng backend nhận pose `[-200,20,15.215,180,0,90]`. Tên/giả định tool cũ cần đối chiếu lại hình học và contact trước khi sửa. Không đổi collision guard để ép xanh.
2. `test_board_picker.mjs:30`: test kỳ vọng `null`, picker trả cell (0,0). Cần thống nhất quy tắc chọn ở biên; còn mở, không gán ngay là fixture cũ.
3. `test_viewer_coordinate_contract.mjs:103`: kỳ vọng X=-0,480 m nhưng nhận -0,497 m; chứa tọa độ cố định cần đối chiếu placement hiện hành. Đây chưa phải bằng chứng viewer lệch runtime: test parity matrix/grid-origin riêng đạt.
4. `test_viewer_single_motion_authority.mjs:59`: kỳ vọng `MEASURED_APPROXIMATE`, metadata hiện `MEASURED_PHYSICAL`. Phải sửa contract test theo provenance thực tế, không đổi trạng thái chỉ để pass.

Lần Node đầu có một lỗi môi trường Python trampoline `permission denied`; chạy lại với PATH Python phù hợp, `test_viewer_board_mesh_transform.mjs` đạt. Không tính lỗi môi trường đó là product failure.

## Bằng chứng và tái hiện

Trong `reports/cross-feature-audit-20261005/`:

- `full-regression.log`, `full-serial.log`, `target-regression-final.log`, `visual-game-regression.log`.
- `history-before.log`, `reset-before.log`: test đỏ trước sửa.
- `viewer-node.log`, `baseline-viewer.log`, `baseline-g90.log`: phân biệt assertion với baseline.
- `capture-after-teaching.json`: placement, actual pose trước commit, sai số, kết quả undo/reset.
- `capture-after-teaching.log`, `capture_after_teaching_probe.py`: probe thực không fake kết quả motion.
- `game-only-startup.log`, `simulation-startup.log`, `startup_probe.py`: startup/cleanup. Helper dùng đường dẫn worktree riêng, không chạy trực tiếp tại repo chính.

Probe R1–R4 phải gọi `prepare_board_adjustment()` trước apply. Lần đầu helper bỏ bước này đã bị backend từ chối `BOARD_RELOCATION_REJECTED_NOT_READY`; sửa helper theo flow hiện có, không thay backend để bypass.

## Phần chưa xác minh

- FR3 và camera thật, calibration/frame/TCP, lực kẹp và khả năng gắp vật lý.
- Tất cả nước hợp lệ, tất cả đường đi và mọi vị trí bàn; capture slots có thể không với tới ở pose khác và cần reject.
- Lưu R1–R4 qua restart chưa có; validation dài còn một cảnh báo freshness đã ghi trong báo cáo R1–R4 trước đó.
- Đợt audit này không chơi lại ván GUI bằng chuột; kết quả UI thực ở đợt trước không bị trình bày như quan sát mới.

Các sửa của audit đã đặt tại repo chính; chưa commit/push. Các thay đổi khác đang dở được giữ nguyên.
