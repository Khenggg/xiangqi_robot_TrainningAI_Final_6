# Camera Monitor đứng hình và mất tên quân — kiểm tra 13/10/2026

## Kết luận

Camera bàn cờ hiện là index **2**, backend **DirectShow/DSHOW**, đã đọc được
ảnh **1280×720** đúng bàn và FR3. Ảnh `cam_1.jpg` được mở nhầm trong lúc kiểm tra
là ảnh webcam cũ, không phải nguồn camera hiện tại. Không thay camera config,
không mở game/SDK/robot trong các probe này.

Nguyên nhân chính của monitor đứng hình: `HardwareManager._init_camera`
tạo `CameraMonitor` tại `src/hardware/hardware_manager.py:429` nhưng không gọi
`self.cam_monitor.start()`. Không tìm thấy caller thay thế trong main/src.
Constructor không tự khởi động luồng; `start()` tại
`src/vision/camera_monitor.py:409` mới chạy capture và detection threads.
Lệnh start có trong snapshot trước ở `_reliability_fix_20261012`, đã biến mất
trong source chính đang kiểm tra. Không xác định được chính xác lần sửa/AI nào
xóa lệnh này chỉ bằng Git HEAD vì thay đổi chưa commit.

Ảnh đang hiện là cache của các lần snapshot thủ công/baseline. Qua **1,5 giây**,
`_draw_overlay` bỏ kết quả CChess có tên; vẫn vẽ detections YOLO trong cache
thành khung xanh `piece`, rồi thêm `Recognition stale / waiting for inference`.
Do đó 32 khung xanh không chứng minh monitor đang nhận dạng liên tục.

## GPU chưa có hiệu lực trong môi trường chạy RUN

RUN.bat ưu tiên `.venv312/Scripts/python.exe`; kiểm tra chính interpreter này:

| Thành phần | Kết quả đọc thực tế |
|---|---|
| NVIDIA | GTX1650Ti, driver592.00, được nvidia-smi nhận diện |
| PyTorch | `2.14.1+cpu`, `torch.version.cuda=None`, `cuda.is_available=False` |
| ONNX Runtime | `1.31.0`, providers Azure/CPU; không có CUDAExecutionProvider |
| onnxruntime-gpu | Không được cài trong .venv312 |
| CChess pose/layout khi chạy thử | Cả hai session dùng CPUExecutionProvider |

Ngoài package, `hardware_manager.py:377` gọi CChessRecognizer mà không truyền
`use_gpu=True`; constructor tại `cchess_recognizer.py:400` mặc định False.
Chỉ cài GPU package chưa đủ để CChess tự chọn CUDA. YOLO tự kiểm tra Torch CUDA
và hiện chọn `cpu`, đúng log phiên18:16. Không có bằng chứng CUDA crash trong
phiên này vì cả hai pipeline thực tế đang chạy CPU.

## Bằng chứng thực thi, không chỉ test có sẵn

Probe nằm trong worktree riêng `D:/OJT/_camera_gpu_review_20261013` với snapshot
đúng các module vision đang có ở repo chính. Không thay production source hoặc
thư viện; không gọi main.py, SDK, enable, motion hay IO.

1. Đọc camera2 qua DirectShow:3 lần read đều trả frame1280×720; frame đầu đen
   khi camera chưa ổn định, hai frame tiếp có ảnh bàn. Camera được release.
2. CameraMonitor constructor trên fake capture:0 lần read, cả hai thread=None.
   Gọi start trong probe:28 lần read/0,15s, cả hai thread sống; stop đóng sạch.
3. CPU inference thật trên ảnh bàn vừa lấy, CChess ONNX + YOLO best.pt:
   - Lần đầu2,484s,32 detections/32 named pieces, health đã stale vì quá1,5s.
   - Lần tiếp0,485s và0,453s,32 detections/32 named pieces, health ready.
   - Không cập nhật thêm1,7s:health stale, named result unavailable,32 detections
     vẫn trong cache. Render cho đúng kiểu ảnh lỗi người dùng đã gửi.
4. Log phiên `logs/20261013_181616_f797471f/run.log`:
   camera/cchess load thành công, YOLO cpu; thiếu thông báo monitor started;
   hai mẫu xác nhận bàn đạt và SPACE vẫn nhận dạng CChess thành công18:18:27.
   Đây là bằng chứng model có thể nhận dạng, nhưng live loop không chạy.

Artifacts: `reports/camera-gpu-review-20261013/` có snapshot.json,
camera-source.json, lifecycle-probe.json, inference-probe.json,
camera2-live-2.jpg, overlay-fresh.jpg và overlay-stale.jpg.

Thời gian đo là probe offline lúc ứng dụng đã đóng, không phải benchmark khi
game/robot/viewer hoạt động đồng thời. 32 tên không thay thế kiểm chứng độ chính
xác từng quân xuyên suốt ván. Không sửa lỗi hoặc cài GPU trong đợt báo cáo này.

## Cách đã mở đúng camera

- Interpreter: `D:/OJT/xiangqi_robot_TrainningAI_Final_6/.venv312/Scripts/python.exe`.
- Source hiện tại: `config.py:97`, `VIDEO_SOURCE=2`; VIDEO_INDEX có thể override.
- Dùng `src.vision.camera_source.open_camera(2)`; policy auto trên Windows thử
  DirectShow trước, rồi MSMF/CAP_ANY nếu không đọc được **cùng index2**.
- Lần kiểm tra này backend đọc thành công là DirectShow.
- Đặt width1280/height720 rồi read vài frame; không kết luận từ frame đầu đen.
- Không dùng các ảnh cam_1/cam_2/raw_frame đã lưu từ phiên trước để xác định
  camera hiện tại. Số index có thể đổi khi đổi cổng USB/cài driver; kiểm tra ảnh.

Ví dụ kiểm tra riêng camera, không mở game/robot (đóng ứng dụng giữ camera trước):

```powershell
cd D:\OJT\xiangqi_robot_TrainningAI_Final_6
@'
import cv2, time
from src.vision.camera_source import open_camera
cap = open_camera(2, backend="dshow")
try:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    frame = None
    for _ in range(10):
        ok, image = cap.read()
        if ok and image is not None:
            frame = image
        time.sleep(0.1)
    if frame is None:
        raise RuntimeError("Camera2 không trả ảnh")
    print("Backend:", cap.getBackendName(), "Shape:", frame.shape)
    cv2.imshow("Camera2 check", frame)
    cv2.waitKey(0)
finally:
    cap.release()
    cv2.destroyAllWindows()
'@ | .\.venv312\Scripts\python.exe -X utf8 -
```

Để mở dự án bằng nguồn đã kiểm tra (thao tác người dùng):

```powershell
cd D:\OJT\xiangqi_robot_TrainningAI_Final_6
$env:VIDEO_INDEX = "2"
.\.venv312\Scripts\python.exe -X utf8 main.py --physical
```

Lệnh này chưa khắc phục lỗi thiếu monitor.start; ở đợt này chỉ ghi lại cách chọn
đúng camera. Không thay perspective/R1-R4 hoặc vị trí bàn.

## Đề xuất sửa theo thứ tự

1. Khôi phục lifecycle start/stop của monitor, đảm bảo chỉ khởi động một owner;
   xác minh ảnh/nhận dạng cập nhật liên tục mà không cần SPACE.
2. Xử lý warmup và trạng thái stale minh bạch; không chỉ tăng timeout để che
   luồng nhận dạng không chạy hoặc làm dữ liệu cũ thành hợp lệ.
3. Sau khi CPU baseline hoạt động, xử lý GPU riêng cho Torch/YOLO và ORT/CChess;
   log providers thực tế và đo cùng ảnh, không dựa vào nvidia-smi alone.
