# Kết nối robot qua Ethernet

Hướng dẫn kiểm tra kết nối giữa PC và controller FAIRINO. Thực hiện kiểm tra mạng trước khi cho phép chuyển động; kết nối camera và kết nối robot là hai trạng thái độc lập.

## Địa chỉ và adapter

Địa chỉ controller mặc định trong cấu hình là `192.168.58.2`. PC cần địa chỉ riêng cùng subnet trên adapter nối với robot. Ví dụ một bộ thiết bị sử dụng:

| Thiết bị | Địa chỉ ví dụ |
|---|---|
| PC Ethernet | `192.168.58.3/24` |
| Controller | `192.168.58.2` |

Các giá trị phải khớp cấu hình thực tế. Trong capsule, IP controller lấy từ `settings.json`; khi chạy source, đối chiếu `config.py`. Không gán trùng địa chỉ PC/controller.

Chỉ định địa chỉ nguồn khi kiểm tra máy có nhiều adapter:

```powershell
ping -n 2 -S 192.168.58.3 192.168.58.2
arp -a | findstr 192.168.58.2
```

Thay IP ví dụ bằng IP của bộ thiết bị. Ping thành công chỉ xác nhận khả năng tiếp cận mạng tại thời điểm kiểm tra, không xác nhận controller/robot đã sẵn sàng chuyển động.

## Nhận biết lỗi

Các thông báo có thể gặp:

```text
GetControllerIP: controller reply unavailable; outcome unknown, do not resend
Robot SDK not connected
```

Telemetry cũ, timeout hoặc RPC không phản hồi có thể liên quan đến cáp/adapter, địa chỉ mạng hoặc trạng thái controller. Cần log và kiểm tra hiện tại để xác định nguyên nhân. Camera vẫn có ảnh không chứng minh kết nối controller hoạt động.

## Kiểm tra và phục hồi

1. Khi mất phản hồi trong thao tác đang dở, giữ journal và không gửi lại motion/gripper command có kết quả chưa xác định.
2. Kiểm tra robot/kẹp theo quy trình vận hành của bộ thiết bị; đóng phần mềm không thay thế việc xác nhận robot đã dừng.
3. Kiểm tra cáp, đầu nối, link LED, adapter và IP/subnet. Thay cáp hoặc adapter nghi lỗi khi cần.
4. Kiểm tra ping trên đúng adapter, sau đó trạng thái controller và telemetry mới trong ứng dụng.
5. Làm theo luồng phục hồi/đối soát trên UI. Chỉ cho phép F9/F10 sau khi các điều kiện dừng, bàn cờ và controller đã được xác nhận.

Ứng dụng mặc định dùng profile teaching cố định tại `calibration/physical_teaching_points_user0.json`. Kết nối lại không tự hiệu chuẩn profile này; khi thay bộ robot, bàn hoặc tool/frame, phải xác minh cấu hình tương ứng. Xem [ROBOT_FRAME_BASE_ONLY.md](docs/ROBOT_FRAME_BASE_ONLY.md).

## Ghi nhận trước đây

Một số phiên kiểm tra đã ghi nhận kết nối không ổn định liên quan cáp/đầu nối của bộ thiết bị. Đây là quan sát lịch sử, không phải chẩn đoán mặc định cho mọi lỗi mới. Các snapshot trong `reports/` mô tả thời điểm được ghi, không đại diện cho trạng thái controller hiện tại.
