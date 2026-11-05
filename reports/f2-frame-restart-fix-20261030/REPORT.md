# F2 và bật robot sau khởi động lại — 2026-10-30

## Follow-up: firmware thực tế không có GetWObjCoordWithID

Log mới `logs/20261030_140422_060e48f6/events.jsonl:24` xác nhận XML-RPC
`Fault -506: Method 'GetWObjCoordWithID' not defined`; dòng 135 xác nhận enable
bị chặn bởi calibration error đó. Bản vá ban đầu có API trong Python SDK nhưng
chưa xử lý việc firmware trên controller không cung cấp method tương ứng.

Đã thêm fallback riêng cho đúng phản hồi method-not-defined này. Firmware cũ
chỉ được xác minh qua GetActualWObjNum/GetCurWObjCoord khi WObj đang chọn đúng
frame trên R1–R4 (trường hợp này là 1), giữ nguyên lựa chọn trong lúc đọc và có
đủ sáu offset hữu hạn bằng zero. Không dùng offset của WObj 0 để kết luận về 1.
Lỗi RPC khác vẫn chặn; code không tự chọn frame hoặc thay đổi controller.

Khi startup đang bị chặn, operator chọn User/WObj 1 trên pendant rồi F9/F10.
Enable retry đọc lại teaching points trên cùng kết nối, sau đó vẫn kiểm tra lại
idle telemetry, camera và stop generation. Không cần restart cho mỗi lần đổi
lựa chọn frame; cần restart một lần để nạp bản vá source mới.

**PASS, exit 0 — 54 parallel + 1 serial = 55:**

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv312\Scripts') + ';' + $env:PATH
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_f2_camera_and_frame_restart.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_legacy_physical_robot_gates.py
```

Môi trường Windows/Python 3.12.10; SDK/controller trong test là mock. Regression
bao gồm Fault -506 thực tế, chọn frame sau startup bị chặn, không lặp query không
hỗ trợ, không fallback với lỗi RPC khác và chặn frame thay đổi lúc đọc.
Controller thật, chọn frame/enable/motion thật và full suite: NOT RUN.
`firmware-compatibility.patch` chứa riêng thay đổi production của follow-up.

## Bản sửa ban đầu và bằng chứng trước follow-up

Đã sửa ba file production: `main.py`, `src/vision/camera_monitor.py`,
`src/hardware/robot_VIP.py`. Working tree có nhiều thay đổi sẵn có; diff của tác vụ
được đối chiếu với snapshot trước sửa, không coi toàn bộ diff HEAD là của tác vụ.
Không đổi config, calibration artifacts, tọa độ, controller hoặc yêu cầu xác nhận
F9/F10. Không dùng skill/subagent trong lượt này theo yêu cầu trước đó của user.

## Bằng chứng và thay đổi

**F2 treo khi đóng phiên.** Log
`logs/20261030_132729_a37d6870/events.jsonl:263` ghi yêu cầu `home`; các dòng tiếp
theo dừng camera/capture và giải phóng thiết bị, nhưng không có dòng hoàn tất stop.
Source tiếp ngay bằng `cv2.destroyWindow` trên disposal worker, trong khi window
được `imshow` trên GUI thread. Ảnh đính kèm báo Not Responding ở đúng bước này.

CameraMonitor giờ ghi nhận thread sở hữu cửa sổ. `stop()` chạy nền chỉ đóng thiết
bị/worker và yêu cầu đóng display; native window chỉ được đóng trên GUI owner.
F2 và shutdown gọi `close_display()` từ GUI trước khi hoàn tất disposal. Các gate
kiểm tra robot đã dừng và giao dịch pending vẫn giữ nguyên.

**Bật robot không được sau restart.** Lần chạy trước có event
`robot.frame_normalized_identity_wobj`, source WObj 1 có offset `[0,0,0,0,0,0]`,
và đã có motion/commit thành công. Lần mới
`logs/20261030_133326_9fc7e91b/events.jsonl:23` ghi calibration unavailable vì
R1–R4 có cả `(tool=0,user=0)` và `(tool=0,user=1)`.

Implementation cũ chỉ đọc frame đang được chọn, nên không xác minh được frame 1
khi controller đang ở user 0. Code mới dùng query read-only `GetWObjCoordWithID(1)`
để kiểm tra đúng frame được ghi trên teaching points. Chỉ normalize metadata
trong bộ nhớ khi đủ sáu offset hữu hạn và bằng zero trong tolerance sẵn có. SDK
ngoài không có API theo ID giữ fallback cũ, yêu cầu frame đang chọn đúng ID cần
kiểm tra. Reply lỗi, thiếu dữ liệu, NaN hoặc transform khác identity vẫn bị chặn.
Mỗi lần load lại points xóa proof identity cũ trước khi xác minh lại.

Callback F9/F10 chạy bất đồng bộ giờ ghi `physical.enable_failed` với code
`PHYSICAL_ENABLE_FAILED` và traceback vào log, thay vì chỉ hiện status tạm thời.

## Kiểm chứng

Windows, Python 3.12.10, `.venv312`. Không truy cập camera/robot thật.

**PASS, exit 0 — 30 parallel + 1 serial:**

```powershell
$env:PATH = (Join-Path (Get-Location) '.venv312\Scripts') + ';' + $env:PATH
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_f2_camera_and_frame_restart.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_camera_gpu_lifecycle.py
```

**PASS, exit 0 — 82 parallel, không có serial được chọn:**

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_f2_camera_and_frame_restart.py,tests/unit/test_home_mode_selector.py,tests/unit/test_session_user_flows.py,tests/unit/test_session_modes.py,tests/unit/test_camera_observation_integrity.py,tests/unit/test_camera_calibration_startup.py,tests/unit/test_legacy_physical_robot_gates.py
```

Output lần chạy thứ hai: `regression.txt`. Hai nhóm có test trùng nhau; không cộng
thành số ca riêng biệt. Có warning deprecation `websockets` sẵn có.

Regression mới kiểm tra luồng F2 entry/disposal thật với MotionWorker và
SessionDisposal, window-owner guard, quay về menu, trường hợp restart khi active
frame đã là base, chặn các reply/transform không hợp lệ, không dùng lại proof cũ
và log lỗi enable bất đồng bộ. SDK/camera/native calls đều được mock trong pytest.

**PASS, exit 0 — cửa sổ Windows HighGUI thật, ảnh sinh ra và fake capture:**

```powershell
.\.venv312\Scripts\python.exe -X utf8 reports/f2-frame-restart-fix-20261030/native_window_probe.py
```

Window được tạo trên GUI thread, stop chạy ở worker, worker kết thúc và GUI đóng
window thành công. Kết quả lưu ở `native-window-evidence.json`, 0 camera/robot calls.

Full repository regression, controller query thực tế, bật robot và chuyển động
FR3 thật: **NOT RUN**. Không khẳng định các finding OPEN của hai lượt audit trước
đã được sửa bởi bản vá này. Cần khởi động lại ứng dụng để nạp source mới.
