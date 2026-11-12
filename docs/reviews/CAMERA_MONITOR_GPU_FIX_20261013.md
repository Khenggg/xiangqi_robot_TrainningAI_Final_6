# Sửa Camera Monitor và bật GPU — 13/10/2026

## Phạm vi

Sửa lỗi monitor không chạy nền; phục hồi API nhận dạng/snapshot đã bị mất;
bật GPU cho YOLO và CChess trong đúng `.venv312` mà RUN dùng. Không đổi camera
index2, perspective.npy, R1-R4, hình học bàn/robot, quyền hoặc lệnh robot.
Worktree sửa/kiểm chứng: `D:/OJT/_camera_gpu_review_20261013`.

## Thay đổi

- HardwareManager gọi CameraMonitor.start một lần sau calibration/profile
  startup; không khởi động thêm owner khi start được gọi lại.
- Khôi phục atomic get_latest_observation, recognized frame, fresh pick,
  predict serialization, pick scan pause/diagnostics, CPU thread budget và
  stop không release capture nếu worker chưa dừng. Các API này có ở snapshot
  trước nhưng bị mất khỏi camera_monitor.py của repo chính.
- Preview còn chạy khi dữ liệu stale; không vẽ khung YOLO cũ như dữ liệu mới.
  Giữ nguyên gate1,5s và timestamp ảnh, không tăng timeout để che lỗi.
- VISION_DEVICE mặc định auto. CChess được yêu cầu GPU, Torch quyết định YOLO
  theo CUDA availability. `VISION_DEVICE=cpu` ép cả hai pipeline dùng CPU.
- ONNX CUDA dùng DLL CUDA/cuDNN kèm wheel Torch. Providers thực tế được log.
  Chọn HEURISTIC và không dùng workspace cực đại cho GPU4GB của máy này.
- SETUP_GPU.bat cài stack đã kiểm chứng, kiểm tra session CUDA và inference;
  SETUP_WINDOWS giữ GPU runtime đã có. Base requirements không cài thêm CPU
  ORT chồng lên GPU; Windows setup chọn CPU ORT nếu chưa có GPU wheel.

## Thư viện đã cài vào máy

- torch2.14.1+cu126, torchvision0.29.1+cu126 (thay các wheel CPU cùng phiên bản).
- onnxruntime-gpu1.20.2 (gỡ onnxruntime CPU1.31.0 để tránh trùng package).
- CUDA12.6/cuDNN9.10.2 từ wheel Torch; không cài full CUDA Toolkit hay đổi driver.
- CUDA tensor tính tổng thực bằng4; torch nhận GTX1650Ti; pip check không báo
  dependency hỏng. ORT pose và layout đều có CUDAExecutionProvider, YOLO cuda:0.

Chọn phiên bản theo [bảng CUDA/cuDNN của ONNX Runtime](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#requirements)
và [wheel CUDA của PyTorch](https://pytorch.org/get-started/previous-versions/).
Import Torch để preload DLL tuân theo
[hướng dẫn tích hợp ORT/PyTorch](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#compatibility-with-pytorch).

## Bằng chứng trực tiếp

- Lifecycle mới4 tests: baseline4fail; sau sửa passes. Hai thử runner đầu
  không chạy được do thiếu thư mục cha basetemp, đã giữ log và tạo thư mục.
- Gate subsystem89passes, exit0: lifecycle, health/stale, atomic observation,
  camera startup/cleanup, pick/ring/consensus, calibration và CChess.
- Trên cùng ảnh bàn đã chụp, CPU warm0,453–0,485s; GPU warm0,047–0,078s,
  cả hai nhận32 quân. Cold GPU2,344s vẫn bị gate stale từ chối như thiết kế;
  kết quả tiếp theo mới được dùng. Không coi cold startup là dữ liệu ready.
- Camera2/DSHOW thật1280×720, preview15s trong probe camera-only có GUI.
  Sau giây5:227/227 mẫu ready, tất cả có32 tên quân;147 timestamp capture
  khác nhau và39 timestamp recognition khác nhau trong toàn run.
  Capture/detect threads dừng và capture được release; không có SDK/robot.
- Ảnh `reports/camera-gpu-fix-20261013/live-overlay.jpg` đã kiểm tra bằng mắt:
  tên Xe/Ma/Tu/Si/Tg/Ph/Tot, banner16Đỏ/16Đen, đúng camera bàn cờ.

Kết quả final full/delivery được ghi trong REPORT.md và delivery-manifest.json
của cùng thư mục evidence. Không coi log tests có sẵn thay cho probe camera.
Gate cuối phạm vi sửa:123passes, exit0. Full gate:857passes/12failures,
runner dừng trước serial. Cả12failure tái hiện khi phục hồi source trước bản
sửa camera (cùng môi trường thư viện đã cài). Sửa thêm thiếu màu accent trong
banner Robot vs Robot loại được3startup failures. Rerun12findings:3pass/9fail.
Chín findings còn lại thuộc spectator API/FEN, logic fallback AI home approach,
attached payload geometry và kỳ vọng calibration/frame/board mirror đã đổi
trước đợt này. Không thay những logic đó để ép toàn bộ test thành xanh.
Không tuyên bố toàn repo hết lỗi hoặc full suite đạt.
Độ chính xác từng quân qua cả ván, gắp/thả và robot thật không được nghiệm thu
trong đợt sửa camera này. Thời gian trên ảnh offline không phải latency tổng
camera+game+robot. Probe live chạy15s, không phải kiểm tra ổn định dài hạn.

## Khởi động

```powershell
cd D:\OJT\xiangqi_robot_TrainningAI_Final_6
$env:VIDEO_INDEX = "2"
$env:VISION_DEVICE = "auto"
.\.venv312\Scripts\python.exe -X utf8 main.py --physical
```

Chọn chế độ chơi và hoàn tất bước calibration camera như thường lệ. Trong log
phải có `Camera Monitor started`, providers CUDA và YOLO device0. Lượt warmup
đầu có thể cần vài giây; không dùng dữ liệu cũ làm nước đi trong lúc chờ.

Để chạy CPU chủ động: `$env:VISION_DEVICE="cpu"` rồi khởi động lại. Khi setup
máy mới: chạy SETUP_WINDOWS.bat trước; SETUP_GPU.bat là bước GPU riêng.
Môi trường hiện tại đã được cài; không cần chạy lại setup để dùng bản sửa.
