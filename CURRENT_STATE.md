# CURRENT_STATE.md — ACTIVE MACHINE-READABLE REPOSITORY STATE

> **Purpose:** Authoritative record of the currently reviewed codebase state. Agents MUST read this file to determine the delta between `LAST_REVIEWED_HEAD` and `HEAD` without rescanning the entire repository.

---

## METADATA
* **CURRENT_BRANCH:** `feature/virtual-robot-3d-simulator`
* **HEAD:** `2edfed83cf254ad0e0fccd3fc25645ca9345c854`
* **LAST_REVIEWED_HEAD:** `2edfed83cf254ad0e0fccd3fc25645ca9345c854`
* **PASS_A_RUNTIME_AUTHORITY:** `PASS`
* **PASS_A1_REENTRANT_LOCK:** `PASS`
* **PHASE:** `PHASE_3_SIMULATION_VIRTUAL_TWIN`
* **PHASE_STATUS:** `PARTIAL`
* **CI_STATUS:** `LOCAL_VERIFIED_GREEN`

---

## VERIFIED_FIXED
The delta between `5f2e84a` and current working tree has been fully reviewed and verified:
1. **[B01] try_grasp Candidate Matching:** Strict single-candidate matching and rejection of mismatched candidate IDs with `GraspStatus.AMBIGUOUS`. (Verified by `test_01_try_grasp_target_matching`, `test_02_try_grasp_target_mismatch_rejection`).
2. **[B02] PlaceResult & GraspStatus Contract:** Formal `PlaceResult` dataclass with backward-compatible dict/bool protocol. (Verified by `test_03_pick_result_fail_fast_contract`).
3. **[B03] PyBullet FR3 Articulated Tracking:** Added `@property def joints_rad` to `RobotStateSnapshot` and `get_robot_joint_positions()` in `VirtualPhysicalWorld`, ensuring real-time tracking of robot joints in PyBullet. (Verified by `test_04_pybullet_fr3_tracking_interpolated`).
4. **[B04] Runtime State Machine, Authority & Concurrency (Pass A & A.1):** Defined `RuntimeOperationBusy`, implemented `runtime_move_joint()`, routed all WebSocket motion commands through runtime wrappers, closed validation race window by acquiring `acquire_operation_state()` atomically at entry, resolved re-entrant operation lock yielding bug by strictly releasing `_operation_lock` before `yield`, implemented `_operation_depth` tracking, eliminated redundant inner acquisitions in `validate_board_placement` and `validate_full_board_routes`, added deterministic pause test hooks, and verified zero blocking / instant `MOTION_REJECTED_BUSY` response under real validation concurrency. (Verified by `test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_1_real_validator_rejects_move_joint_before_release`, `test_a3_2_timing_handshake_proof`, `test_a3_3_full_route_validator_rejects_move_joint`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a6_nested_exception_cleanup`, `test_a7_service_jog_vs_validation`, `test_lock_not_held_across_yield`).
5. **[B05] Ruler Listener De-duplication:** Consolidated 3D ruler update listener to a single authoritative telemetry event listener. (Verified by `test_16_ruler_single_authoritative_update`, `test_viewer_coordinate_ruler.mjs`).
6. **[B06] Wildcard Protection:** Prohibited wildcard `*` in `allowed_grasp_piece_id` across `CollisionGuard` and backend. (Verified by `test_07_collision_guard_explicit_candidate_no_wildcard`).
7. **Service Safe Pose:** Canonical joint angles `[0.0, -25.0, 40.0, -105.0, -90.0, 0.0]°` and `is_service_safe()` predicate. (Verified by `test_08_is_service_safe_predicate`, `test_09_go_service_safe_motion`).
8. **Board Adjustment Preparation Flow:** Safe parking in `SERVICE_SAFE` and settling check before board movement. (Verified by `test_10_prepare_board_adjustment_flow`).
9. **Swept-Volume Collision Detection:** Interpolated collision check between current and candidate board pose against arm links. (Verified by `test_11_swept_volume_collision_arm_obstruction`, `test_12_swept_volume_collision_clear_path`).
10. **Manual Cartesian & Joint Jogging:** Incremental jog with step size selectors and collision prechecks. (Verified by `test_13_runtime_jog_tcp`, `test_14_runtime_jog_joint`).
11. **In-Process Recovery Actions:** Granular recovery (`clear_error`, `reset_robot`, `reset_board`, `reset_pieces`) and `full_reset` without process termination. (Verified by `test_15_granular_recovery_actions`, `test_17_full_system_reset_in_process`).

---

## OPEN_BLOCKERS
* **Total Count:** 0
* No active blocking bugs in simulation runtime, collision guard, kinematics, or viewer integration.

---

## UNVERIFIED_CLAIMS
* **Real Camera Homography:** The homography transform in `perspective.npy` was calibrated for a physical camera and is unverified against the virtual 3D board scene. (Deferred to Phase 4 calibration).
* **Physical FR3 Robot Interfacing:** `RealFR3Backend` and Ethernet RPC communication with physical hardware remain unverified in the physical world. (Deferred to Phase 4).

---

## TEST_EVIDENCE
* **Python Unit Tests:** 65/65 Phase 3 specific tests PASSED (100% pass rate)
  * `tests/unit/test_phase3_final_master.py`: 29 passed (including mandatory Pass A & A.1 tests A1-A7, A3.1, A3.2, A3.3, A6.2, lock yield)
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
* Development of automated Board Placement Optimization search algorithms within Phase 3 simulation scope.
* Enhancement of telemetry visualization and performance profiling.

---

## DO_NOT_ADVANCE_TO
* **PHASE 4:** Physical FAIRINO FR3 robot hardware connection, power-on, or physical actuation.
