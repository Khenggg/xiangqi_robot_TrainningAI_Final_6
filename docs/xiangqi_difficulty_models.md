# Các mức AI cờ tướng

`AI_DIFFICULTY` trong `config.py` chọn một trong bốn mức Moonfish. Người chơi chọn ở màn hình đầu bằng chuột hoặc phím `1`–`4`; game sẽ hiện thông báo xác nhận mức đang sử dụng.

| Mức | Search depth | Nodes tối đa | Temperature | Think time |
| --- | ---: | ---: | ---: | ---: |
| Easy | 3 plies | 2,000 | 1.35 | 0.2 giây |
| Medium | 8 plies | 20,000 | 0.9 | 1 giây |
| Hard | 11 plies | 150,000 | 0.4 | 2 giây |
| Impossible | Moonfish nguyên gốc | Không thêm giới hạn | Không áp dụng | `MOONFISH_THINK_MS` hiện tại |

Moonfish không có lệnh UCCI temperature gốc; giá trị này được lưu/ghi log như metadata của profile. Độ mạnh thực tế được hạ bằng depth, node limit và think time.

Model policy **không** tạo nước đi trực tiếp. `src.core.xiangqi.find_all_valid_moves` sinh danh sách nước hợp lệ, rồi runtime chỉ xếp hạng các nước trong danh sách đó.

## Tạo dữ liệu và train

Moonfish phải được clone tại `moonfish/moonfish_ucci.py` trước khi chạy các lệnh này.

```powershell
python scripts/generate_xiangqi_policy_data.py --difficulty easy --games 500 --output data/easy_teacher.npz
python scripts/train_xiangqi_policy.py --difficulty easy --data data/easy_teacher.npz --output models/xiangqi_easy_policy.pt

python scripts/generate_xiangqi_policy_data.py --difficulty medium --games 2000 --output data/medium_teacher.npz
python scripts/train_xiangqi_policy.py --difficulty medium --data data/medium_teacher.npz --output models/xiangqi_medium_policy.pt
```

Trước khi phát hành một checkpoint, đối đấu đổi màu với tập khai cuộc cố định: Medium cần thắng Easy khoảng 70–80%; Hard cần thắng Medium khoảng 65–80%. Không dùng checkpoint chưa benchmark trên robot thật.
