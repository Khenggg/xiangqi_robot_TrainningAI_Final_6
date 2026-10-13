## 2026-10-13 SDK connection / calibration separation

Live controller read: R1-R3 tool=0,user=1; R4 tool=0,user=0. Teaching-point validation no longer marks an established SDK connection disconnected. Raw arm telemetry/WebSocket remains available; invalid calibration blocks physical enable/actuation and board alignment. Focused gate: 106 passes, including actual local WebSocket with mocked measurements. Patched GUI/hardware motion NOT RUN. See docs/SDK_CONNECTION_CALIBRATION_SPLIT_20261013.md.

## 2026-10-13 worker scheduling / retry review

Six reproduced boundary failures repaired: QUIT remaining-event dispatch, F6 discarding unconsumed results or paused checkpoints, self-play overlapping UI worker jobs, retry baseline/mirror failures, and terminal retry publication. Final subsystem: 189 passes; independent before/after scheduling probe: 100/100 mock-executor replays. Full gate: 1044 parallel + 8 serial = 1052 passes (exit 0). Primary compile/parity passed; see delivery-manifest.json. See `docs/RUNTIME_RACE_REVIEW_20261013.md` and `reports/runtime-race-review-20261013/`. Hardware, firmware completion and real grasp remain unverified.

## 2026-10-13 game mode review

Repaired UNIFIED Black turns/rearming/recognition quality/sample gaps and post-mirror recovery, AI/self-play finished or unconfirmed entry guards, and Continuous surrender at a safe READY boundary. Final affected gate: 160 passes; full gate: 1029 parallel + 8 serial = 1037 passes. Each of three game modes completed a deterministic 10-ply/two-capture sequence, surrender and New Game with real PyBullet board reconciliation and mocked arm execution. Evidence: `docs/GAME_MODE_REVIEW_20261013.md`; latest hashes: `reports/mode-review-20261013/delivery-manifest.json`. Physical actuation/vision and trajectories remain unverified; no geometry/calibration change.

## 2026-10-12 lifecycle edge review

Additional fixes: human/Black Emergency terminal publication, entrypoint rejection for finished/unconfirmed/illegal moves, preservation of rejected Red Emergency recovery, rollback undo-stack restoration, Emergency mirror/result handling, and camera-Q same-frame dispatch prevention. Final subsystem gate: 142 passes; full gate: 1011 parallel + 8 serial = 1019 passes, including a real headless main.py camera-Q probe with mocked devices. Details: `docs/LIFECYCLE_EDGE_REVIEW_20261012.md`; latest hashes: `edge-delivery-manifest.json`. Hardware remains unverified.

## 2026-10-12 spectator lifecycle follow-up

F8 → F6 reopens spectator with the current FEN, startup reuses queued rooms, New Game explicitly rotates rooms, and finished games require New Game. Self-play startup failure messages remain visible. Final subsystem gate: 85 passes; full gate: 996 parallel + 8 serial = 1004 passes. Real headless main.py F8/F6 event routing passed with mocked devices/HTTP and zero robot commands. See `docs/SPECTATOR_LIFECYCLE_FIX_20261012.md` for delivery evidence; latest hashes: `session-lifecycle-delivery-manifest.json`. Hardware and live spectator service remain unverified.

## 2026-10-12 second reliability review

Seven additional failure groups reproduced and repaired: startup UI rollback, Continue confidence/current-color, recovery error lifecycle, spectator stop/terminal publication, and known king-capture board verification. Final affected gate 110 passes; full pre-terminal snapshot 978 parallel + 8 serial passes. Scope and exact evidence: `docs/RELIABILITY_RECHECK_20261012.md`. Hardware remains unverified; latest hashes are `recheck-delivery-manifest.json`.

## 2026-10-12 reliability corrections

- Physical target coordinates/heights follow fetched visual-correction-v2 `fb0598d`; explicit enable and fresh controller state remain required. Physical commands do not consult simulator collisions, per current user request. Virtual collision handling is retained.
- Startup/recovery/engine/RPC/API/lifecycle and command-animation fixes are documented in `docs/RELIABILITY_FIXES_20261012.md`. Exact verification results and delivery hashes: `reports/reliability-fixes-20261012/REPORT.md` and `delivery-manifest.json`.
- Missing board surface contact calibration permits read-only arm telemetry; it does not prove board/piece alignment. No camera/FR3 physical test in this change. Earlier dated entries below describe earlier snapshots.

## 2026-10-09 physical UI latency fix

- Automatic board polling consumes atomic camera-worker observations without camera reads/model inference on the UI thread; repeated/stale samples cannot satisfy stability gates. ONNX CPU pools are bounded; fresh command verification remains unchanged.
- HTTP viewer now starts even when physical calibration blocks the mirror, with an explicit offline preview warning and no telemetry/autoconnect. --virtual still disables simulation/viewer.
- 72 targeted tests passed; real Python3.12 model/UI smoke and browser preview verified in isolation. Physical camera/FR3 responsiveness after restart remains unverified; cold model setup can still be slow. Evidence: reports/physical-ui-latency-20261009/REPORT.md.

## 2026-10-09 startup device failure recovery

- main.py now catches initialization failures locally, retains the home screen and displays wrapped failure/retry guidance. initialize_all retains ownership of partial-startup cleanup; no implicit device substitution or calibration override.
- 25 targeted startup/camera/window tests passed; Python3.12 real-entrypoint probe retained the GUI through two mocked camera failures, with no controller connection or APP_UNHANDLED. Scoped Luna review: no blocker.
- Live log diagnosis: camera index1 supplied no frame while WindowsCamera process was present; physical mirror also refused an uncalibrated board contact offset. Camera readiness and physical calibration remain unresolved/untested. Evidence: reports/startup-camera-recovery-20261009/REPORT.md.

## 2026-10-09 Windows viewer startup repair

- Windows setup now installs pinned local Three.js modules, including dev dependencies; startup checks required assets and reports missing installation with actionable guidance.
- HTTP JS/MJS MIME types are deterministic across Windows associations. RUN.bat forwards CLI options, preserves the Python exit code, and checks the actual Python Moonfish entrypoint.
- Targeted launcher/HTTP/logging gate: 22 tests passed on Python3.11. Python3.12.10 actual HTTP probe verified incorrect OS MIME mappings before/after the patch; browser rendered the virtual robot/board and autoconnected to SIMULATION/IDLE.
- The user's earlier one-off main.mjs error did not reproduce on the already-running server; its exact original cause remains unverified. No physical hardware used. Evidence: `reports/viewer-startup-fix-20261009/REPORT.md`.

## 2026-10-09 selective visual v2 integration

- Selected source `fe3faa8` under all recommendations A; preserve current simulation/R1-R4/geometry/executor/identity/telemetry and defaults. New camera optics/calibration, strict target guard, same-move retry checkpoints, physical worker, and T/H/Y UI adapters. New camera modes off; measured dimensions unset; donor calibration not activated.
- Local evidence: full runner 727 parallel + 8 serial passed; after final guard/recovery refinements, 236 focused tests passed. Replay 10 plies each in three modes with actual PyBullet; 15 robot moves measured before FEN/reconcile, max XY error 0.173 mm in simulation. Rotated/translated R1-R4 hover and viewer reconnect observed.
- Integration remains a selective uncommitted patch, not a merge commit. Camera/FR3 and fresh Python3.12 install unverified. Guide: `docs/VISUAL_V2_INTEGRATION.md`; scope/evidence: `reports/visual-integration-20261009/REPORT.md`.

## 2026-10-06 telemetry liveness fix verified in virtual self-play

- Network callbacks now run outside the asyncio loop with serialized dispatch. Robot/world snapshots coalesce into bounded per-client writers; slow/overflow clients disconnect explicitly. Reconnect replays operation state; older mirror samples cannot rewind telemetry.
- Borrowed virtual snapshots delayed by planning locks are discarded without false stale faults. Physical freshness gates remain unchanged.
- Isolated normal-entrypoint GUI session: 10 total plies (5 each side), two captures, surrender; all 30 remaining identities/cells match, 0 twin.fault and 0 error events. Viewer follows motion and reloads to IDLE with matching final joints; reconnect probes 0.41–0.64s. Six final liveness tests pass; earlier affected gate 21 passes. Main/worktree hashes match for three changed source/test files.
- Changes remain uncommitted. Other game modes were not replayed after this transport fix; hardware and exhaustive trajectories remain unverified. Evidence: `reports/telemetry-fix-20261006/REPORT.md`.

## 2026-10-05 simulation board profile and recovery UI

- Added explicit save/restore of the active R1–R4 simulation pose across restarts, with frame/unit/provenance/calibration version, scene checksum and transit height. Restore uses existing SERVICE_SAFE, version, geometry and swept collision gates; no automatic startup relocation or physical calibration override.
- Recovery panel now shows required action, fault, pending move and execution state. Camera recovery guidance applies to physical mode; virtual mode and manual test have their own guidance. Existing recovery/activation gates remain authoritative.
- Isolated worktree: 70 subsystem checks passed; full unit runner 701 parallel + 8 serial passed (exit 0). After final UI/physical command guard refinements, 35 focused checks passed and viewer syntax check passed. Browser actual save/reset/stale rejection/preparation rejection/restore observed; GUI images retained. Mock physical ordinary/capture commits update real PyBullet/telemetry; failed camera confirmation retains board and blocks repeat motion.
- Luna independent static review: one misleading manual-test instruction corrected, no remaining blocker reported. Eight edited code files have matching main/worktree SHA256. No hardware used; changes remain uncommitted. Guide: `docs/BOARD_PROFILE_AND_RECOVERY.md`; evidence: `reports/profile-recovery-20261005/`.

## 2026-10-05 selective visual integration verified

- Integrated stable corner consensus/operator approval, strict centre pick, independent measurement client/CLI, correction debug, and reimplemented manual pick/place through the unified executor. Preserved simulation, geometry, launcher/logging, read-only physical connect, resize/fullscreen and MOVE_SPEED=70.
- Manual test owns a separate board/identity map; checked movement precedes scene reconciliation. SDK/camera/scene failures latch; game/AI/self-play stay paused until New Game/reconciliation. Physical faults revoke owned activation without gripper/HOME.
- Isolated worktree evidence: broad gate 731 parallel + 8 serial passed; subsequent focused gates 97, 51 and 30 passed. Nine Node contracts and both startup smokes exit 0. Actual manual GUI → PyBullet move after yaw 3 degrees/X +10mm: XY error 0.1504mm before reconciliation; reset preserves taught pose and restores 32 pieces.
- Main working changes retained, not committed/pushed. No real hardware exercised, no exhaustive 8010-route claim. Details: `docs/VISUAL_LATEST_REVIEW_20261005.md`, `reports/visual-integration-20261005/`.

## 2026-10-05 latest visual branch review (historical, before selective integration)

- Fetched `origin/feature/visual-correction-v2` at `652af26`, seven commits beyond donor `e6bb632`. Reviewed in detached worktree; 62 selected tests pass, but mocked SDK/camera probes reproduce two P1 issues in new manual pick/place: continuation after code 112 and repeat commands after failed post-motion verification.
- Stable-corner approval, strict center pick, independent geometry measurement and debug changes are useful candidates. Keep current integration launcher, physical gates, typed results, simulation/viewer and resizing when incorporating them. Visual legacy startup remains physically active by default and must not replace current read-only startup.
- Review only; source not merged or fixed on visual. Evidence: `docs/VISUAL_LATEST_REVIEW_20261005.md`, `reports/visual-review-652af26/`. This is not a whole-repository or hardware safety approval.

## 2026-10-05 cross-feature audit

- Fixed game-only new-game/rollback falsely requiring camera verification; undo uses the logical sync path. Reset now discards the previous SPACE rollback snapshot (an existing baseline bug).
- Broad unit gate: 658 passed / 1 known baseline failure; separate serial gate: 8 passed. Final affected gate: 51 passed; visual application regression: 45 passed. Six of nine selected Node modules pass; three assertion failures reproduce on clean HEAD. Whole regression remains red.
- Actual PyBullet capture after R1–R4 X +10 mm / yaw +3 degrees succeeds before reconciliation (XY error 0.152152 mm); undo restores victim and reset restores 32 pieces while retaining the taught pose. Both launcher startup probes exit 0. No physical hardware exercised.
- Evidence: `docs/CROSS_FEATURE_AUDIT_20261005.md`, `reports/cross-feature-audit-20261005/`. Historical whole-repository review baseline is unchanged.

## 2026-10-05 scoped R1–R4 simulation verification

- UI apply verified in isolated worktree: X +10 mm, then yaw +90 degrees; 32 PyBullet bodies, motion provider, twin and backend versions follow the transform. Actual black pawn pick/place reaches (4,4) before reconciliation, XY error 0.152137 mm.
- Shifted version 2 GUI validation: 90/90 LOCAL CELL TRAJECTORIES PASS. Not a claim for all 8010 routes or physical hardware. Four targeted Python modules: 31 passed; final logging gate: 8 passed; viewer placement integrity Node test passes.
- Disabled unsupported H edits in R1–R4 mode and prevented legacy preview recalculation there. Console encoding failure now fails without logging recursion. Node single-motion-authority test has an existing tool-status fixture failure, reproduced on clean 7d8c5de.
- Evidence: `docs/R1_R4_SIMULATION_AUDIT_20261005.md` and `reports/r1r4-audit-20261005/`. Historical LAST_REVIEWED_HEAD remains unchanged; this is a scoped review of working changes.

## 2026-10-04 game window sizing

- Added a resizable, aspect-preserving display around the existing 1440×1080 logical canvas, fit-to-desktop startup and SDL Windows DPI policy. F11 switches fullscreen; Esc restores the previous window size. Mouse positions are mapped before all menu/game handlers; letterbox margins are ignored.
- Scoped gate: 22 passed via `tools/test_fast.ps1` (window, offline mouse confirmation, difficulty menu), exit 0. Direct Windows SDL probe: 1152×864 → 1920×1080 fullscreen → 1152×864, exit 0. New GUI observed fully within screen bounds.
- Computer Use screen capture works but automated input remains unconfirmed; no complete GUI game was played. Details: `docs/GAME_WINDOW_DISPLAY.md`. Historical whole-repo review baseline remains unchanged.

## 2026-10-04 gripper opening correction

- User-selected open inner surface gap is 27.5 mm. Viewer CAD finger offsets and generated PyBullet hulls share the same offset helper. Direct hull query measures 27.500 mm; fixed shapes, closed CAD vertices and tool frame/length are unchanged.
- Focused verification: 39 passed / 1 fixture failure, then corrected tip-surface obstacle fixture gate 9 passed; the other 31 cases passed with final production geometry. Node viewer/telemetry and syntax checks passed. Evidence: `reports/integration-20261004/gripper-opening-verification.json`. Full regression and physical hardware were not exercised for this change.
- Historical LAST_REVIEWED_HEAD remains unchanged; this is a scoped geometry correction.

## 2026-10-04 simulation capture follow-up

- Baseline b0afeb2: visual physical R_Trash capture already existed; the simulation adapter had a deliberate blanket capture interlock. Replaced it with identity-checked victim pick → floor-slot place/settle → attacker pick/place → game commit.
- Scene capture slots follow the current board XY frame and use the simulated floor as support. A GAME_MOVE operation excludes concurrent mutations across the whole sequence. Existing checked trajectories, release fail-fast and service retreat remain mandatory.
- Exact recorded h9h2 capture succeeds with actual PyBullet positions inspected before reconciliation; blocked landing retains the victim in the gripper and leaves FEN/turn unchanged. Targeted capture 6 passed, adapter/approach 10 passed, combined capture/fail-fast 25 passed. Final full safe regression: 732 passed, exit 0, 470.09 s; slow/hardware tests excluded. Raw evidence is recorded in reports/integration-20261004/capture-full-regression.log. No hardware was operated; arbitrary placement/route coverage is still not claimed.

## 2026-10-04 scoped AI approach correction

- Baseline: `e5e3b74`. First human move `e6 -> e5` followed by AI UCCI `h7e7` reproduced an approach rejection: gripper/red_rook_0 clearance 1.37 mm versus the existing required 2.00 mm.
- `move_joint_with_lift_recovery` now tries the existing SERVICE_SAFE route after a collision-rejected elevated approach even when J5 does not flip. Every segment retains the full MoveJ collision guard; non-collision failures do not trigger this fallback.
- Final targeted gate: 14 passed, exit 0. Actual PyBullet pick/place verified the cannon at cell (2,4) BEFORE logical-board reconciliation. A blocked service route leaves the AI move uncommitted and recovery required. Prior broader run: 96 passed, 2 failed due only to the new test incorrectly expecting a truthy return from `process_human_move`; corrected tests pass. This is a scoped fix, not a whole-branch re-review or proof of every legal route.

# CURRENT_STATE.md — ACTIVE MACHINE-READABLE REPOSITORY STATE

> **R1–R4 placement:** See `docs/R1_R4_BOARD_PLACEMENT_CURRENT.md`. Simulator-generated points are provisional; no physical four-point measurement has been entered. Fixed-axis formulas below are historical, not a general board transform.

## 2026-09-29 camera/GameState/PyBullet/Three.js worktree update

On `feature/unified-robot-vs-robot` at base `b6acba6`, camera-confirmed red/black moves, captures, full-board rescan, semantic robot contexts, and viewer world-state parity have been implemented in an isolated worktree. A one-move rescan infers the next turn; ambiguous multi-change rescans require operator confirmation (`1` Red, `2` Black) before play resumes. Focused Game/Twin regression: 115 passed; Three.js reconciliation: PASS. No physical robot actuation or live-camera accuracy test. Virtual collision guard rejects a black-cannon approach at yaw 0° with gripper/base contact (-0.18 mm); game state stays unchanged. The full `tests/unit` regression was stopped at 92% after multiple failures, many historical yaw-90 tests are stale. Details: `docs/CAMERA_GAME_TWIN_SYNC_2026-09-29.md`. The historical `LAST_REVIEWED_HEAD` below is unchanged until a complete review of the branch is performed.

## 2026-09-26 collision worktree update

This section describes **uncommitted, simulation-only work** on `integration/unified-fr3-system` at `fab750a918c1457ae14bfda900572fb16f846e26`. The historical G90 metrics and test counts below apply to an older checkout; they must not be used as evidence for the current yaw 0° scene. `LAST_REVIEWED_HEAD` below remains historical because the entire dirty worktree has not been reviewed.

### CONTACT-GATED CORRECTION (simulation only)

- The current 22.5 mm rook is **not gripped** by the declared CAD jaw stroke. Direct PyBullet queries at the nominal grasp leave roughly 2-7 mm separation at the two jaws. Closing now returns NO_JAW_CONTACT; no piece is attached and EXECUTE_3STAGE stops at GRASP rather than claiming placement success. Actual stroke, alignment, and grip force still require measurement.
- The carried piece is checked against the floor and every robot link as well as the board and other pieces. Deliberate PyBullet payload penetration into the floor or link 2 is rejected.
- The viewer resolves empty-board clicks through the same board placement transform used to render cells. Piece click metadata follows authoritative nearest_row/nearest_col telemetry. A Node helper test passed; a full browser click session has not been verified.
- The 90/90 and 18/18 acceptance-marked tests check **static simulator IK/collision endpoints only**. They do not verify grip contact, full paths, or hardware safety. Stage-machine tests that need a successful grasp use a documented synthetic bilateral-contact fixture; direct PyBullet contact tests remain unmocked.

### VERIFIED_FIXED (current scope)

- Canonical flange-to-fingertip TCP is 168.3 mm in the active profile; invalid profile data or scene/profile disagreement now fails closed. The collision proxy covers the full axial tool and uses the same transform.
- Adaptive tool yaw: four orthogonal IK candidates yield collision-checked static endpoint poses at 90/90 cells; this is not a successful grasp/contact result.
- Physical FR3 reach envelope: MAX_REACH_RADIUS_M updated from 0.65m to 0.78m in fr3.py, faithful to physical arm span (0.724m from shoulder, ~0.737m-0.864m from base origin), unlocking all 18 key hover & grasp poses.
- PyBullet compound collider 12+7 split ensures all 19 fixed component boxes + 2 moving finger hulls (including viewer_adapter_collar) are registered in physics engine.
- Carried piece payload checks: extended collision verification to floor and robot arm links.
- Pick descent preserves the collision-checked IK jaw orientation. Collision checks include out-of-bounds bodies and the moving attached piece against board and other pieces. Placement releases from 1 mm above the board so the attached piece maintains the 0.5 mm minimum guard clearance until release.
- Repeated board placement updates use the immutable scene surface height, so offsets do not accumulate.

### TEST_EVIDENCE (current scope)

- Direct PyBullet grasp/payload test: 3/3 passed. The nominal rook test asserts an honest NO_JAW_CONTACT failure; synthetic payload penetrations of floor and robot link 2 are rejected.
- Targeted collision and stage-machine fast suite: 99/99 passed. Stage-machine positive grasp cases use synthetic bilateral contact, not actual CAD jaw contact with the nominal rook.
- Viewer helper and existing viewer Node tests passed. The live browser click flow was not exercised.
- An extended fast suite initially returned 44 passed / 11 failed. Two tests in this change set were repaired and rerun (2/2 passed). Nine board-placement/stale-dataset tests remain failing under the active yaw 0 degree scene; the wider suite is not green.
- Historical 90/90 and 18/18 endpoint gates below are not proof of grasp, complete collision-free motion, or hardware safety. No physical robot command was sent.
---

> **Purpose:** Authoritative record of the currently reviewed codebase state. Agents MUST read this file to determine the delta between `LAST_REVIEWED_HEAD` and `HEAD` without rescanning the entire repository.

---

## METADATA
* **CURRENT_BRANCH:** `feature/virtual-robot-3d-simulator`
* **STARTING_REMOTE_HEAD:** `52ae176a6a0a72478693dd32a9b20256c42f6b86`
* **LAST_REVIEWED_HEAD:** `e8ac273`
* **LAST_REVIEWED_FUNCTIONAL_HEAD:** `e8ac273`
* **PASS_A_RUNTIME_AUTHORITY:** `PASS`
* **PASS_A1_REENTRANT_LOCK:** `PASS`
* **PASS_A2_NO_SILENT_QUEUE:** `PASS`
* **PASS_B_SERVICE_SAFE:** `PASS`
* **PASS_C_POST_OP_RETREAT:** `PASS`
* **CORRECTIVE_GEOMETRY_G90:** `PASS`
* **CORRECTIVE_VIEWER_BOOT_AND_COORDINATES:** `PASS`
* **CORRECTIVE_G90_SEMANTIC_CONTRACT:** `PASS`
* **CORRECTIVE_G90_FINAL:** `PASS`
* **SELECTED_PLACEMENT_CANDIDATE:** `d = 15.0 mm, H = 40.0 mm, Z = 0.0 mm`
* **PHASE:** `PHASE_3_SIMULATION_VIRTUAL_TWIN`
* **PHASE_STATUS:** `PARTIAL`
* **CI_STATUS:** `LOCAL_VERIFIED_GREEN`

---

## KEY_GEOMETRY_METRICS
* **Board Yaw:** `+90.0°` around `+Z_robot` ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`)
* **Axis Alignment:** Column axis (span 320 mm) $\to -X_{\text{robot}}$; Row axis (span 360 mm) $\to -Y_{\text{robot}}$
* **Selected Placement:** Forward shift $d = 15.0\text{ mm}$, Safe transit height $H = 40.0\text{ mm}$, Height offset $Z = 0.0\text{ mm}$
* **Reach Margin:** `+24.9 mm` (Max flange approach distance $625.1\text{ mm} < 650.0\text{ mm}$ kinematic reach limit; Max TCP distance $550.3\text{ mm}$)
* **Link Collision Clearance:** `7.69 mm` (Link 1 <-> Link 3 distance at near cells, threshold $0.5\text{ mm}$; zero arm self-collisions)
* **Kinematic Conditioning:** Max Jacobian condition number `21.79` (Well conditioned across all 90 cells, threshold $< 40.0$)
* **Joint Limit Margin:** `9.23°` (Minimum clearance to any joint software limit, threshold $> 5.0^\circ$)
* **Reachability Dataset:** `shared/cell_reachability_dataset.json` (90/90 cells solved, 0 collisions)

---

## VERIFIED_FIXED
The delta between `5f2e84a` and current working tree has been fully reviewed and verified:
1. **[B01] try_grasp Candidate Matching:** Strict single-candidate matching and rejection of mismatched candidate IDs with `GraspStatus.AMBIGUOUS`. (Verified by `test_01_try_grasp_target_matching`, `test_02_try_grasp_target_mismatch_rejection`).
2. **[B02] PlaceResult & GraspStatus Contract:** Formal `PlaceResult` dataclass with backward-compatible dict/bool protocol. (Verified by `test_03_pick_result_fail_fast_contract`).
3. **[B03] PyBullet FR3 Articulated Tracking:** Added `@property def joints_rad` to `RobotStateSnapshot` and `get_robot_joint_positions()` in `VirtualPhysicalWorld`, ensuring real-time tracking of robot joints in PyBullet. (Verified by `test_04_pybullet_fr3_tracking_interpolated`).
4. **[B04] Runtime State Machine, Authority & Concurrency (Pass A, A.1, A.2):** Defined `RuntimeOperationBusy`, implemented `runtime_move_joint()`, routed all WebSocket motion commands through runtime wrappers, closed validation race window by acquiring `acquire_operation_state()` atomically at entry, resolved re-entrant operation lock yielding bug by strictly releasing `_operation_lock` before `yield`, implemented `_operation_depth` tracking, eliminated redundant inner acquisitions, inverted command lock ordering across all 8 runtime wrappers (`runtime_move_joint`, `runtime_go_service_safe`, `runtime_retract_from_board`, `runtime_jog_joint`, `runtime_jog_tcp`, `pick_piece`, `place_piece`, `execute_3stage_trajectory`) so `RuntimeOperationState` acts as the primary admission gate before `_command_lock`, enforced strict non-reentrancy on physical motion operations (`MOTION`, `SERVICE_MOVE`), synchronized validation-in-progress state checking in admission, added deterministic test hooks (`_test_hook_motion_owned`, `_test_hook_service_move_owned`), and proved with timing handshakes that concurrent motions fail fast immediately with `MOTION_REJECTED_BUSY` without silent queueing. (Verified by `test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_1_real_validator_rejects_move_joint_before_release`, `test_a3_2_timing_handshake_proof`, `test_a3_3_full_route_validator_rejects_move_joint`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a6_nested_exception_cleanup`, `test_a7_service_jog_vs_validation`, `test_lock_not_held_across_yield`, `test_a2_1_move_joint_vs_move_joint_no_queue`, `test_a2_2_timing_handshake_proof`, `test_a2_3_move_joint_vs_jog`, `test_a2_4_service_move_vs_move_joint`, `test_a2_5_pick_vs_move_joint`, `test_a2_6_place_vs_jog`, `test_a2_7_3stage_trajectory_vs_move_joint`).
5. **[B05] Ruler Listener De-duplication:** Consolidated 3D ruler update listener to a single authoritative telemetry event listener. (Verified by `test_16_ruler_single_authoritative_update`, `test_viewer_coordinate_ruler.mjs`).
6. **[B06] Wildcard Protection:** Prohibited wildcard `*` in `allowed_grasp_piece_id` across `CollisionGuard` and backend. (Verified by `test_07_collision_guard_explicit_candidate_no_wildcard`).
7. **[B07] Swept Volume Collision Detection & Margin:** Interpolated 3D collision check between current and candidate board pose against arm links with positive clearance margin $\ge 5.0\text{ mm}$ and detailed diagnostics. (Verified by `test_11_swept_volume_collision_arm_obstruction`, `test_12_swept_volume_collision_clear_path`, `test_b6_vertical_board_raise_rejected_when_arm_low`, `test_b7_board_lowering_swept_path`, `test_b8_forward_and_backward_shift_swept_path`, `test_b9_combined_diagonal_swept_path`).
8. **[B08] Validation Cell Loop Indentation Scope:** Corrected block indentation so each cell and route increments and records failures within its respective loop. (Verified by `test_recommended_placement_90_cells_pass`, `test_full_board_routes_validation`).
9. **[B09] SERVICE_SAFE Physical Safety Predicate & Board Adjustment Safety (Pass B):** Resolved candidate pose collision audit: established authoritative Upright Retracted configuration `[0.0, -70.0, 60.0, -80.0, -90.0, 0.0]°` providing $> 129.9\text{ mm}$ moving link clearance and $> 216.3\text{ mm}$ gripper clearance across the entire adjustment envelope ($[-20, 60]\text{ mm}$ shift, $[-10, 30]\text{ mm}$ height offset); implemented full physical safety predicate `evaluate_service_safety()` with `ServiceSafetyReport`; enforced strict `BOARD_ADJUSTMENT_READY` lifecycle token invalidated by any motion, jog, or completed adjustment; ensured 100% state invariance on adjustment rejection. (Verified by `test_b1_service_safe_physical_predicate_clear` through `test_b11_jog_invalidates_service_safe`).
10. **Manual Cartesian & Joint Jogging:** Incremental jog with step size selectors and collision prechecks. (Verified by `test_13_runtime_jog_tcp`, `test_14_runtime_jog_joint`).
11. **In-Process Recovery Actions:** Granular recovery (`clear_error`, `reset_robot`, `reset_board`, `reset_pieces`) and `full_reset` without process termination. (Verified by `test_15_granular_recovery_actions`, `test_17_full_system_reset_in_process`).
12. **[B10] Pass B Corrective: Predicate Methods, Settling Piece Guard, Mandatory Relocation Gate & Swept Exclusion Volume (Pass B Corrective):** Fixed `is_connected()` method invocation on backend; incorporated `PiecePhysicalState.SETTLING` into transient piece physical state check so settling pieces invalidate `is_service_safe()` and `is_board_adjustment_ready`; enforced mandatory `prepare_board_adjustment()` readiness token and fresh physical `evaluate_service_safety()` check before executing `set_board_placement()` (with narrow internal reset bypass); established behavioral regression test fixture (`[0, -60, 125, -135, -90, 0]°`) with proven initial clearance $d_{\text{initial}} = 7.14\text{ mm} > 5.0\text{ mm}$ margin, proving negative board lowering triggers collision at step $k = 1 > 0$ with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` and 100% state invariance; implemented canonical service exclusion volume derived from `self.geom` and `self.placement_state` with PyBullet continuous collision detection across all moving links (0..5) and gripper proxies, and explicitly verified arm link detection inside exclusion volume while TCP is $> 39\text{ mm}$ outside the ceiling. (Verified by `test_bc1_disconnected_backend_rejects_service_safe` through `test_bc12_supported_envelope_boundary_cases_remain_safe`).
13. **[B11] Post-Operation Safe Retreat & Separation of Manipulation from Robot Safety (Pass C & Pass C Corrective):**
   - Defined `PayloadSafetyReport` dataclass and `evaluate_payload_clearance()` predicate in runtime ($z_{\text{piece}} > z_{\text{board}} + 20\text{ mm}$).
   - Extended `PickResult` (`piece_grasped`, `payload_clear`, `requires_recovery`, `payload_safety`) and `PlaceResult` (`piece_placed`, `piece_released`, `post_release_lift_complete`, `board_clear`, `service_safe`, `requires_recovery`, `service_safety`) preserving backward-compatible dict/bool fallback.
   - Enforced sequential trajectory stages on `pick_piece()` (`PREPOSITION` -> `DESCEND` -> `GRASP` -> `LIFT` -> `PAYLOAD_CLEAR` -> `COMPLETE`), reaching payload-safe clearance above board without requiring `SERVICE_SAFE` while piece is attached.
   - Enforced 3-stage post-release retreat on `place_piece()` (`APPROACH` -> `LAND` -> `RELEASE` -> `SETTLE` -> `POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `COMPLETE`), evaluating physical predicate `evaluate_service_safety()`.
   - Decoupled physical piece placement success from post-operation retreat safety so that if piece release succeeds but post-release lift or service retreat fails, `success = False`, `piece_placed = True`, `piece_released = True`, `service_safe = False`, and `requires_recovery = True`.
   - Integrated full Pass C retreat pipeline into `execute_3stage_trajectory()` and WebSocket `EXECUTE_3STAGE`, guaranteeing that manipulation operations never terminate control at `LAND` or low altitude, enforcing `POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `evaluate_service_safety()`.
   - Enforced explicit grasp precheck on `execute_3stage_trajectory(..., grasp_piece=True)`: strictly requires piece at source cell and empty destination cell; fails fast at `PRECHECK` with `status = "PRECHECK_NO_SOURCE_PIECE"` or `status = "PRECHECK_DESTINATION_OCCUPIED"`; never silently downgrades to arm-only transit.
   - Enforced strict fail-fast verification during `CLEAR_BOARD` in `_execute_3stage_trajectory_impl()`: checks return value of Cartesian elevation and joint IK fallback, halts immediately upon motion failure with `status = "CLEAR_BOARD_FAILED"`, `failed_stage = "CLEAR_BOARD"`, `requires_recovery = True`, `service_safe = False`.
   - Enforced strict `GRASP` stage verification in `_execute_3stage_trajectory_impl()`: evaluates grasp success, handles state-update attachment, verifies physical attachment of requested piece, and halts immediately with `status = "GRASP_FAILED"`, `failed_stage = "GRASP"`, `requires_recovery = True`, `service_safe = False` if grasp fails.
   - Enforced physical piece placement verification in both `place_piece()` and `execute_3stage_trajectory()`: piece must be in `ON_BOARD` or `RESTING` physical state, not in transient states (`OUT_OF_BOUNDS`, `FALLING`, `SETTLING`), nearest cell matches target destination within $25\text{ mm}$, and Z altitude matches board surface within $15\text{ mm}$ before declaring `piece_placed = True`. If piece tumbles or is lost during settle, returns `status = "PIECE_PLACEMENT_UNVERIFIED"`, `piece_placed = False`, `service_safe = True`, `requires_recovery = True`.
   - Converted `test_c9_retreat_collision` into a true PyBullet physical collision fixture with a zero-mass obstacle piece `black_cannon_0` positioned at `[-0.434, -0.102, 0.227]`, triggering physical contact detection in `CollisionGuard` during retreat and halting safely with `PLACE_SERVICE_RETREAT_FAILED`, `requires_recovery = True`, `service_safe = False`.
   - Enforced explicit non-manipulation default contract across `EXECUTE_3STAGE` and viewer `goToCell()`: missing/None grasp flags fail-safe strictly to `False` (`should_grasp = False`), preventing unintended piece manipulation when navigating diagnostic cells. Diagnostic `goToCell()` explicitly dispatches `grasp_piece: false`.
    - Added tests `test_c13` through `test_c20`. (Verified by `test_c1_normal_pick_retreat` through `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`).
14. **[B12] Phase 3 Board Orientation 90° Geometry Redesign (Corrective Geometry Gate):**
    - Authoritative 90° board rotation around $+Z_{\text{robot}}$ ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`).
    - Aligned 9-column axis (320 mm) along $-X_{\text{robot}}$ and 10-row axis (360 mm) along $-Y_{\text{robot}}$.
    - Selected placement candidate $(d=15.0\text{ mm}, H=40.0\text{ mm}, Z=0.0\text{ mm})$ via exhaustive candidate evaluation: reach margin $+24.9\text{ mm}$ ($625.1\text{ mm} < 650.0\text{ mm}$), arm link clearance $7.69\text{ mm}$ (link 1 <-> link 3), condition number $21.79$, joint limit margin $9.23^\circ$.
    - Regenerated `shared/cell_reachability_dataset.json` with 90/90 cells solved and 0 collisions.
    - Updated physics transform engine, piece poses, world relocation, runtime cell mapping, viewer mesh, canvas texture, and dimension tape.
    - Implemented dedicated G90-01 through G90-25 test suite in `tests/unit/test_phase3_board_orientation_90.py`. (Verified by `test_phase3_board_orientation_90.py` 25/25 PASSED, `test_phase3_dynamic_board_placement.py` 13/13 PASSED).
15. **[B13] Phase 3 90° Board Migration Corrective: Browser Viewer Boot Recovery & Coordinate Contract Audit:**
    - Resolved fatal boot defect in `createBoardTexture()` where missing `y` coordinates in 4 `ctx.lineTo(x)` calls caused an unhandled `TypeError` during startup, aborting `initApp()` and leaving a blank canvas.
    - Unified coordinate contract `BoardCell(row, col)` with `row` $\in [0, 9]$ and `col` $\in [0, 8]$ across all frontend modules, standardizing `boardPointToXYZ(row, col)` and supporting object overloads `{ row, col }`.
    - Removed stale 0° geometry formulas from `goToCell()` and telemetry handlers in `robot-3d-viewer/main.mjs`, replacing them with canonical 90° formulas ($robX = -0.360 - d/1000 - u$, $robY = -v$, $robZ = 0.0105 + z_{\text{off}}/1000$).
    - Updated `computeGeometricPrecheck()` with canonical 90° extrema ($X_{\text{far}} = 520.0 + d\text{ mm}$, $Y_{\text{far}} = 180.0\text{ mm}$) and synchronized precheck UI readouts with dynamic board placement.
    - Updated `robot-3d-viewer/ruler.mjs` special Z markers (Cột 0: 200mm, Tâm: 360mm, Cột 8: 520mm) and 4-edge hit proxies (Near: 176.5mm, Far: 543.5mm along Z; Left: -205mm, Right: +205mm along X).
    - Verified complete 90-cell parity and 32-piece layout placement in `tests/unit/test_viewer_coordinate_contract.mjs`.
    - Verified live browser boot and WebGL render pipeline via automated headless Chrome CDP test in `tests/unit/test_viewer_browser_smoke.mjs`.
16. **[B14] Phase 3 90° Coordinate Semantics & Backend Contract Corrective (S90 Corrective Gate):**
    - Eliminated remaining legacy row/col semantic inversions across backend, frontend, physics, and telemetry.
    - Defined `BoardCell` frozen dataclass with strict Xiangqi bounds validation $[0..9] \times [0..8]$, sequence indexing, and unpackability.
    - Standardized public API signature everywhere strictly as `(row, col)` with $row \in [0, 9]$ (0 = Black home side, 9 = Red home side - game meaning only) and $col \in [0, 8]$ (col 0 = near side of robot, col 8 = far side of robot).
    - Normalized `robot_xyz_to_nearest_cell` to return canonical `(nearest_r, nearest_c, dist_m)`, eliminating manual coordinate swaps across `runtime.py` and unit tests.
    - Exported `T_robot_from_board` (4x4 SE(3) matrix) in `BoardPlacementState.to_dict()` and aliased `to_telemetry_dict`.
    - Updated `robot-3d-viewer/board.mjs` (`boardPointToXYZ` and `setScenePlacement`) to directly consume authoritative `T_robot_from_board` and `board_yaw_deg`, eliminating hardcoded axis swaps.
    - Renamed DOM readout IDs in `index.html` and `main.mjs` to `#readoutNearGridDepth` and `#readoutFarGridDepth`, and updated selection dropdowns to honest base/depth labels.
    - Created comprehensive regression suite `tests/unit/test_phase3_coordinate_semantics_contract.py` (11/11 tests PASSED) and expanded `tests/unit/test_viewer_coordinate_contract.mjs` (8/8 tests PASSED).
17. **[B15] Phase 3 Final G90 Corrective: Full Route Fail-Fast Integrity, Exhaustive Coverage Reporting & Authoritative Placement Extrema:**
    - Enforced strict fail-fast in `validate_full_board_routes()`: if `CLEAR_BOARD` stage fails, the route terminates immediately with `route_passed = False`, `failed_routes += 1`, `worst_route` records stage `"CLEAR_BOARD"`, and `SERVICE_RETREAT` is never evaluated or executed.
    - Implemented explicit validation modes in `validate_full_board_routes()`: `SAMPLED` (`exhaustive=False`, status `FULL_BOARD_ROUTES_SAMPLE_SAFE`) and `EXHAUSTIVE` (`exhaustive=True`, status `FULL_BOARD_ROUTES_EXHAUSTIVE_SAFE`).
    - Added full coverage telemetry fields: `validation_mode`, `possible_ordered_routes` (8010), `tested_routes`, `passed_routes`, `failed_routes`, `coverage_fraction`, `exhaustive`, `all_routes_safe`. Enforced accounting invariant `passed_routes + failed_routes == tested_routes`.
    - Eliminated hardcoded extrema (`520 + d`, `180`, `200 + d`, `176.5 + d`, `543.5 + d`) from `robot-3d-viewer/main.mjs`, dynamically computing extrema from transformed cell coordinates and board corners via authoritative `BoardPose`.
    - Added dynamic `d_max_for_current_h_mm`, `h_max_for_current_d_mm`, `near_grid_depth_mm`, and `far_grid_depth_mm` to `BoardPlacementAnalyzer.compute_geometric_precheck()`.
    - Corrected reach metric description in `index.html`, viewer, and documentation: strictly labeled 625.1 mm as "Max flange approach distance" ($D_{\text{flange\_app}} = 625.1\text{ mm} < 650.0\text{ mm}$), distinct from TCP distance ($550.3\text{ mm}$).
    - Added comprehensive test suite `tests/unit/test_phase3_final_g90_corrective.py` covering G90F-01 through G90F-14 (14/14 tests PASSED).

---

## OPEN_BLOCKERS
* **Total Count:** 3 (Passes D, E, F)
* **Pass D:** Reset transactionality (ensuring atomic cleanup during system/component resets).
* **Pass E:** Viewer safety UX (front-end safety state guards and error indicators).
* **Pass F:** Final closure (end-to-end integration and simulation phase sign-off).

---

## UNVERIFIED_CLAIMS
* **Real Camera Homography:** The homography transform in `perspective.npy` was calibrated for a physical camera and is unverified against the virtual 3D board scene. (Deferred to Phase 4 calibration).
* **Physical FR3 Robot Interfacing:** `RealFR3Backend` and Ethernet RPC communication with physical hardware remain unverified in the physical world. (Deferred to Phase 4).

---

## TEST_EVIDENCE
* **Python Unit Tests:** 165/165 Phase 3 specific tests PASSED (100% pass rate)
  * `tests/unit/test_phase3_final_g90_corrective.py`: 14 passed (G90F-01 to G90F-14)
  * `tests/unit/test_phase3_coordinate_semantics_contract.py`: 11 passed (S90-01 to S90-13)
  * `tests/unit/test_phase3_board_orientation_90.py`: 25 passed (G90-01 to G90-25)
  * `tests/unit/test_phase3_final_master.py`: 79 passed (including Pass A/A.1/A.2 tests, Pass B/B-Corr tests, and Pass C tests c1–c20)
  * `tests/unit/test_phase3_final_closure.py`: 11 passed
  * `tests/unit/test_phase3_isolation_and_fail_fast.py`: 12 passed
  * `tests/unit/test_phase3_dynamic_board_placement.py`: 13 passed
* **Node.js Viewer Tests:** 7/7 suites PASSED (100% pass rate)
  * `test_viewer_single_motion_authority.mjs`: PASSED
  * `test_viewer_profile_binding.mjs`: PASSED
  * `test_viewer_coordinate_ruler.mjs`: PASSED
  * `test_viewer_gripper_and_telemetry.mjs`: PASSED
  * `test_viewer_canvas_api.mjs`: PASSED
  * `test_viewer_coordinate_contract.mjs`: PASSED (8 tests)
  * `test_viewer_browser_smoke.mjs`: PASSED (V90-01 to V90-05)

---

## NEXT_ALLOWED_WORK
* Pass D — Reset transactionality (ensuring atomic cleanup during system/component resets).

---

## DO_NOT_ADVANCE_TO
* **PHASE 4:** Physical FAIRINO FR3 robot hardware connection, power-on, or physical actuation.
