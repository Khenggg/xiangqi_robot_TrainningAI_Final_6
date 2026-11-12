# Chế độ phát mô phỏng

## Khởi động bằng PowerShell

```powershell
Set-Location 'D:\OJT\xiangqi_robot_TrainningAI_Final_6'
& '.\.venv312\Scripts\python.exe' .\main.py --simulation-profile detailed
```

Để phát nhanh hơn, thay `detailed` bằng `fast`.

| Profile | Hệ số mặc định | Cách thực thi |
|---|---:|---|
| `detailed` | 0.2 | Phát chậm để theo dõi đầy đủ gắp, nâng, di chuyển, thả |
| `fast` | 1.0 | Phát nhanh hơn qua cùng executor vật lý |

Cả hai profile dùng cùng quỹ đạo, mọi mẫu chuyển động, physics, collision guard,
kiểm tra gắp/thả và điều kiện commit. Profile không tạo đường tắt để báo thành công.
Đây là lựa chọn tốc độ phát, không phải giảm độ chính xác hoặc bỏ animation theo nước.
Tốc độ/FPS thực tế chưa được benchmark.

Mặc định là `detailed`; có thể đặt `XIANGQI_SIMULATION_PROFILE` hoặc chỉnh
`SIMULATION_PROFILE` trong config. `SIMULATION_SPEED_FACTOR` là tốc độ detailed;
`SIMULATION_FAST_SPEED_FACTOR` là tốc độ fast. Giá trị phải hữu hạn trong dải
0.05–1.0 hiện được giao diện hỗ trợ; fast không được chậm hơn detailed.

Lựa chọn CLI ghi đè tên profile trong config. `--virtual` vẫn có nghĩa **tắt mô
phỏng**, theo hợp đồng launcher hiện tại. Không ghép `--simulation-profile` với
`--virtual` hoặc `--physical`; parser từ chối tổ hợp đó.

Profile chỉ được áp dụng khi tạo virtual backend. Nó không đổi `MOVE_SPEED`,
quyền enable, cấu hình hoặc tốc độ FR3 thật. Viewer nhận profile/tốc độ mặc định
khi kết nối; các thao tác chỉnh tốc độ trong viewer vẫn dùng điều khiển hiện có.
Binding nước ảo ghi profile và tốc độ backend; đổi tốc độ mặc định làm binding
đang chờ không còn hợp lệ, không tự chạy lại lệnh cũ.

Trạng thái: code đã có; chỉ kiểm tra cú pháp/diff, chưa chạy test/GUI/physics.
Chưa có bằng chứng T-10/T-21, thời gian thực tế hay khả năng quan sát mọi animation
trên máy đích. Không coi tài liệu này là biên bản nghiệm thu.
