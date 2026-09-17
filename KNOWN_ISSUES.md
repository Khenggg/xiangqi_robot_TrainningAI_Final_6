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
* **Evidence:** Previously, `MOVE_JOINT` bypassed `RuntimeOperationState`, validation checked `is_busy` before acquiring `VALIDATING_*`, and re-entrant acquisition in `acquire_operation_state` yielded inside `with self._operation_lock:`, holding the lock across nested long-running operations and blocking concurrent callers. Furthermore, runtime motion wrappers acquired `_command_lock` before `RuntimeOperationState`, allowing competing commands to silently queue rather than failing fast.
* **Fix Summary:** Defined `RuntimeOperationBusy(RuntimeError)`, implemented authoritative `runtime_move_joint()`, routed `_handle_client_command(MOVE_JOINT)` and `RESET` through runtime wrappers, wrapped `validate_board_placement` and `validate_full_board_routes` in atomic outer `acquire_operation_state()`, resolved re-entrant lock yielding bug by strictly releasing `_operation_lock` before `yield`, implemented `_operation_depth` tracking, eliminated redundant inner validation acquisitions, inverted lock acquisition order across all runtime motion and service wrappers to prioritize `RuntimeOperationState` admission over `_command_lock`, enforced non-reentrancy on physical motion states (`MOTION`, `SERVICE_MOVE`), and added test hooks proving immediate fail-fast with `MOTION_REJECTED_BUSY` (no silent queueing).
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_1_real_validator_rejects_move_joint_before_release`, `test_a3_2_timing_handshake_proof`, `test_a3_3_full_route_validator_rejects_move_joint`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a6_nested_exception_cleanup`, `test_a7_service_jog_vs_validation`, `test_lock_not_held_across_yield`, `test_a2_1_move_joint_vs_move_joint_no_queue`, `test_a2_2_timing_handshake_proof`, `test_a2_3_move_joint_vs_jog`, `test_a2_4_service_move_vs_move_joint`, `test_a2_5_pick_vs_move_joint`, `test_a2_6_place_vs_jog`, `test_a2_7_3stage_trajectory_vs_move_joint`)
* **Last Verified Functional HEAD:** 5af7e3442519502c3028b476da126642cc8fa864

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

## B09 — `SERVICE_SAFE` Physical Safety Predicate & Board Relocation Collision Margin
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `src/simulation/virtual_fr3_backend.py`
* **Evidence:** Previously, Candidate 1 (`[0, -25, 40, -105, -90, 0]`) penetrated the board by 22.3mm on forward shifts due to the 218mm tool flange-to-TCP offset; Candidate 2 (`HOME: [0, -45, 90, -45, -90, 0]`) had only 14.8mm clearance to link 4 and penetrated by 15.2mm upon a 30mm board elevation; `is_service_safe()` was a simple joint angle threshold check lacking physical grounding (connection, idle, gripper state, attached pieces, and physical clearance); and `set_board_placement` did not enforce continuous 3D swept volume safety margins ($\ge 5.0\text{ mm}$) or authoritative readiness token consumption.
* **Fix Summary:** Audited both candidates and derived authoritative Upright Retracted configuration `[0.0, -70.0, 60.0, -80.0, -90.0, 0.0]°` ($> 129.9\text{ mm}$ moving link clearance, $> 216.3\text{ mm}$ gripper clearance, condition number $17.67$, joint margin $85.0^\circ$ across full $[-20, 60]\text{ mm}$ shift and $[-10, 30]\text{ mm}$ height envelope); implemented comprehensive `ServiceSafetyReport` and physical predicate `evaluate_service_safety()`; implemented dense 3D interpolated swept volume collision check `check_board_swept_volume_collision()` with positive clearance margin $\ge 5.0\text{ mm}$ and detailed diagnostics; implemented strict `BOARD_ADJUSTMENT_READY` lifecycle token invalidated by any motion/jogging/relocation; and enforced 100% state invariance on board relocation rejection.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_b1_service_safe_physical_predicate_clear` through `test_b11_jog_invalidates_service_safe`, `test_08_is_service_safe_predicate`, `test_09_go_service_safe_motion`, `test_10_prepare_board_adjustment_flow`, `test_12_swept_volume_collision_clear_path`
* **Last Verified Functional HEAD:** 2b50063d446717abff5d89f44e219d270e369230

---

## B10 — Pass B Corrective: SERVICE_SAFE Physical Predicate, Settling State & Swept Exclusion Volume Gaps
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/virtual_fr3_backend.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `tests/unit/test_phase3_final_master.py`, `tests/unit/test_phase3_isolation_and_fail_fast.py`, `tests/unit/test_phase3_dynamic_board_placement.py`
* **Evidence:** 
  1. `backend.is_connected` was inspected as a boolean object rather than invoked as a method (`is_connected()`).
  2. `PiecePhysicalState.SETTLING` was missing from the transient piece state check in `evaluate_service_safety()`, allowing settling pieces to pass service safety.
  3. `set_board_placement()` did not strictly enforce the `_board_adjustment_ready` token and fresh physical `evaluate_service_safety()` check before execution.
  4. Missing behavioral test validating negative board lowering into an obstructing arm/gripper with 100% state invariance upon rejection.
  5. Service exclusion volume used static coordinates rather than canonical geometric derivations from `self.geom` and `self.placement_state`, and did not query all moving arm links (0..5) and gripper proxies via PyBullet collision detection.
* **Fix Summary:**
  1. Updated `virtual_fr3_backend.py` and `runtime.py` to strictly invoke `self.backend.is_connected()`.
  2. Included `PiecePhysicalState.SETTLING` alongside `FALLING` in `evaluate_service_safety()`.
  3. Added strict readiness token validation and fresh physical safety predicate check in `set_board_placement()`, with narrow `internal_reset: bool = False` bypass for reset routines, returning `BOARD_RELOCATION_REJECTED_NOT_READY` and `BOARD_RELOCATION_REJECTED_SERVICE_UNSAFE`.
  4. Added `test_bc7` and `test_bc8` verifying negative lowering collision detection and complete board, piece, and robot joint state invariance on rejection.
  5. Implemented `check_service_exclusion_occupancy()` in `world.py` utilizing a temporary PyBullet collision shape box querying all FR3 moving links (0..5) and gripper proxies with deterministic cleanup. In `runtime.py`, dynamically computed bounding box dimensions from `self.geom.board_length_m`, `self.geom.board_width_m`, `self.geom.board_thickness_m`, `self.placement_state.board_height_offset_m`, `DEFAULT_SERVICE_XY_MARGIN_M` (0.030m), and `DEFAULT_SERVICE_VERTICAL_CLEARANCE_M` (0.050m).
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_bc1_disconnected_backend_rejects_service_safe` through `test_bc12_supported_envelope_boundary_cases_remain_safe`)
* **Last Verified Functional HEAD:** 2b50063d446717abff5d89f44e219d270e369230

---

## I01 — Deprecated `WebSocketServerProtocol` Import in Telemetry Publisher
* **Status:** OPEN (Benign warning)
* **Severity:** LOW
* **Affected Files:** `src/hardware/telemetry_publisher.py`
* **Evidence:** Warning during pytest: `DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated`.
* **Action:** Low impact, server functions normally. Can be migrated to `websockets.asyncio.server.ServerConnection` in a future dependency cleanup.
* **Last Verified HEAD:** 2b50063d446717abff5d89f44e219d270e369230
