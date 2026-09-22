# Các mức AI cờ tướng

`AI_DIFFICULTY` trong `config.py` chọn một trong ba mức:

- `easy`: checkpoint `models/xiangqi_easy_policy.pt`; policy nhỏ, teacher Moonfish depth 2 và top-k ngẫu nhiên.
- `medium`: checkpoint `models/xiangqi_medium_policy.pt`; policy lớn hơn, teacher Moonfish depth 5.
- `hard`: Moonfish/cloud theo cấu hình engine hiện tại.

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
