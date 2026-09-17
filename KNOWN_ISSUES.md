# KNOWN_ISSUES.md — COMPACT ISSUE & REGRESSION TRACKER

> **Purpose:** Persistent tracking of bugs, blockers, and edge cases. Prevents agents from rediscovering solved bugs or re-investigating known characteristics.

---

## B01 — `try_grasp` Target Piece Filtering Contract Mismatch
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/world.py`, `src/simulation/runtime.py`
* **Evidence:** Previously, `try_grasp()` evaluated all candidates blindly. If adjacent pieces were nearby, ambiguous candidate selection occurred.
* **Fix Summary:** Updated `try_grasp(target_piece_id=...)` to strictly filter candidates to the requested piece ID, returning `GraspStatus.AMBIGUOUS` on mismatch.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_01_try_grasp_target_matching`, `test_02_try_grasp_target_mismatch_rejection`
* **Last Verified HEAD:** 7ce5e71

---

## B02 — Missing Typed `PlaceResult` and `GraspStatus.PARTIAL` Contract
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/runtime.py`
* **Evidence:** `place_piece()` returned raw booleans/dicts lacking unified typed attribute access (`.success`, `.status`, `.piece_id`).
* **Fix Summary:** Created `PlaceResult` dataclass with dictionary/boolean fallback protocol matching `PickResult`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_03_pick_result_fail_fast_contract`
* **Last Verified HEAD:** 7ce5e71

---

## B03 — Articulated PyBullet FR3 Kinematic Synchronization
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/hardware/backends/base.py`, `src/simulation/physics/world.py`
* **Evidence:** `RobotStateSnapshot` lacked `.joints_rad` property, causing PyBullet link synchronization listeners to crash or leave the simulated arm as a stale ghost pose.
* **Fix Summary:** Added `@property def joints_rad` to `RobotStateSnapshot` and implemented `get_robot_joint_positions()` on `VirtualPhysicalWorld`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_04_pybullet_fr3_tracking_interpolated`
* **Last Verified HEAD:** 7ce5e71

---

## B04 — Validation vs Motion Mutual Exclusion Atomicity & Single Authority
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/runtime.py`
* **Evidence:** Previously, `MOVE_JOINT` bypassed `RuntimeOperationState`, and validation checked `is_busy` before acquiring `VALIDATING_*`, leaving a race window where PyBullet joint configurations could be snapshot or mutated concurrently.
* **Fix Summary:** Defined `RuntimeOperationBusy(RuntimeError)`, implemented authoritative `runtime_move_joint()`, routed `_handle_client_command(MOVE_JOINT)` and `RESET` through runtime wrappers, wrapped `validate_board_placement` and `validate_full_board_routes` in atomic outer `acquire_operation_state()`, and enforced thread-owner re-entrancy for nested sub-tasks.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a7_service_jog_vs_validation`

---

## B05 — Duplicate 3D Ruler Telemetry Update Listener
* **Status:** FIXED
* **Severity:** MEDIUM
* **Affected Files:** `robot-3d-viewer/ruler.mjs`, `robot-3d-viewer/main.mjs`
* **Evidence:** Duplicate `updateBoardPlacement` listener caused race conditions and out-of-sync distance measurements on dynamic board shifts.
* **Fix Summary:** Centralized 3D ruler update into a single authoritative `placement_state` telemetry handler.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_16_ruler_single_authoritative_update`, `tests/unit/test_viewer_coordinate_ruler.mjs`
* **Last Verified HEAD:** 7ce5e71

---

## B06 — Wildcard Protection in Collision Guard
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/collision_guard.py`, `src/simulation/virtual_fr3_backend.py`
* **Evidence:** Passing `allowed_grasp_piece_id="*"` effectively bypassed all piece collision checking.
* **Fix Summary:** Enforced explicit validation rejecting wildcard strings (`*`) with `ValueError`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_07_collision_guard_explicit_candidate_no_wildcard`
* **Last Verified HEAD:** 7ce5e71

---

## B07 — Swept Volume Collision When Robot Arm Obstructs Relocation
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/world.py`, `src/simulation/runtime.py`
* **Evidence:** Changing board placement while robot arm was parked low over board caused unmonitored visual clipping / physical overlap.
* **Fix Summary:** Implemented `check_board_swept_volume_collision()` interpolating bounding boxes against arm links. Rejects relocation with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` if path is blocked.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_11_swept_volume_collision_arm_obstruction`, `test_12_swept_volume_collision_clear_path`
* **Last Verified HEAD:** 7ce5e71

---

## B08 — Validation Cell Loop Indentation Scope
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/runtime.py`
* **Evidence:** `if cell_passed:` in `validate_board_placement()` and `passed_routes += 1` in `validate_full_board_routes()` were indented outside inner column/route loops, leading to inaccurate failure counts.
* **Fix Summary:** Corrected block indentation so each cell and route increments and records failures within its respective loop.
* **Regression Test:** `tests/unit/test_phase3_dynamic_board_placement.py::DynamicBoardPlacementTests::test_recommended_placement_90_cells_pass`, `test_full_board_routes_validation`
* **Last Verified HEAD:** 7ce5e71

---

## I01 — Deprecated `WebSocketServerProtocol` Import in Telemetry Publisher
* **Status:** OPEN (Benign warning)
* **Severity:** LOW
* **Affected Files:** `src/hardware/telemetry_publisher.py`
* **Evidence:** Warning during pytest: `DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated`.
* **Action:** Low impact, server functions normally. Can be migrated to `websockets.asyncio.server.ServerConnection` in a future dependency cleanup.
* **Last Verified HEAD:** 7ce5e71
