# Đồng bộ bàn cờ thật, ván cờ và Digital Twin

Mốc thực hiện: `feature/unified-robot-vs-robot` tại `b6acba6`; thử nghiệm trong worktree riêng. Chưa điều khiển FR3 thật.

## Luồng vận hành

1. Camera chụp hai frame mới. Full-board recognizer phải trả cùng ma trận 10×9, `success=true`, `quality_ok=true` ở cả hai frame.
2. Đối với lượt người, so với GameState để suy ra đúng một nước hợp lệ của màu đang đi. Ma trận sau phải bằng toàn bộ kết quả áp dụng nước đó, kể cả quân bị ăn.
3. Nước người đã xảy ra ngoài đời được ghi vào FEN rồi chuyển cho `LiveTwinBridge`; bridge đặt body PyBullet của quân đang đi vào ô mới, xóa body quân bị ăn và gửi full `world_state` cho Three.js. Lỗi đồng bộ khóa lượt robot để quét lại bàn.
4. Robot ở cả hai màu dùng `MoveContext(actor=ROBOT)` với ID quân đi và quân bị ăn. Chỉ `HardwareManager.execute_piece_move` qua Resolver/Executor được phép ra lệnh; bộ kiểm tra va chạm virtual dùng cùng world PyBullet của twin. Lỗi đường đi hoặc kẹp không tạo nước đi thành công trong FEN.
5. Ở chế độ FR3 thật, sau khi robot chạy xong, camera phải xác nhận hai full-board frame bằng trạng thái dự kiến trước khi ghi FEN. Đây là kiểm tra vị trí quân, không chứng minh lực kẹp hay an toàn quỹ đạo phần cứng.
6. Nút tiếp tục quét cho phép đồng bộ toàn bàn sau sự cố khi robot đứng yên và không giữ quân. Nếu ảnh mới tương ứng đúng một nước hợp lệ từ bàn trước đó, lượt được chuyển sang màu còn lại. Nếu có nhiều thay đổi hoặc không suy ra được nước duy nhất, GameState khóa lệnh; người vận hành xác nhận lượt kế tiếp bằng phím `1` (Đỏ) hoặc `2` (Đen). Các ID cùng loại được gán theo quy tắc cố định; ảnh 2D không chứng minh danh tính vật lý của hai quân giống nhau.
7. Self-play sau lỗi chỉ khởi động lại khi đã quét và xác nhận bàn, xác nhận lượt nếu cần, rồi nhấn `R`; không tự phát lệnh robot khi vừa khôi phục trạng thái.

`GAME_MODE=HUMAN_VS_HUMAN` cho người đi cả hai màu; `HUMAN_VS_ROBOT` giữ người đỏ, robot đen. Self-play điều khiển robot ở cả hai màu. Camera người được xác nhận bằng SPACE hoặc cơ chế hand-aware đã cấu hình; tự quét nền liên tục vẫn chưa được triển khai.

## Bằng chứng chạy

- `DRY_RUN=True`, `ROBOT_BACKEND=VIRTUAL`, `.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_camera_game_pipeline.py,tests/unit/test_camera_twin_world.py,tests/unit/test_self_play_twin_contract.py,tests/unit/test_physical_camera_commit_gate.py,tests/unit/test_live_twin_physical_mirror.py,tests/unit/test_game_twin_integration.py,tests/unit/test_end_to_end_game_twin_sync.py,tests/unit/test_hardware_manager_integration.py,tests/test_self_play_controller.py,tests/test_capture_fen_sync.py,tests/test_emergency_client_move.py,tests/unit/test_phase2_vision_and_carryover.py`: **115 passed**, exit code 0.
- Trong 115 bài kiểm tra có cổng camera cho robot thật ở dạng giả lập: robot báo thành công nhưng camera không xác nhận thì FEN không đổi, và hai frame phải đồng thuận.
- `node tests/unit/test_viewer_camera_reconciliation.mjs`, `test_viewer_coordinate_contract.mjs`, `test_viewer_gripper_and_telemetry.mjs`: PASS với Three.js thật. Test tọa độ cũ đã được cập nhật theo yaw 0° của scene hiện tại.
- Bộ `test_fast.ps1 -Workers 4` trên toàn `tests/unit` chạy tới 92% rồi dừng vì các ca hình học chạy rất lâu; xuất hiện nhiều lỗi. `KNOWN_ISSUES.md` đã ghi nhận nhiều test yaw 90° cũ trên scene yaw 0°. Vì chưa phân loại đầy đủ các lỗi đó, không tuyên bố full regression xanh.

## Giới hạn và điều kiện dừng

- Một đường đi virtual của pháo đen ở scene yaw 0° bị chặn tại `APPROACH`: gripper/link đế robot có penetration 0.18 mm trong mẫu quỹ đạo. Test end-to-end yêu cầu không ghi nước đi, giữ collision guard. Cần sửa thiết kế đường đi với kiểm tra toàn quỹ đạo trước khi coi robot pick/place hoạt động ở ô này.
- Chưa thử trực tiếp chất lượng nhận diện trên camera và bàn thật. Hai ảnh ổn định có thể cùng sai; cần đối chiếu thủ công hình ảnh, calibration, confidence và vật cản trước commissioning.
- Không thử chuyển động FR3 thật. Hiệu chuẩn camera/board/TCP, payload, gripper và E-stop phải được xác minh riêng trước khi cấp quyền di chuyển phần cứng.
- Re-scan chỉ tự đổi lượt khi xác nhận được đúng một nước hợp lệ từ bàn đã biết. Sau nhiều thay đổi hoặc mất lịch sử, ảnh không cho biết đến lượt ai; robot và người chơi bị khóa cho đến khi người vận hành xác nhận lượt. Số nước trong FEN sau quét nhiều thay đổi không thể khôi phục chính xác từ một ảnh.
