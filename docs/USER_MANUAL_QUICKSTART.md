# Sổ tay sử dụng Xiangqi Robot

Hướng dẫn hiện hành của nhánh `final` nằm tại **[README — Sổ tay sử dụng](../README.md)**, cập nhật ngày 07/11/2026 và đối chiếu code tại commit `005f95539531c32601232cdeeec3cca4185f32d9`.

- [Khởi động và chọn chế độ](../README.md#bat-dau)
- [Cách chơi từng chế độ](../README.md#cach-choi)
- [Chuẩn bị robot thật](../README.md#robot-that)
- [Chấm bốn giao điểm camera](../README.md#camera)
- [Dừng, đối soát và phục hồi](../README.md#phuc-hoi)
- [Tra lỗi và phím tắt](../README.md#xu-ly-loi)

Bản hướng dẫn 09/09/2026 trước đây đã được thay thế vì không còn khớp luồng hiện tại. Khi calibration, chọn **giao điểm lưới trên mặt bàn**, không chọn tâm mặt quân. Mất kết nối physical không tự biến phiên thành simulation. Lệnh chuyển động lỗi không được coi là thành công; không tự tắt nguồn/kéo tay/Home để thử lại. Xác nhận thoát ứng dụng không gửi lệnh dừng robot/kẹp.

Phạm vi cập nhật này là tài liệu và kiểm tra tĩnh; chưa nghiệm thu camera/FR3 thật hoặc cả ván trên Windows. Các giới hạn còn mở được giữ tại [KNOWN_ISSUES.md](../KNOWN_ISSUES.md).
