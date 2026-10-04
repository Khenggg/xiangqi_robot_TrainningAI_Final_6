# Kết quả hợp nhất (2026-10-04)

Đã giữ simulation/viewer của unified và lấy ứng dụng camera/game/AI/robot vật lý từ visual-correction-v2. Các adapter, điều kiện chặn và sửa lỗi hình học được ghi dưới đây. Chưa commissioning FR3 thật; simulation ăn quân bằng robot vẫn bị chặn nếu chưa có đường thải quân được kiểm chứng.

# Visual v2 + unified simulator integration

## Source ownership

- Base simulation branch: `feature/unified-robot-vs-robot`, `830e73b3082a93cf3dee4d5500c35fa6c5846e64`.
- Visual application donor: `feature/visual-correction-v2`, pulled to `e6bb6323a966727de1a17e57625711b3c2ead0c3`.
- Integration branch: `integration/visual-v2-unified-20261004`.
- Simulation, PyBullet, kinematics, domain transforms, viewer, shared geometry, motion contracts/executor: unified.
- Camera, game presentation, Moonfish/policies, physical FAIRINO controller, gripper wiring: visual.
- Additive adapters join these boundaries; no second physical SDK connection and no startup actuation.
- Existing uncommitted simulation/viewer/R1-R4 fixes were copied deliberately from the primary checkout. Other primary dirty camera/game changes are preserved separately, not silently substituted for the visual donor.
- Governance and historical review documents retained from unified. Superseded manager/engine tests are documented in `MERGE_TEST_CONTRACT_MIGRATION_20261004.md`.

## Runtime

Default: `ROBOT_BACKEND=VIRTUAL`, `DRY_RUN=1`. Run `python main.py`; the visual launcher starts the game, simulator and local telemetry after selecting a game mode. Viewer connects to `ws://127.0.0.1:8765`.

- Human vs robot: visual game + explicit human confirmation, then one typed robot job.
- Human vs human: both colors use camera-verified legal transitions.
- Robot vs robot: step mode, F7 schedules the next move; F8 ends scheduling. F6 can start it from a game.
- F4: two fresh complete board scans and explicit reconciliation. If multiple changes prevent inferring a turn, keys 1/2 confirm Red/Black.
- F5: explicit retry of a failed engine query only when the physical/twin state is not faulted.
- SPACE, visual pick correction, difficulty profiles, recovery UI, measured gripper output wiring remain from visual.

The primary `shared/virtual_fr3_scene.json` retains unified's backend pose. Its preview and live representations now use the same proper rigid transform; old nonrigid/reflected teaching observations are preserved under `legacy_teaching_points_unvalidated` and never drive target coordinates. `XIANGQI_SCENE_CONFIG` selects an explicit scene consistently across domain, runtime and PyBullet; historical yaw-90 regressions use a separate named fixture instead of assuming the operator's mutable default.

## State and safety boundaries

- Stable piece IDs accompany committed moves and complete camera boards. Captures remove the victim from PyBullet and viewer state only after a verified game/camera transition.
- Error 112 and every failed arm/gripper stage stop the physical sequence. A truthy boolean cannot masquerade as a typed completed motion.
- Physical moves require full-board verification before and after motion, with epoch checks after camera reads; failures preserve pending recovery and block additional motion.
- Physical connect is read-only. Activation is explicit through `FR5Robot.activate_physical_control(commissioned=True)`, after calibration/commissioning. No test here activates real hardware.
- Physical mirror requires contact-offset frame/provenance, base-frame R1-R4 metadata, rigid fit and parity with the visual bilinear map. Commands adopt the same verified tool/user frames. Arbitrary nonrigid measured grids are rejected instead of fabricating a rigid mirror.
- Physical board motion is not automatically tracked by camera pixel calibration; remeasure/recalibrate extrinsics before resuming if the board moves.
- Virtual commands use the shared actual collision world, swept trajectory checks and payload confirmation. Dangerous table/floor/arm collisions must be rejected without replacing the authoritative robot pose.
- Simulation robot capture deliberately remains blocked until a validated disposal route exists. Camera/human captures synchronize correctly. No victim is teleported to fabricate robot capture success.

## Geometry provenance

STEP-derived gripper envelope was regenerated and compared: 19 fixed boxes, 2 finger boxes, jaw travel and frame unchanged. Only stale fingerprints were repaired. Text hashing is canonical UTF8/LF so Git CRLF conversion is not a false mismatch; actual numeric mutations still fail.

The retained profile declares TCP offset 168.3 mm, while the visual mesh's extension target is 168.058 mm. The 0.242 mm difference is not silently reclassified as physically calibrated parity. Controller TCP/tool measurements, camera calibration, payload behavior, collision clearances and hardware recovery remain commissioning gates.

## Verification artifacts

- `reports/integration-20261004/gui-home.png`, `gui-difficulty.png`, `gui-game.png`: actual Pygame launch using the virtual runtime and Moonfish.
- `reports/merge_visual_unified/viewer_offline.png`, `viewer_live.png`: actual browser preview/live parity; board transform and asymmetric cells unchanged across Connect.
- `reports/merge_visual_unified/collision_evidence.json`: direct actual simulation command rejection and PyBullet contacts, including unchanged joints/TCP.
- `tools/simulation/smoke_merged_gui.py`: reproducible virtual GUI smoke; never uses physical hardware.

### Final verification record

- Full safe regression: `tools/test_fast.ps1 -Mode Full -Tests tests`: **716 passed, 1 failed**, exit 1, 422.84 s. The remaining failure was A2.5: a 3-second join expired while a pick worker was still correctly holding MOTION under CPU load. This is not reported as an all-green full run.
- Corrective gate after that fix and the final startup/physical-camera changes: **79 passed**, exit 0, 11.17 s. It includes A2.5 (bounded 30-second join plus explicit worker-completed assertion), camera startup cleanup, full-board observation integrity, physical camera commit gating, visual simulation adapter and SPACE confirmation. The final tree was not subjected to another full 7-minute rerun.
- Previous application/camera corrective gate: **73 passed**, exit 0. Real ONNX models load/infer; a blank image is rejected as an unverified board, rather than being asserted successful.
- Node `npm run test:viewer`: **2 passed**, exit 0. Rigid board transform/grid-origin integrity and actual mesh/cell parity checked.
- GUI: actual virtual launch succeeds in **HUMAN_VS_ROBOT, HUMAN_VS_HUMAN and ROBOT_VS_ROBOT**; each emits MERGED_GUI_SMOKE_OK. Screenshots are stored for each mode.
- Fresh direct runtime/PyBullet evidence: `python -m reports.merge_visual_unified.check_collision_runtime`, exit 0. Board penetration and folded pose commands are rejected; joints/TCP deltas are zero and gripper state unchanged. Raw negative contacts demonstrate that the gripper really is a collision object.
- Serial inventory: 719 collected tests are deselected by the serial marker; no serial cases exist. Slow/hardware-marked tests and five explicit manual robot diagnostics are excluded. No physical controller was connected or actuated in this integration verification.
- Manual diff review covered startup/cleanup, SDK ownership, tool/user frame adoption after parity approval, typed motion failure propagation, full-board camera authority, board transform/inverse mapping, reset failure telemetry and test fixture changes. Graph detect_changes was executed; its pre-resolution index is stale, so a zero-symbol impact result is not considered proof of no impact.
- Original donor whitespace warnings remain in imported third-party Moonfish/data and other donor files. They are not hidden as a clean lint result. No unresolved Git conflict exists.

### Local work preservation

Before updating the primary checkout, its original uncommitted files are preserved in a Git stash named `pre-visual-unified-integration-20261004`. Do not blindly reapply it: its camera/game changes belong to the replaced application. Recover individual files only after comparing ownership and current integration contracts.

