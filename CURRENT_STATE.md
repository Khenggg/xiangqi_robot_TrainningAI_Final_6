# CURRENT_STATE.md — ACTIVE MACHINE-READABLE REPOSITORY STATE

> **Purpose:** Authoritative record of the currently reviewed codebase state. Agents MUST read this file to determine the delta between `LAST_REVIEWED_HEAD` and `HEAD` without rescanning the entire repository.

---

## METADATA
* **CURRENT_BRANCH:** `feature/virtual-robot-3d-simulator`
* **STARTING_REMOTE_HEAD:** `ad91f5d5e40f0eae0819ad6932130578a380dda4`
* **LAST_REVIEWED_HEAD:** `953b77d`
* **LAST_REVIEWED_FUNCTIONAL_HEAD:** `953b77d`
* **PASS_A_RUNTIME_AUTHORITY:** `PASS`
* **PASS_A1_REENTRANT_LOCK:** `PASS`
* **PASS_A2_NO_SILENT_QUEUE:** `PASS`
* **PASS_B_SERVICE_SAFE:** `PASS`
* **PASS_C_POST_OP_RETREAT:** `PASS`
* **CORRECTIVE_GEOMETRY_G90:** `PASS`
* **CORRECTIVE_VIEWER_BOOT_AND_COORDINATES:** `PASS`
* **CORRECTIVE_G90_SEMANTIC_CONTRACT:** `PASS`
* **SELECTED_PLACEMENT_CANDIDATE:** `d = 15.0 mm, H = 40.0 mm, Z = 0.0 mm`
* **PHASE:** `PHASE_3_SIMULATION_VIRTUAL_TWIN`
* **PHASE_STATUS:** `PARTIAL`
* **CI_STATUS:** `LOCAL_VERIFIED_GREEN`

---

## KEY_GEOMETRY_METRICS
* **Board Yaw:** `+90.0°` around `+Z_robot` ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`)
* **Axis Alignment:** Column axis (span 320 mm) $\to -X_{\text{robot}}$; Row axis (span 360 mm) $\to -Y_{\text{robot}}$
* **Selected Placement:** Forward shift $d = 15.0\text{ mm}$, Safe transit height $H = 40.0\text{ mm}$, Height offset $Z = 0.0\text{ mm}$
* **Reach Margin:** `+24.9 mm` (Max TCP distance $625.1\text{ mm} < 650.0\text{ mm}$ kinematic reach limit)
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
* **Python Unit Tests:** 151/151 Phase 3 specific tests PASSED (100% pass rate)
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
