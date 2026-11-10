# Brainstorm: Dùng chung startup physical giữa các mode

**Date:** 2026-11-09

## Kết luận

Khả thi và có lợi nếu dùng chung một **physical startup service** cho các mode physical, trong khi giữ nguyên session/gameplay của từng mode. Không nên chuyển các mode khác sang toàn bộ `vsc-v3`.

## Bối cảnh code đã kiểm tra

- `main.py` định tuyến `HUMAN_VS_ROBOT` sang `VscV3Session`; các mode còn lại dùng `build_session` và `src.hardware.HardwareManager`.
- `vsc-v3` có stack riêng cho robot, camera, calibration và vision, đồng thời riêng `GameState`, move handling và FEN commit. `docs/HVR_VSC_V3.md` xác nhận tính cô lập này.
- Luồng chung có `SessionProfile`, `HardwareManager.initialize_all`, `_start_selected_game`, `AutomaticPhysicalStartup`, và một handler F9/F10 trong `main.py`.
- `AutomaticPhysicalStartup.tick()` chỉ chạy khi physical profile bật, `AUTO_ENABLE_PHYSICAL_ON_STARTUP` bật, baseline đã kiểm tra và session không có điều kiện chặn. Bởi vậy tự enable hiện không riêng về mặt thiết kế cho HvR; cần truy vết chắc chắn việc tick/poll được gọi trong app để biết các mode đang dùng service này thực tế.
- F9/F10 cấp quyền chuyển động physical. Chúng không tự nhận diện FEN. FEN ban đầu vẫn được khởi tạo từ `INITIAL_FEN`; baseline YOLO là mốc occupancy còn `verify_physical_board` đối chiếu quan sát với bàn dự kiến.
- `vsc-v3` đọc teaching profile R1 để đặt `BOARD_ORIGIN_X/Y` và dùng camera riêng. Luồng chung đọc calibration/camera qua `src.vision` và cấu hình/session profile dùng chung. Các bước này có thể được đưa sau một giao diện chung mà không nhập chung bộ điều khiển ván.

## Ideas Explored

1. **Chỉ chia sẻ chính sách enable:** đưa các mode physical khác qua cùng chính sách auto-enable có kiểm tra của HvR, còn adapter và camera stack giữ nguyên. Đây là thay đổi nhỏ nhất, nhưng chất lượng kết nối/camera còn khác nhau.
2. **Chia sẻ physical startup adapter:** thống nhất thứ tự connect → đọc teaching/calibration → mở camera → xác nhận bàn/baseline → enable; gameplay vẫn được chọn theo mode. Đây là hướng khuyến nghị vì xử lý đúng lợi ích người dùng quan sát được mà giữ ranh giới gameplay.
3. **Chuyển mọi mode sang `vsc-v3`:** loại bỏ hai stack nhưng trộn khác biệt FEN, journal, executor, PvP và self-play. Phạm vi lớn và nguy cơ hồi quy cao; không khuyến nghị.
4. **Giữ nguyên và chỉ hướng dẫn F9/F10:** ít thay đổi nhưng không cải thiện sự khác nhau về startup mà người vận hành đã gặp.

## User's Direction

Người dùng chọn: **“Startup chung, gameplay riêng.”** Mục tiêu là đem độ mượt/ít lỗi của đường kết nối Người vs Máy sang các mode khác mà không thay đổi luật chơi hoặc cách nhập nước riêng của chúng.

## Hình dung kiến trúc đích

```text
Mode đã chọn
  → SessionProfile / capabilities (camera, robot, AI, input)
  → Shared PhysicalStartup (khi physical capability được bật)
      → connect/read-only robot handshake
      → load canonical teaching/calibration profile
      → open/validate camera; calibrate board image transform
      → verify opening board against explicitly selected expected FEN
      → capture fresh baseline
      → guarded auto-enable OR operator F9 → F10 fallback
  → Mode-specific session/controller/gameplay
      HvR: vsc-v3
      HvH robot / Robot-vs-Robot / Robot PvP: existing controllers
```

Shared startup should expose a typed result (robot connection/readiness, camera/calibration readiness, board/FEN match, baseline timestamp, reason blocked) so each mode does not infer success from a connected camera or from enable alone. Mode policy decides whether camera is required to start, whether FEN scan can accept a custom position, and whether enable is needed immediately. Simulation and board-only modes should not open physical devices.

## User-visible flow proposal

For physical modes that need the camera and robot: select mode → one consistent read-only setup and diagnostics → compare the visible board to the current expected position → guarded automatic enable when configured and safe → show a concrete blocked reason and F9/F10 retry if needed → enter that mode's existing gameplay. For two-player mouse-only mode, keep camera/robot startup out of the path. For robot PvP and self-play, retain their separate start controls and admission policies after shared setup.

## Open Questions

- [NEEDS CLARIFICATION: Scope of target modes] “Các mode khác” likely means `ROBOT_VS_ROBOT` and `HUMAN_VS_HUMAN_ROBOT` in PHYSICAL. `HUMAN_VS_HUMAN` is explicitly hardware-free in `SessionProfile`; should remain excluded unless product requirements change.
- [NEEDS CLARIFICATION: FEN behavior] Should physical startup only verify the standard/current `INITIAL_FEN`, or should the operator be able to scan and adopt an arbitrary opening position? Current baseline is not a FEN importer.
- [NEEDS CLARIFICATION: Camera requirement] Must all physical-capable modes fail startup if camera/calibration is unavailable, or may robot-only/self-play start with a declared reduced capability?

## Risks

1. Duplicating two camera/robot owners or driver stacks can cause resource contention and leaks; shared service must have one clear owner and deterministic close/rollback.
2. Applying HvR enable policy indiscriminately can start motion-capable authority in a mode that expects a human confirmation or a separate F6/start action. Keep startup readiness separate from gameplay admission.
3. Teaching profile, board origin and perspective calibration have different current producers. Unify canonical sources deliberately; do not silently copy one mode's offsets or overwrite calibration artifacts.
4. Current `vsc-v3` uses a distinct gameplay/FEN state model. Preserve the session boundary and test that startup failures cannot commit a move or claim a successful physical operation.

## Suggested next step

Use `$bb-plan plans/shared-physical-startup/spec.md` after resolving the open FEN and camera-policy questions. Begin with an inventory of physical modes and a parity matrix; implement one shared startup owner with mode policy injected, then migrate modes one at a time.
