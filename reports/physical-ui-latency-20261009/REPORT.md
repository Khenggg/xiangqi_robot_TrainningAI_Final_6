# Sửa lag giao diện / viewer physical — 2026-10-09

## Phạm vi và nguồn bằng chứng
- Repo chính: feature/unified-robot-vs-robot, HEAD 7d8c5de; thay đổi hiện có chưa commit được giữ nguyên.
- Chạy kiểm chứng trong D:/OJT/_viewer_fix_20261009 với snapshot code hiện hành. Hash các file chính được kiểm tra trước khi đưa fix về repo chính.
- Phiên thật đang mở: logs/20261009_182123_8cf5e112/run.log; PID13700 có title REAL RUN. Không mở thêm camera, không gửi lệnh robot và không dừng phiên người dùng.

## Nguyên nhân đã xác nhận
1. AUTO_MOVE_CONFIRM_ENABLED=True: main.py gọi poll_board_stability mỗi vòng UI; interval0.1s. Hàm này trước đây đồng bộ grab5/read + ONNX/YOLO qua get_fresh_snapshot, rồi recognize_board_state chạy CChess thêm lần nữa. Nó chờ chung inference lock với luồng nền. Giao diện chờ dù không có traceback. Tin cậy cao từ đường gọi và mã thực.
2. ONNX mặc định tạo pool riêng, spinning; Torch/Ultralytics trên máy này dùng7threads. Tiến trình game được ghi nhận khoảng391% CPU theo counter tổng nhiều lõi, không phải391% toàn máy. RAM còn khoảng5.3GiB. CPU cạnh tranh có thể làm tình trạng chờ nặng hơn; tỷ trọng SDK/camera chưa đo độc lập.
3. Log18:21:33: Physical mirror unavailable: Physical board surface contact offset has not been calibrated. Không có listener8088/8765 lúc kiểm tra. main trước đây chỉ mở cảWS vàHTTP nếu bridge được tạo; tab HTML cũ có thể còn hiện nhưng module/telemetry không được phục vụ. Tin cậy cao. Không suy ra lỗi mạng/CDN là nguyên nhân ở phiên này.

## Thay đổi
- CameraMonitor.get_latest_observation xuất atomic frame đã được infer + boxes + layout + timestampmonotonic; không lấy frame preview mới ghép boxes cũ. Sample stale/lỗi bị loại.
- poll_board_stability dùng cache, không đọc thiết bị hoặc chạy lại model. Timestamp lặp không tăng samplecount; baseline thay đổi tạo cutoff, bỏ sample cũ; quan sát mất/stale reset candidate. Luật, gatecamera và full-board verification vẫn áp dụng. Snapshot phục vụSPACE/pick/verification vẫn là snapshot mới.
- CChess ONNX2threads/session, interop1, tắt spinning. Torch CPU2threads sau khi Ultralytics hoàn tất lazy setup; GPU không đổi. LượtYOLO đầu vẫn chưa cap, có thể chậm.
- HTTPviewer khởi động kể cả mirror chưa sẵn sàng, trừ --virtual/--no-viewer. Khi bridgeNone: không mởWS/không publish giả; URL autoconnect0 và banner PREVIEW OFFLINE nêu lỗi calibration. Không giả lập calibration để mở physical gate.
- HTTPCache-Control:no-cache để revalidate code sau cập nhật. Browser cần hardreload ở lần cập nhật từ server cũ.
- Thêm ui.slow_frame và camera.slow_inference, rate limit10s, có duration; không thể coi log im lặng là bằng chứng không lag.

## Kiểm chứng
- final-tests.txt:72passed, Python3.11.15, pytestxdist2; camera cache/health/rawpick, actualmain entrypoint with mocked hardware (--physical bridgeNone và --virtual), camera->GameState/PyBullet/telemetry, physical verification, startuprecovery, MIME/cacheheaders. Exit0. Không chạy hardware tests hay toàn bộ repo suite.
- Python3.12.10 + model ONNX/YOLO thực trên ảnh screenshot user (chỉ kiểm tra hiệu năng, KHÔNG phải rawframe/độ chính xác): before.txt và after-budget.txt. WarmCPU3mẫu trung bình từ3531ms xuống1839ms (~48%); walltime biến động do game thật cũ còn chạy. Coldsetup vẫn~5.6s; không tuyên bố FPS hoặc tốc độ nhận dạng đã đạt.
- ui-python312.txt:8s với model thật chạy nền, SDLdummy, không camera/FR3:292frames; UIp95=16.19ms, UImax38.16ms, pollingmax0.31ms. Coldinference8.46s, workerTorch2; kết quả bị loại do quá tuổi1.5s đúnggate. Đây là bằng chứng UI không chờmodel, chưa chứng minh camera thật nhận dạng đủ nhanh hoặc người chơi bấm được mọi hành động trên physical.
- Browser qua computeruse ở8098: modelrobot + board render; OFFLINE/banner đúng; consoleerror[]; offline-preview.jpg. Hardreload đã dùng để loại cache cũ. Không click nút điều khiển robot.
- Review độc lập Luna đã đọc fixcục bộ: lưu ý coldYOLO spike; GAME_ONLY khôngviewer đúng quy ước user. Testentrypoint đã phủ.
- detect_changes:376changedfiles,0impacted_symbols; indexgraph cũ và dirtydiff lớn, số0 KHÔNG là bằng chứng không có blast radius.

## Cần kiểm chứng tiếp ở phiên thật
- Thoát game cũ, chạy .\RUN.bat --physical; Ctrl+F5 viewer. Không tự dừng phiên hoặc bật quyềnmotion.
- Chưa có BOARD_CALIBRATION_OFFSET_MM đo thực: previewoffline vẫn không đại diện geometry/pose bàn thật. Live mirror/motion không được xác nhận ready.
- SPACE/scan/baseline/API khi người dùng chủ động yêu cầu còn có thể chờ tác vụ hữu hạn; fix này bỏ nhận dạng đồng bộ ở polling liên tục, không hứa mọi nút hoàn toàn khôngblocking.
- SDK dòng 接收机器人状态字节 -1 là dấu hiệu nhận trạng thái thất bại cần theo dõi riêng; chưa tái hiện socket hoặc thaySDK.
- Không commit/push. Các thay đổi user/nhánh khác được giữ nguyên.

## Tài liệu tham khảo
- ONNX Runtime official thread management: https://onnxruntime.ai/docs/performance/tune-performance/threading.html (pool/session, intra_op_num_threads, allow_spinning).
