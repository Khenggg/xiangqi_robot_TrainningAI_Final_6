# Rà soát lần hai độ tin cậy — 12/10/2026

## Kết quả

Phát hiện và sửa **7 nhóm lỗi** bằng mã và ca tái hiện riêng. Không dùng con số test cũ để kết luận không còn lỗi. Không có camera/FR3 thật được kết nối hay điều khiển. Giữ nguyên tọa độ/Z donor, geometry và collision guard virtual, cùng quyết định không dùng simulator collision để quyết định lệnh physical.

| Lỗi tái hiện | Sửa ở đâu | Bằng chứng mới |
| --- | --- | --- |
| 1. Constructor InputHandler lỗi sau khi backend/WS đã chạy làm main thoát fatal | `main._finish_startup`, `session_startup.rollback_session`: giữ home, đóng partial resources, cho retry | Real main entrypoint với hai lần lỗi input configuration; mỗi lần cleanup manager/WS/HTTP một lần; cuối cùng hw/input None |
| 2. Continue physical chấp nhận legal successor từ một ảnh confidence thấp | `InputHandler._continue_after_snapshot_pause`: dùng hai quan sát mới khớp nhau, đủ quality và calibration qua `_fresh_confirmed_layout` | Legal pawn move với confidence .05 trước sửa bị commit; sau sửa không commit/không baseline và giữ pause; confidence .99 được nhận |
| 3. Continue/cảnh báo bàn chỉ tìm legal successor Đỏ, không nhận nước Đen HvH | `LegalSuccessorMatcher(player_color=...)`, hai caller InputHandler | Cả nước Đỏ và Đen được xác nhận đúng FEN/lịch sử/lượt trong physical harness; mặc định matcher vẫn là Đỏ cho caller cũ |
| 4. Recovery xóa lỗi mirror mới và hiển thị thành công; lỗi command cũ cũng không được thay thế đúng khi commit verified | `GameState.commit_pending_physical_move`, `_finalize_pending_ai_move` | Một commit verified: mirror false giữ lỗi/pause, không baseline; mirror true xóa lỗi command cũ và tiếp tục. History chỉ một lần, không replay motion |
| 5. F8 dừng self-play không đóng spectator; surrender có thể bị đóng với kết quả sai nếu bổ sung stop không phân biệt reason | `SelfPlayController.end_match(winner,reason)`, main surrender caller | End gọi một lần; ENDING/ENDED không lặp; IDLE không đóng game người chơi; RESIGN giữ winner đúng. F8 kết thúc spectator; bắt đầu ván mới bằng New Game rồi F6 |
| 6. Một số nhánh thắng/kẹt không còn legal move chỉ đổi UI mà không gửi end-match | Self-play tick nhánh engine/no-moves; main AI completion sync/async; recovery commit khi chiếu bí | Test terminal self-play xác nhận winner và CHECKMATE. Caller main đã đối chiếu trực tiếp cùng nhánh; API tiếp tục qua queue |
| 7. Ăn Tướng được rule checker/game chấp nhận nhưng camera sanity đòi đủ hai Tướng, chặn cả checkpoint removal lẫn post-board | `validate_board_sanity`, `HardwareManager.verify_physical_board`, `visual_move_coordinator`, recovery InputHandler | Hai màu qua coordinator thực + camera verifier thực + GameState, RPC/ảnh giả: verify trước, verify removal, verify expected; commit winner đúng và không tạo baseline tiếp theo. Mặc định vẫn reject thiếu Tướng; ngoại lệ chỉ được truyền từ pending capture Tướng đã biết, yêu cầu đúng bên mất Tướng, toàn board khớp expected, quality và hai ảnh mới; hai Tướng cùng thiếu vẫn reject |

Lỗi 7 được chứng minh trước sửa trong `recheck-terminal-limit.json`: snapshot tổng hợp được rule checker nhận, camera output khớp board expected và confidence .99, nhưng verify false do thiếu Tướng. Đây là fixture phần mềm, không phải ván đã chạy trên phần cứng.

## Kiểm chứng

- `recheck-repro.log`: 4 failing probes trước sửa (startup/Continue/stop/mirror).
- `recheck-extra.log`: tái hiện Continue Đen và terminal spectator bị thiếu.
- `recheck-recovery-positive.log`: đối chiếu thêm successful recovery và stop IDLE; phát hiện/sửa tương tác của patch mới trước bàn giao.
- `recheck-subsystem.log`: 109 đạt trên các luồng camera/game/recovery/self-play trước bổ sung terminal camera.
- `recheck-full.log`: **978 parallel + 8 serial đạt**, exit 0, 581.46 s. Full chạy trên snapshot trước phần bổ sung terminal camera; 2 test terminal và sửa validator/coordinator sau đó được kiểm tra bằng gate riêng.
- `recheck-final-2.log`: **110 đạt**, exit 0, trên source cuối, gồm 13 probes mới và các test CChess/quality/physical commit/capture retry/board identity. Không cộng số test trùng giữa các gate.
- Compileall `src` và `main.py` đạt. Graph MCP dùng để định vị/truy vết và detect_changes; index còn chứa snapshot lịch sử, nên kết quả impacted_symbols trống không được coi là không có blast radius. Đã đọc file thật, review diff và failure paths tuần tự.

## Bàn giao và giới hạn

Source/docs chỉ được đưa về repo chính sau khi preflight SHA256 khớp snapshot đầu đợt. Chi tiết file/hash: `reports/reliability-fixes-20261012/recheck-delivery-manifest.json`; parity: `recheck-delivery-verification.json`. Manifest `delivery-manifest.json` và full gate 976 của đợt trước là evidence lịch sử, không phải hash của patch mới này. Không commit/push/reset/clean hay đổi venv runtime.

Chưa chứng minh toàn bộ repo không còn lỗi. Những luồng đã tái hiện/sửa ở trên đạt gate cuối; còn chưa kiểm chứng camera nhận dạng và latency thật, R1–R4/TCP/Z, firmware motion completion, grasp/place/capture thật và commissioning. Thiếu calibration contact của bàn vẫn chỉ cho raw arm telemetry, không chứng minh bàn/quân preview khớp ngoài đời. WebSocket deprecated API warnings vẫn còn, không phải failing test.

Bản sửa phải được nạp bằng việc dừng phiên cũ và khởi động lại. Không tự khởi động physical hardware trong đợt review.
