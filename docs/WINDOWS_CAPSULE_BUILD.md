# Build capsule Windows (dành cho team)

Người nhận dùng ZIP phát hành, không clone repo rồi chạy SETUP. Hướng dẫn thao tác ngắn: [CAPSULE_OPERATOR.md](CAPSULE_OPERATOR.md).

## Build

Trên máy phát triển Windows x64 có Python 3.12/pip, Git, Internet và model do team quản lý:

```powershell
.\BUILD_CAPSULE.bat --models "D:\path\to\models"
```

Thư mục model phải có `best.pt`, `cchess/pose_4_v6.onnx`, `cchess/layout_nano_v3.onnx`; thêm `board_pose.pt`, `hand_best_egohands.pt` nếu có. Không dùng checkpoint không đáng tin cậy. Các trọng số không được commit vào Git; team phải có quyền phân phối khi bàn giao.

PyBullet 3.2.7 trên Python 3.12 có thể cần build wheel bằng MSVC trên máy build (pip tái dùng wheel cache nếu có). Đây là công đoạn của team, không diễn ra trên máy sự kiện. Không copy `.venv` sang máy khác.

Kết quả mặc định:

```text
dist/
  Xiangqi-Capsule-Windows-x64/
    START.bat                 # entrypoint duy nhất cho vận hành
    READ_ME_FIRST.md
    settings.json             # cấu hình máy/thiết bị, không chứa pose hay credential
    manifest.json             # SHA256 từng file, source và package versions
    runtime/                  # CPython + dependencies CPU + VC runtime DLLs
    app/                      # code, engine, model, CAD/Three.js và fixed hardware profile
    state/                    # launcher/model caches và log chẩn đoán
    LICENSES/
  Xiangqi-Capsule-Windows-x64.zip
  Xiangqi-Capsule-Windows-x64.zip.sha256
```

`--output "D:\Releases\Xiangqi-v2"` chọn thư mục mới; builder từ chối ghi đè release cũ. Build lỗi không xuất ZIP thành công. Runtime/download cache tại `build/capsule-cache/` có kiểm tra SHA256; thư viện đã cài được tái dùng theo requirements fingerprint. Nếu cài dependency bị gián đoạn, chuyển cache `site` sang chỗ khác rồi build lại; không cài đè lên cache dở.

## Nguyên tắc đóng gói

- CPython embeddable x64 app-local; `_pth` khóa đường import về release và bỏ phụ thuộc Python/PATH/registry của máy nhận. Dependencies được vendor vào release bởi team, không cung cấp pip cho người dùng. Xem [tài liệu Python](https://docs.python.org/3.12/using/windows.html#the-embeddable-package) và [quy tắc `_pth`](https://docs.python.org/3.12/library/sys_path_init.html#pth-files).
- Runtime 3.12.10 là bản 3.12 có Windows embeddable binary dùng cho baseline này; ghi version/hash trong manifest. Khi nâng runtime/dependency, rebuild và kiểm thử lại cả bundle.
- Requirements CPU được pin riêng tại `tools/capsule/requirements.txt`; mỗi release ghi toàn bộ package thực tế và hash các file. Torch CPU tải từ nguồn chính thức, không yêu cầu GPU/CUDA.
- Chỉ copy runtime source/asset được Git quản lý theo allowlist, cộng model được cung cấp. Không copy logs, journal, `.env`, venv hay credential của workstation. Fixed teaching/calibration **được** copy như profile của bộ thiết bị team, không phải tọa độ phổ dụng.
- Three.js kiểm tra integrity trong package-lock, CAD loader đã vendor. Font Noto CJK và OFL đi kèm để không phụ thuộc gói ngôn ngữ Trung trên Windows.
- Bỏ headers, static libraries, test files và stock `pybullet_data` demo datasets; giữ asset FR3/bàn cờ riêng của ứng dụng. Trên Windows có đường dẫn tiếng Việt, resolver dùng alias ASCII hoặc bản sao mesh/texture tạm ở thư mục ASCII có quyền ghi (tự dọn khi thoát), không đổi cwd/map ổ đĩa hay sửa source/calibration. Cache URDF được đối chiếu nội dung để không giữ đường dẫn của nơi cũ.
- Không thay luật/chuyển động/stop/recovery gate. LOCAL engine, spectator token trống và CPU vision là mặc định của launcher sự kiện.
- File settings và thư mục state/game logs/journal là mutable; checksum release không coi chúng là binary bất biến. Không xóa journal khi đang recovery.

## Gate trước bàn giao

Builder chạy `launcher.py --smoke` bằng **runtime đã đóng gói**, PATH chỉ còn System32: kiểm tra SHA256, import native libraries nằm trong runtime, Moonfish subprocess, load hai ONNX, YOLO inference CPU, PyBullet DIRECT và renderer/font. Python socket connect bị chặn trong bước probe; không mở camera/controller.

Sau build, copy/giải nén sang thư mục khác có dấu/khoảng trắng và kiểm tra lại:

```powershell
.\START.bat --check
```

Đối chiếu ZIP với `.sha256`. Chạy thử trên Windows sạch/PC thứ hai không có Python/Node, tắt Internet, chơi một ván và kiểm tra viewer trước sự kiện. Kiểm thử cô lập trên máy build không thay thế nghiệm thu máy thứ hai. Robot/camera, thay setup, tải gắp/thả thật và các lỗi vận hành còn mở trong KNOWN_ISSUES phải nghiệm thu riêng; capsule không tự chữa các lỗi đó.

Artifact lớn/cache ở `dist/`, `build/` bị Git ignore. Source/pipeline trên nhánh `final`; ZIP và `.zip.sha256` được bàn giao qua [GitHub Release capsule](https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105-r2). Không commit model hoặc runtime nặng. Người nhận tải asset capsule, không dùng `Source code (zip)` thay bộ phát hành.

Bản final r2 hợp nhất code mới từ need-review, giữ nguyên mode HUMAN_VS_HUMAN_ROBOT mới và xác nhận thoát. Acceptance probe còn kiểm tra subprocess client Đen bằng runtime bundle và socket localhost, render cửa sổ Đen, nhận board/gửi request; không gọi executor vật lý. Probe exit modal bắt Enter và thay hàm kết thúc OS bằng SystemExit chỉ trong probe, không tuyên bố nghiệm thu cleanup khi os._exit.
