# CURRENT_STATE.md — ACTIVE MACHINE-READABLE REPOSITORY STATE

> **Purpose:** Authoritative record of the currently reviewed codebase state. Agents MUST read this file to determine the delta between `LAST_REVIEWED_HEAD` and `HEAD` without rescanning the entire repository.

---

## METADATA
* **CURRENT_BRANCH:** `feature/virtual-robot-3d-simulator`
* **LAST_REVIEWED_HEAD:** `88dc791ee8b409d6895746557264382f9957b067`
* **LAST_REVIEWED_FUNCTIONAL_HEAD:** `88dc791ee8b409d6895746557264382f9957b067`
* **PASS_A_RUNTIME_AUTHORITY:** `PASS`
* **PASS_A1_REENTRANT_LOCK:** `PASS`
* **PASS_A2_NO_SILENT_QUEUE:** `PASS`
* **PASS_B_SERVICE_SAFE:** `PASS`
* **PASS_C_POST_OP_RETREAT:** `PASS`
* **PHASE:** `PHASE_3_SIMULATION_VIRTUAL_TWIN`
* **PHASE_STATUS:** `PARTIAL`
* **CI_STATUS:** `LOCAL_VERIFIED_GREEN`

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
* **Python Unit Tests:** 115/115 Phase 3 specific tests PASSED (100% pass rate)
  * `tests/unit/test_phase3_final_master.py`: 79 passed (including Pass A/A.1/A.2 tests, Pass B/B-Corr tests, and Pass C tests c1–c20)
  * `tests/unit/test_phase3_final_closure.py`: 11 passed
  * `tests/unit/test_phase3_isolation_and_fail_fast.py`: 12 passed
  * `tests/unit/test_phase3_dynamic_board_placement.py`: 13 passed
* **Node.js Viewer Tests:** 4/4 suites PASSED
  * `test_viewer_single_motion_authority.mjs`: PASSED
  * `test_viewer_coordinate_ruler.mjs`: PASSED
  * `test_viewer_gripper_and_telemetry.mjs`: PASSED
  * `test_viewer_profile_binding.mjs`: PASSED

---

## NEXT_ALLOWED_WORK
* Pass D — Reset transactionality (ensuring atomic cleanup during system/component resets).

---

## DO_NOT_ADVANCE_TO
* **PHASE 4:** Physical FAIRINO FR3 robot hardware connection, power-on, or physical actuation.
