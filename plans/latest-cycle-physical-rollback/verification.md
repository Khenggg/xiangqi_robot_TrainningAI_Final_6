> Historical design: rollback has been removed. This document does not describe the current runtime.

# Bằng chứng và phạm vi kiểm chứng rollback

Các test dùng camera/controller/arm/provider giả hoặc geometry tổng hợp. Không
có yêu cầu HTTP thật hay lệnh arm thật trong kiểm chứng này. Một test có thể
kiểm tra nhiều subcase; không coi số test là số case đã nghiệm thu phần cứng.

| Case trong plan | Bằng chứng offline | Phần cần nghiệm thu thật |
|---|---|---|
| A01–A07 | `test_rollback_cycle`: sáu nhóm capture, đổi thứ tự, đích trống và S0; `test_rollback_coordinator`: executor/capture/manual | Từng mẫu gắp/đặt, capture và vị trí nghỉ |
| A08–A10 | Hardware verifier occupancy theo mode; coordinator đo tâm an toàn riêng quân nguồn trước motion | Góc/biên bàn, calibration và sai lệch thực tế |
| B01–B10 | Cycle seal/consume; integration Z, async ownership, latest partial cycle, baseline gate; normal suite AI/pending guards | Trạng thái controller và timing UI thật |
| B11 | Integration SPACE không có nước, legacy snapshot không ghi đè ledger | Nhiễu camera thực tế |
| B12 | Integration Emergency không tạo ledger, nút gameplay/poll khóa khi partial; review test terminal durability; reset/epoch regression | Test/operator thao tác xuyên suốt phiên thật |
| C01–C05 | Pure full-board restoration subsets, wrong/unexpected; coordinator WAIT_PLAYER và final proof | Người chơi phục hồi một/hai quân, thông báo mismatch thật |
| C06–C07 | 90-cell confidence/unknown, stable reset; occupancy .4-cell vẫn đúng ô; nguồn không có target đo vẫn bị chặn; PvP không tải intrinsics | Tay che/mờ/ánh sáng và ngưỡng confidence được commissioning |
| C08 | Giới hạn được nêu trong spec/docs, không có physical ID | Không hứa phát hiện tráo hai quân giống hệt |
| D01–D06 | Camera/geometry failure, checkpoint before/after, lost ACK, unknown board, controller packet/pose/DO guards; existing motion112 tests | Lỗi kết nối/112, kẹp còn giữ quân, rơi quân với phần cứng thật |
| D07–D08 | Coordinator verified-abort, partial progress và abort record roundtrip | Operator phục hồi S2 an toàn |
| D09 | Runtime integration restart giữ S2/S0 và room, zero auto motion; read-only connection/cleanup tests; corrupt journal validation | Cắt điện/crash đúng checkpoint và SDK controller thật |
| D10 | Coordinator baseline-only retry, altered S0 rejection; integration baseline seal | Baseline camera thật sau commit |
| D11–D12 | Durable commit ID/outbox restart, pending enqueue lock, single-worker ordering tests | Server chấp nhận backward FEN/rejection semantics |
| D13–D14 | Epoch/generation invalidation, normal poll/auto-confirm gates, reset arbiter after finish | Auto-confirm/AI liên tiếp trên bàn thật |

Lệnh và kết quả cuối được ghi trong Session Notes của `plan.md`; log chi tiết
và review ở `outputs/reviews/2026-10-28/`. Chưa commit/push trong lượt triển khai.
