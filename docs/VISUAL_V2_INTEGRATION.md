# Tích hợp visual v2 vào unified

Nguồn: visual `fe3faa8dcac121defa4c9ee000d4df0ac6c8fd09`; nền: unified `7d8c5de` và source chưa commit tại snapshot `da70323`. Chủ dự án đã chọn toàn bộ khuyến nghị A ngày 09/10/2026.

## Cấu hình và khởi động

Lệnh cũ giữ nguyên: `python main.py` chạy game + simulation + viewer; `--virtual` tắt simulation; `--physical` dùng camera/FR3 sau commissioning. `SETUP_WINDOWS.bat` tạo `.venv312` và cài `requirements.txt` có đủ vision, PyBullet và WebSocket. RUN và các launcher calibration cùng ưu tiên môi trường của dự án. Không áp dụng lock hoặc intrinsics camera 0 từ máy donor.

Mặc định vẫn **strict center**, không tự đổi sang height/top-face/ring và không fallback sang chân quân/tâm lý thuyết khi mất tâm đo. `VISUAL_HEIGHT_PICK_ENABLED`, `VISUAL_TOP_FACE_ENABLED`, `VISUAL_RING_PICK_ENABLED` đều False. Mỗi lần chỉ bật một chế độ; ring được ưu tiên nếu bật. `VISUAL_CURRENT_PICK_ENABLED=False` cùng ring=False chặn việc đo tâm.

Kích thước camera geometry mặc định `None`: phải điền số đã đo trên bàn/quân đang dùng. Không dùng 324×368, 250×281.25, chiều cao 7/10 mm hay xoay tool của donor như số đo tại máy này. Bộ thông số donor chỉ lưu tại `calibration/visual_v2_candidate_settings.json` để đối chiếu; runtime không tự đọc nó.

## Công cụ camera

Đóng phiên đang sở hữu camera trước khi chạy:

```powershell
python scripts/calibrate_camera_intrinsics.py --square-mm <canh-o-checkerboard-da-do>
python scripts/calibrate_pick_geometry.py --square-mm <canh-o-da-do> --board-width-mm <rong-luoi> --board-height-mm <dai-luoi> --piece-height-mm <cao-quan>
```

Các dấu `<...>` là chỗ nhập số đo, không phải lệnh chạy nguyên văn. Dùng `--help` để xem đầy đủ. Hai công cụ chỉ mở camera. `VIDEO_INDEX` hoặc `--camera` chọn đúng thiết bị, không tự chuyển sang camera khác. Runtime và công cụ cùng dùng `camera_source.py`; mặc định giữ yêu cầu 1280×720 của unified. Profile phải khớp camera index, kích thước frame, homography, kích thước bàn và chiều cao quân. Index không chứng minh cùng camera vật lý nếu USB đổi thứ tự; cần kiểm tra lại calibration.

Height dùng `VISUAL_HEIGHT_BOARD_MM`, `VISUAL_HEIGHT_PIECE_MM` và intrinsics. Top-face dùng `VISUAL_BOARD_WIDTH_MM`, `VISUAL_BOARD_HEIGHT_MM`, `VISUAL_PIECE_HEIGHT_MM` và profile đã kiểm định độc lập. Ring sử dụng geometry height, cộng điều kiện nhận dạng vòng màu. Chưa bật mặc định vì chưa có phép đo và ảnh thực tại máy này.

## Chức năng tương ứng ở simulation

| Chức năng | VIRTUAL | PHYSICAL |
|---|---|---|
| Người–người | Nước người cập nhật quân; tay không tự đi | Camera xác nhận bàn trước khi commit |
| Người–robot | Nước người đồng bộ quân; nước AI qua backend virtual | Cùng semantic identity; đo tâm, kiểm tra toàn bàn, typed motion result |
| Robot–robot | Cả hai màu qua backend virtual | Hai màu dùng cùng adapter; không hardcode AI phải đen |
| T: gắp/thả thủ công | Identity test riêng, collision guard, đồng bộ scene; không đổi FEN game | Cùng manager/motion lock, điểm camera và xác nhận sau motion |
| T → chọn quân → H: hover | R1–R4 hiện tại → resolver → waypoint approach → backend kiểm tra quỹ đạo; không kẹp | XY gắp đã đo tại SAFE_Z; vẫn cần quyền physical/calibration hiện tại |
| Y / nút ĐO LẠI | Không retry tự động lỗi collision/IK/payload; lỗi motion giữ fault | Chỉ đo lại tại checkpoint trước pick, hoặc sau bỏ quân bị ăn đã được camera xác nhận |
| Intrinsics/height/top-face/ring | Không áp dụng: không giả camera thật bằng tâm ô | Opt-in, dùng quan sát mới và số đo có nguồn gốc |

Simulation dùng vị trí body và BoardPoseProvider hiện tại để gắp quân. Tính năng camera không tạo một bộ R1–R4 hoặc tọa độ simulation thứ hai. Hover khi collision guard tắt bị từ chối. Biên ngoài lưới là khả năng của nhận diện/camera pick, không phải lý do tắt guard hay cho phép xuyên vật thể.

## Retry, lỗi và tài nguyên

- Retry gắn với pending object, move ID, identity nguồn/quân bị ăn, expected board, epoch, actor và toàn bộ trạng thái bàn. Đổi một trong các dữ liệu này chặn retry.
- Sau capture removal, kiểm tra cả ô trống và **toàn bộ bàn chỉ thiếu quân bị ăn** trước khi ghi checkpoint. Retry từ đó chỉ gắp quân nguồn; không lặp bước bỏ quân bị ăn.
- SDK khác 0, gripper lỗi, sai bàn hoặc stale result không trở thành lỗi camera có thể retry. FEN chỉ commit sau typed success và kiểm tra toàn bàn dự kiến.
- Worker physical giữ một job, khóa thao tác UI và ngăn các job khác. Self-play đã có worker riêng; dùng cùng adapter. Đóng ứng dụng đợi worker; nếu còn chạy thì giữ camera/controller mở và báo lỗi, không giả đã hủy SDK.
- New Game xóa request và checkpoint cũ. Đối soát/recovery hiện có tiếp tục là đường xử lý khi bàn thật đã thay đổi ngoài checkpoint.
- Log mới: `vision.retry_paused`, `vision.pick_resolved`; lỗi stage/backend giữ mã lỗi và move ID trong hệ thống log hiện tại.

`VISUAL_PICK_OUTSIDE_MARGIN_MM=0.0` mặc định. Khả năng mở tới 10 mm đòi hỏi kích thước lưới đã đo và kiểm chứng đường đi riêng; không thay R1–R4. Top-face còn giữ giới hạn riêng của bộ estimator. Không nhập offset outward hoặc xung gripper mới của donor.

## Phạm vi kiểm chứng

Xem báo cáo đợt tích hợp trong `reports/visual-integration-20261009/REPORT.md` để biết lệnh, exit code, kiểm tra mô phỏng và giới hạn. Test synthetic/mocks không xác nhận camera hoặc FR3 thật. Setup import trên môi trường đang có không chứng minh cài mới Python 3.12 thành công.
