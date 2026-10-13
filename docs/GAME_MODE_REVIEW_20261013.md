# Rà soát ba chế độ chơi — 13/10/2026

## Snapshot và phạm vi

Repo chính `D:/OJT/xiangqi_robot_TrainningAI_Final_6`, nhánh `feature/unified-robot-vs-robot`, HEAD `7d8c5deee9e03bb187ccf8e8c1999703202cfd7e` cộng patch chưa commit. Tiếp tục từ snapshot đã bàn giao ở `docs/LIFECYCLE_EDGE_REVIEW_20261012.md`, dùng lại worktree `D:/OJT/_reliability_fix_20261012`. `reports/mode-review-20261013/baseline.json` xác nhận parity trước sửa.

Không kết nối camera/FR3 hoặc API spectator thật. Không sửa calibration, tọa độ visual, chiều cao gắp, geometry, collision guard, IK hay quỹ đạo. Không đổi mặc định LEGACY/SHADOW/UNIFIED trong config.

## Kết quả theo chế độ

| Chế độ | Chuỗi kiểm tra | Kết quả thực thi |
| --- | --- | --- |
| Người vs Robot | 5 nước người và 5 nước robot; mỗi nước người mở đúng một generation AI; duplicate human request bị chặn | PASS: 10 lượt, 2 quân bị ăn; 5 lần gọi executor giả; game, 30 bodies PyBullet và cells/identities telemetry khớp sau từng lượt |
| Người vs Người | Cả hai màu dùng coordinator người chơi; không gọi executor robot; thêm ca nhận diện UNIFIED ở lượt Đen | PASS: 10 lượt, 2 quân bị ăn; 0 lần gọi executor; game/PyBullet/telemetry khớp |
| Robot vs Robot | Hai màu dùng SelfPlayController và MoveActor.ROBOT; Step; thêm ca GUI surrender khi chuyển Continuous tại READY | PASS: 10 lượt, 2 quân bị ăn; 10 lần gọi executor giả; game/PyBullet/telemetry khớp |

Cả ba chuỗi đều đầu hàng, xác minh winner/end một lần, New Game khôi phục bàn ban đầu và đủ 32 bodies/identities. Robot vs Robot còn kiểm tra controller có thể start lại sau reset.

Các ca này chạy **PyBullet thật cho board/piece reconciliation**, nhưng **executor cánh tay trả typed result giả lập**. Reconciliation đặt bodies theo trạng thái đã commit; không phải bằng chứng cánh tay đã gắp/đặt hoặc quỹ đạo collision-free. Telemetry được kiểm tra trực tiếp; không quan sát browser 3D trong vòng này. Opening được định trước để có hai lần ăn quân, không đánh giá sức chơi engine.

## Lỗi tái hiện và sửa

| Nhóm | Trước sửa / tác động | Sửa / vị trí source | Evidence |
| --- | --- | --- | --- |
| UNIFIED còn giả định Đỏ | `_maybe_activate_unified_turn` chặn lượt Đen; arbiter luôn dựng matcher Red. Người vs Người Black không được auto-confirm | `src/ui/input_handler.py:167`, `src/vision/player_turn_arbiter.py:39`: dùng quyền human turn và truyền `player_color`; API activate giữ mặc định Red tương thích callers cũ | Ca Black trong HvH fail trước, pass sau |
| UNIFIED không khởi tạo lại lượt | Deactivate matcher nhưng `_unified_active` vẫn True. Sau AI trả lời trong HvR hoặc sau mirror recovery không tăng game_epoch, lượt sau có thể không xác nhận nữa | Reset cả matcher và active flag sau mỗi commit attempt; block khi recovery/turn chưa xác nhận | Ca Red thứ hai trong HvR và Black sau sửa mirror fail trước, pass sau |
| Thiếu chất lượng / gián đoạn mẫu | Adapter không chuyển confidence vào BoardObservation; defaults 1.0 làm gate quality không có ý nghĩa. Mẫu thiếu camera không reset arbiter nên có thể xác nhận ngay khi hình trở lại | `_unified_observation_confidence` dòng 197: shape 10x9, finite 0..1, min cell theo config; aggregate confidence vào gate hiện hữu. Không có grid chỉ chấp nhận `quality_ok=True` rõ ràng. Mất sample/pause reset matcher/window | Low/missing/false/shape/NaN/changed-cell-low đều bị chặn; camera-gap phải tích lũy window mới |
| Quyền đi tại entrypoint robot | `execute_ai_move` và self-play chưa kiểm tra độc lập ván đã kết thúc/lượt chưa xác nhận; caller GUI không phải boundary duy nhất | `src/core/ai_execution.py:10`, `src/core/self_play_controller.py:119` và `:181`: reject trước pending/executor. Request Next ngoài READY không đổi ownership của worker đang chạy | No dispatcher/pending mutation khi game_over hoặc turn chưa xác nhận; in-flight status giữ MOVING |
| Surrender Continuous | Main dùng `accepts_next` (chỉ Step) để quyết định đầu hàng, nên Continuous ở READY bị bỏ qua | `accepts_surrender` dòng 69, `main.py` nhánh BTN_SURRENDER: chỉ kết thúc tại READY, worker đã dừng, ván/lượt hợp lệ, không phụ thuộc cadence | Chạy main.py/Pygame headless thật, click qua phép đổi tọa độ window/canvas: winner BLACK, end RESIGN một lần, 0 motion |

Mức tin cậy **VERIFIED bằng fault probes và executable flows** trong phạm vi trên. Những nhóm lỗi này có sẵn ở baseline của vòng này; không xác định commit gây ra khi chưa có bằng chứng lịch sử. Gate quality áp dụng cho nhánh arbiter UNIFIED/SHADOW; LEGACY vẫn giữ authority cũ khi SHADOW được bật.

## Bằng chứng thực thi

Thư mục evidence: `reports/mode-review-20261013/`. Môi trường Windows, Python 3.12.10, pytest 8.4.2, xdist 3.8.0; dùng `.testvenv` của worktree và thư viện runtime `.venv312` hiện hữu.

| Gate | Kết quả | Log |
| --- | --- | --- |
| Probe đầu trước sửa | FAIL: 12 failed; ca surrender đầu chưa đổi canvas coordinates sang window nên riêng ca đó được kiểm tra lại | `red.log` |
| Surrender baseline với vị trí window đúng | FAIL: game không kết thúc, exit 1; main.py được restore đầy đủ sau probe | `surrender-red.log` |
| Camera gap / mirror recovery trước sửa bổ sung | FAIL: mỗi ca exit 1 | `gap-red.log`, `recovery-red.log` |
| Focused lần đầu | FAIL: 57 pass, 1 fail do tọa độ fixture GUI | `focused.log` |
| Focused với fixture GUI đúng và matrix 3 mode | PASS: 61 test, exit 0 | `focused-2.log` |
| Subsystem có gap/recovery | PASS: 159 test, exit 0 | `subsystem.log` |
| Bản cuối sau review | PASS: 160 test, exit 0; gồm 18 test mới | `final-targeted.log` |
| Full regression | PASS: 1.029 song song + 8 tuần tự = 1.037 test, exit 0, 528,68 giây | `full.log` |
| Compile / parity repo chính | PASS: compileall exit 0; 9 file bàn giao khớp hash | `primary-compile.log`, `delivery-verification.json` |

Lệnh chính (cwd worktree):

```powershell
$env:PATH=(Join-Path (Get-Location) '.testvenv/Scripts')+';'+$env:PATH
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/modes-final-targeted --tb=short'
./tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_game_modes_review.py,tests/test_player_turn_arbiter.py,tests/test_board_stability_monitor.py,tests/unit/test_physical_ui_latency.py,tests/unit/test_self_play_merge_contract.py,tests/unit/test_self_play_twin_contract.py,tests/unit/test_reliability_recheck.py,tests/unit/test_review_lifecycle_edges.py,tests/unit/test_camera_game_pipeline.py,tests/unit/test_spectator_lifecycle.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_visual_v2_adapter.py,tests/test_emergency_client_move.py,tests/test_human_commit_ai_handoff.py,tests/unit/test_physical_camera_commit_gate.py
$env:PYTEST_ADDOPTS='--basetemp=D:/OJT/_reliability_fix_20261012/.pytest_tmp/modes-full --tb=short'
./tools/test_fast.ps1 -Mode Balanced -Tests tests
```

## Review và bàn giao

Review delta của 5 file production, callers và các enum/contracts có liên quan, thực hiện tuần tự theo yêu cầu tiết kiệm token. Optional keyword `player_color` giữ các calls activate(board, capability) trước đây. Adapter chỉ dùng mẫu cache, không mở camera/rerun model hoặc HTTP trên UI. Cadence Step/Continuous không làm mất ownership của worker. Những gates motion/recovery/camera khác không bị nới.

Graph được dùng cho discovery và trace; một số results là bản cũ hoặc snapshot reports. `detect_changes` ở worktree trả 397 changed paths gồm thay đổi kế thừa, 0 impacted symbols; không coi số 0 là blast radius bằng 0. Source thực tế, `delta.patch`, `code-locations.json` và 160 test là căn cứ của review. Không phát hiện blocker trong delta cuối.

`tested-hashes.json` khóa source ở thời điểm full gate. Copy về repo chính chỉ khi tất cả hash đích vẫn khớp `baseline.json`, sau đó xác minh `delivery-manifest.json` / `delivery-verification.json`. Chưa commit/push; các patch kế thừa được bảo toàn.

## Chưa kiểm chứng

Camera/FR3 thật, firmware completion, gắp/ăn/thả quân vật lý, quỹ đạo đầy đủ cho 10 lượt mỗi mode, live spectator HTTP, browser rendering và calibration/metric parity đều **NOT RUN trong vòng này**. Các test vision dùng sample nhận diện giả, không kiểm định độ chính xác model. Đây là bằng chứng cho các boundary/mode đã nêu, không khẳng định dự án không còn lỗi.
