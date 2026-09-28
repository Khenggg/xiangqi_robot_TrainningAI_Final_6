---
name: boost
description: "Kích hoạt chế độ Ultra-Reasoning & Test-Time Compute Scaling cho Gemini 3.8: Tự động kích hoạt Sequential Thinking 15 bước với Dynamic Backtracking, thẩm định System 1 PRM qua Laya Reflex (35ms), lập bản đồ AST Blast Radius, phản biện Red-Team đối kháng và bắt buộc kiểm chứng thực nghiệm bằng Fast Pytest."
---

# /boost — Ultra-Reasoning, PRM & Multi-Agent Protocol

Khi người dùng kích hoạt lệnh `/boost`, Agent KHÔNG ĐƯỢC sinh code ngay lập tức mà PHẢI tuân thủ chu trình 5 bước nghiêm ngặt:

## Bước 1: AST Blast Radius & Context Delta
1. Chạy thanh tra delta: `python tools/agent_context.py`.
2. Dùng `codebase-memory-mcp` (`search_graph`, `trace_path`) để định vị các hàm chịu ảnh hưởng và phạm vi lan truyền lỗi.
3. Kiểm tra độ phủ đồ thị: `check_index_coverage`.

## Bước 2: Deep Recursive Sequential Thinking (Tối thiểu 10–15 bước)
Bắt buộc gọi MCP `sequential-thinking` với các tiêu chí:
- Xác lập 3 điều kiện bất biến (Invariants) toán học và an toàn vật lý của FAIRINO FR3:
  1. $Z_{\text{tip}} \ge 0.0105\text{m}$ (không cày mũi hút vào bàn cờ).
  2. Góc định hướng gắp: Euler RPY = `[180.0, 0.0, 90.0]` độ.
  3. `placement_version` phải khớp với phiên bản bàn cờ hiện hành.
- Phân tích rủi ro va chạm tự thân (self-collision) và điểm suy biến động học (singularity).
- Nếu phát hiện giả định vi phạm, kích hoạt `isRevision: true` và `branchFromThought` để quay lại điểm rẽ nhánh.

## Bước 3: System 1 Fast PRM Gating (35ms)
1. Gọi `laya_reflex` (`laya_multi_audit` hoặc `laya_hardware_guardrail`):
   - Chấm điểm an toàn động học, đảm bảo `DRY_RUN = True` trong Phase 3.
2. Nếu PRM phát hiện rủi ro (Risk Score > 2 hoặc boolean Check == False), dừng lại ngay và điều chỉnh thiết kế.

## Bước 4: Minimal Surgical Implementation
1. Áp dụng nguyên tắc thay đổi phẫu thuật tối thiểu (Surgical Edit).
2. Không thay đổi hằng số hiệu chuẩn và cấu trúc dữ liệu trả về kiểu mẫu (`PickResult`, `PlaceResult`).

## Bước 5: Evidence-First Empirical Verification
1. Chạy test song song có chủ đích:
   `powershell -Command ".\tools\test_fast.ps1 -Workers 2 -Tests <affected_test_file>"`
2. Nếu test FAIL: Dùng `laya_error_triage` để chẩn đoán nguyên nhân gốc (singularity, collision, gripper tolerance) và tự sửa sai.
3. Chỉ tuyên bố hoàn tất khi có log terminal xác nhận PASS và mã thoát `exit 0`.
4. Gọi `laya_eval_hallucination` đối soát văn bản phản hồi với `PROJECT_CONTEXT.md`.
