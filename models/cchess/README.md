# CChess Recognition ONNX Models

Thư mục chứa các mô hình Deep Learning dạng ONNX phục vụ nhận diện bàn cờ và quân cờ tướng:

- **`pose_4_v6.onnx`** (~10.7 MB): Mô hình RTMPose (SimCC) phát hiện 4 góc bàn cờ (`A0`, `A8`, `J0`, `J8`).
- **`layout_nano_v3.onnx`** (~31.1 MB): Mô hình Swin Transformer v2 phân loại 16 nhãn quân cờ trên toàn bộ 90 vị trí (10 hàng × 9 cột).

Nguồn: [TheOne1006/chinese-chess-recognition](https://github.com/TheOne1006/chinese-chess-recognition)
HuggingFace: [yolo12138/Chinese_Chess_Recognition](https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition/tree/main/onnx)

