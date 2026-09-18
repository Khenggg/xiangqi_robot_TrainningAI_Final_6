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
  4. Added `test_bc7` and `test_bc8` using proven fixture configuration `[0.0, -60.0, 125.0, -135.0, -90.0, 0.0]°` with initial clearance $d_{\text{initial}} = 7.14\text{ mm} > 5.0\text{ mm}$ margin, verifying negative lowering collision triggers at step $k = 1 > 0$ with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` and preserves 100% board, piece, and robot joint state invariance. Updated `test_bc9` to explicitly assert that TCP is $> 39\text{ mm}$ above the service exclusion ceiling while moving arm links encroaching the exclusion zone are detected and rejected.
  5. Implemented `check_service_exclusion_occupancy()` in `world.py` utilizing a temporary PyBullet collision shape box querying all FR3 moving links (0..5) and gripper proxies with deterministic cleanup. In `runtime.py`, dynamically computed bounding box dimensions from `self.geom.board_length_m`, `self.geom.board_width_m`, `self.geom.board_thickness_m`, `self.placement_state.board_height_offset_m`, `DEFAULT_SERVICE_XY_MARGIN_M` (0.030m), and `DEFAULT_SERVICE_VERTICAL_CLEARANCE_M` (0.050m).
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_bc1_disconnected_backend_rejects_service_safe` through `test_bc12_supported_envelope_boundary_cases_remain_safe`)
* **Last Verified Functional HEAD:** 097490d1ce95ee3ea87f5caa4f2183b189dfeaf4

---

## B11 — Post-Operation Safe Retreat & Split Physical Manipulation from Service Safety (Pass C & Pass C Corrective)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/physics/collision_guard.py`, `src/simulation/virtual_fr3_backend.py`, `src/simulation/runtime.py`, `tests/unit/test_phase3_final_master.py`
* **Evidence:**
  1. Previously, `place_piece()` returned `success = True` if piece was released, even when post-release lift or service retreat failed with collision/error (`LIFT_FAILED_AFTER_RELEASE`), violating the physical safety contract.
  2. `pick_piece()` did not track trajectory stages (`PREPOSITION` -> `DESCEND` -> `GRASP` -> `LIFT` -> `PAYLOAD_CLEAR` -> `COMPLETE`) or ensure physical payload clearance over the board.
  3. No distinct `PayloadSafetyReport` existed to evaluate safe post-pick holding without demanding `SERVICE_SAFE` (which requires an empty gripper).
  4. Post-release retreat stages (`POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT`) were not monitored in `place_piece()`, and were entirely bypassed in `execute_3stage_trajectory()` / WebSocket `EXECUTE_3STAGE`, leaving the robot at `LAND` or low altitude before reporting `success = True`.
  5. `place_piece()` set `piece_placed = True` without physical position and state verification after release and settle.
  6. `test_c9_retreat_collision` previously used a mock rather than a real physical PyBullet collision fixture.
  7. `execute_3stage_trajectory(..., grasp_piece=True)` on an empty source cell silently fell back to an arm-only transit (`should_grasp = False`) instead of rejecting fast at `PRECHECK`.
  8. `CLEAR_BOARD` motion failure in `_execute_3stage_trajectory_impl()` did not assign fallback `move_joint()` to `ok_clear` or check `ok_clear`, silently falling through to `SERVICE_RETREAT`.
  9. `_execute_3stage_trajectory_impl()` did not verify `try_grasp()` outcome or verify that the requested piece was attached before proceeding to `LIFT`.
  10. `goToCell()` / `EXECUTE_3STAGE` previously inferred grasp intention from board occupancy when `grasp_piece` was missing or `None` (`should_grasp = piece_at_src is not None and piece_at_dst is None`), causing unintended manipulation during diagnostic cell navigation.
* **Fix Summary:**
  1. Defined `PayloadSafetyReport` dataclass and `evaluate_payload_clearance()` runtime predicate ($z_{\text{piece}} > z_{\text{board}} + 20\text{ mm}$).
  2. Extended `PickResult` and `PlaceResult` with typed physical/safety outcome fields, recovery flags, and report objects while preserving dictionary/boolean fallback.
  3. Fixed collision guard palm penetration checks during grasp descent to specifically ignore currently carried pieces, preventing false collisions during retreat.
  4. Decoupled manipulation outcome from robot safety: if release succeeds but retreat fails, `success = False`, `piece_placed = True`, `piece_released = True`, `service_safe = False`, and `requires_recovery = True`.
  5. Enforced that post-operation unsafe state keeps board adjustment strictly locked (`is_board_adjustment_ready == False`).
  6. Integrated full Pass C retreat pipeline (`POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `evaluate_service_safety()`) into `execute_3stage_trajectory()` and WebSocket `EXECUTE_3STAGE`, supporting both pick & place and arm-only transit without leaving the arm in an unretreated state.
  7. Implemented physical placement verification: verifies piece is in `ON_BOARD` or `RESTING` physical state, within $25\text{ mm}$ of target cell intersection and within $15\text{ mm}$ of board surface altitude. Returns `status = "PIECE_PLACEMENT_UNVERIFIED"` if piece tumbles or is lost.
  8. Converted `test_c9_retreat_collision` into a true physical PyBullet collision fixture with a zero-mass obstacle piece `black_cannon_0` at `[-0.434, -0.102, 0.227]`, halting safely with `PLACE_SERVICE_RETREAT_FAILED`, `requires_recovery = True`, `service_safe = False`.
  9. Enforced explicit grasp precheck in `execute_3stage_trajectory()`: if `grasp_piece is True` and `piece_at_src is None`, immediately returns `status = "PRECHECK_NO_SOURCE_PIECE"`, `failed_stage = "PRECHECK"`. If `piece_at_dst is not None`, returns `status = "PRECHECK_DESTINATION_OCCUPIED"`.
  10. Enforced strict fail-fast check on `CLEAR_BOARD`: validates both Cartesian and joint IK fallback, halting with `status = "CLEAR_BOARD_FAILED"`, `failed_stage = "CLEAR_BOARD"`, `requires_recovery = True`, `service_safe = False`.
  11. Added explicit `GRASP` stage verification in `_execute_3stage_trajectory_impl()`, checking `try_grasp` and physical attachment before `LIFT`, halting with `status = "GRASP_FAILED"`, `failed_stage = "GRASP"`, `requires_recovery = True`.
  12. Enforced explicit non-manipulation default contract: `goToCell()` in `robot-3d-viewer/main.mjs` explicitly dispatches `grasp_piece: false`. In `runtime.py`, `_handle_client_command` and trajectory implementations strictly default missing/None grasp flags to `False` (`should_grasp = False`), never guessing grasp intention based on board occupancy. Added regression tests `test_c19_execute_3stage_omitted_grasp_flag_defaults_to_arm_only` (verifying piece unmoved $< 1\text{ mm}$, $d_p < 0.025$, `piece_placed=False`) and `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`.
  13. Added `test_c13` through `test_c20`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_c1_normal_pick_retreat` through `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`)
* **Last Verified Functional HEAD:** 88dc791ee8b409d6895746557264382f9957b067

---

## B12 — Phase 3 Board Orientation 90° Geometry Redesign (G90)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/placement.py`, `src/simulation/physics/transforms.py`, `src/simulation/physics/piece.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `robot-3d-viewer/board.mjs`, `shared/cell_reachability_dataset.json`, `shared/virtual_fr3_scene.json`
* **Evidence:**
  1. Under the nominal 0° orientation, the 10 rows (360 mm span) were oriented along $-X_{\text{robot}}$ and 9 columns (320 mm span) laterally.
  2. Near-side center cells ((4, 0) and (5, 0)) forced link 3 into collision with link 1 during LAND descent at nominal $d = 0$ (clearance $< 0.5\text{ mm}$ self-collision limit).
  3. Positive forward shifts ($d \ge 15\text{ mm}$) to clear link collision pushed far-side row 9 cells close to the robot kinematic reach limit ($650\text{ mm}$), leaving inadequate safety margins.
* **Fix Summary:**
  1. Rotated the Xiangqi board authoritatively by $+90.0^\circ$ around $+Z_{\text{robot}}$ ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`).
  2. The 9-column axis (320 mm playable span) now maps along $-X_{\text{robot}}$, and the 10-row axis (360 mm playable span) maps along $-Y_{\text{robot}}$, substantially reducing the required reach depth along the arm extension axis.
  3. Conducted exhaustive candidate placement evaluation across $(d, H, Z)$ combinations and selected $d = 15.0\text{ mm}, H = 40.0\text{ mm}, Z = 0.0\text{ mm}$.
  4. Selected placement achieves:
     - Kinematic reach margin: $+24.9\text{ mm}$ ($625.1\text{ mm} < 650.0\text{ mm}$)
     - Collision clearance: $7.69\text{ mm}$ (link 1 <-> link 3, safely above $0.5\text{ mm}$ margin)
     - Jacobian condition number: $21.79$ (well conditioned across all 90 cells, $< 40.0$)
     - Joint limit margin: $9.23^\circ$ (above $5.0^\circ$ limit)
  5. Regenerated `shared/cell_reachability_dataset.json` with 90/90 cells solved and 0 collisions.
  6. Updated physics collision bodies, piece placement, PyBullet world relocation, runtime coordinate transforms, viewer 3D board geometry, canvas texture, and dimension tape.
  7. Implemented dedicated unit test suite G90-01 through G90-25 in `tests/unit/test_phase3_board_orientation_90.py`.
* **Regression Test:** `tests/unit/test_phase3_board_orientation_90.py` (25/25 tests), `tests/unit/test_phase3_dynamic_board_placement.py` (13/13 tests)
* **Last Verified Functional HEAD:** b0027e744ccacc3e4dd21f6150271c0fc6f7c2cf

---

## B13 — Phase 3 90° Board Migration Corrective: Browser Viewer Boot Recovery & Coordinate Contract Audit
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/ruler.mjs`, `tests/unit/test_viewer_canvas_api.mjs`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Evidence:**
  1. Fatal boot defect in `createBoardTexture()`: 4 calls to `ctx.lineTo(x)` were missing the `y` parameter in `board.mjs`, causing an unhandled `TypeError` during startup and aborting `initApp()` before WebGL/Three.js rendering or model loading started.
  2. Stale 0° orientation geometry remained in `robot-3d-viewer/main.mjs`: `goToCell(row, col)` computed `robX = -0.180 - d/1000 - row*0.04`, `robY = -0.160 + col*0.04`; `computeGeometricPrecheck()` hardcoded $X_{\text{far}} = 540.0 + d$, $Y_{\text{far}} = 160.0$; and `updateGeometricPrecheckUI()` reported 0° extrema (180, 540, 155, 565 mm).
  3. Non-standardized `boardPointToXYZ(col, row)` parameter ordering inverted arguments vs backend `BoardCell(row, col)`, risking column/row transposition.
  4. Stale 0° markers in `robot-3d-viewer/ruler.mjs`: `specialZMarkers` listed H0: 180mm, H9: 540mm; and board edges hit proxies used length along Z and width along X.
* **Fix Summary:**
  1. Fixed `createBoardTexture()` Canvas API path calls by supplying required `y` arguments to `ctx.lineTo(...)`. Verified across all 45 Canvas path operations in `test_viewer_canvas_api.mjs`.
  2. Standardized `boardPointToXYZ(row, col)` signature and object overload `boardPointToXYZ({ row, col })`, deriving coordinates strictly from canonical 90° orientation math ($u = (col - 4) \times 0.040$, $v = (row - 4.5) \times 0.040$, $X_{\text{world}} = v$, $Z_{\text{world}} = 0.360 + d/1000 + u$).
  3. Updated piece construction (`buildPieces`) and piece relocation (`movePieceTo`) to consume standardized `(row, col)` coordinates.
  4. Refactored `goToCell()` and `applyAuthoritativeBoardPlacement()` in `main.mjs` with canonical 90° formulas ($robX = -0.360 - d/1000 - u$, $robY = -v$, $robZ = 0.0105 + z_{\text{off}}/1000$), standardized label formatting `(Hàng row, Cột col)`, and atomic `updateGeometricPrecheckUI()` dispatch.
  5. Refactored `computeGeometricPrecheck()` with 90° extrema ($X_{\text{far}} = 520.0 + d$, $Y_{\text{far}} = 180.0$) and updated precheck readouts (Col 0: 200 mm, Col 8: 520 mm, Near edge: 176.5 mm, Center: 360 mm, Far edge: 543.5 mm).
  6. Updated `ruler.mjs` special markers (Cột 0: 200mm, Tâm: 360mm, Cột 8: 520mm) and 4-edge hit proxies (Near: 176.5mm, Far: 543.5mm along Z; Left: -205mm, Right: +205mm along X).
  7. Created `test_viewer_coordinate_contract.mjs` verifying 90-cell parity, 32-piece placement, asymmetric cell (2, 7), and dynamic shift invariance.
  8. Created automated headless Chrome CDP smoke test `test_viewer_browser_smoke.mjs` verifying V90-01 through V90-05.
* **Regression Test:** `tests/unit/test_viewer_canvas_api.mjs`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Last Verified Functional HEAD:** 1196f90d1f4b8cf65f02bc0f7e4dfbf6b3fcb590

---

## B14 — Phase 3 90° Coordinate Semantics & Backend Contract Corrective (S90)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/placement.py`, `src/simulation/physics/transforms.py`, `src/simulation/physics/piece.py`, `src/simulation/runtime.py`, `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/index.html`, `tests/unit/test_phase3_coordinate_semantics_contract.py`, `tests/unit/test_viewer_coordinate_contract.mjs`
* **Evidence:**
  1. `runtime.py` had conflicting methods: `cell_to_robot_xyz(col, row)` vs `cell_to_robot_xyz_m(row, col)`, causing confusion and transposition bugs across callers.
  2. `robot_xyz_to_nearest_cell` returned `(c, r, dist)`, which forced all call sites across `runtime.py` and test files to manually perform a tuple swap `r, c = c, r`.
  3. UI DOM IDs `#readoutRow0Dist` and `#readoutRow9Dist` and select dropdown options still described `row 0 = near robot` and `row 9 = far robot`, which contradicts the canonical 90° rotation where column 0 is the near side and column 8 is the far side.
  4. Frontend `boardPointToXYZ` hardcoded axis swaps without directly consuming authoritative `BoardPose` (`TRobotFromBoard`, `board_yaw_deg`).
* **Fix Summary:**
  1. Introduced frozen dataclass `BoardCell` with bounds validation $[0..9] \times [0..8]$, sequence indexing, and unpackability.
  2. Standardized public API signature everywhere strictly as `(row, col)` with $row \in [0, 9]$ (0 = Black home side, 9 = Red home side - game meaning only) and $col \in [0, 8]$ (col 0 = near side of robot, col 8 = far side of robot).
  3. Aligned `robot_xyz_to_nearest_cell` to return `(nearest_r, nearest_c, dist_m)` in canonical order, eliminating manual swaps across `runtime.py` and tests.
  4. Added `T_robot_from_board` (4x4 SE(3) matrix) to `BoardPlacementState.to_dict()` and aliased `to_telemetry_dict`.
  5. Updated `robot-3d-viewer/board.mjs` (`boardPointToXYZ` and `setScenePlacement`) to directly consume authoritative `T_robot_from_board` and `board_yaw_deg`, eliminating hardcoded axis swaps.
  6. Renamed UI elements to `#readoutNearGridDepth` and `#readoutFarGridDepth`, and updated selection dropdowns to honest base/depth labels.
  7. Added comprehensive regression suite `tests/unit/test_phase3_coordinate_semantics_contract.py` (11/11 tests PASSED) and expanded `tests/unit/test_viewer_coordinate_contract.mjs` (8/8 tests PASSED).
* **Regression Test:** `tests/unit/test_phase3_coordinate_semantics_contract.py`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_phase3_board_orientation_90.py`, `tests/unit/test_phase3_final_master.py`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Last Verified Functional HEAD:** 953b77d

---

## B15 — Full Chained Route Fail-Fast Integrity, Coverage Telemetry & Authoritative Placement Extrema (G90 Final Corrective)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/runtime.py`, `src/simulation/placement.py`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/index.html`, `tests/unit/test_phase3_final_g90_corrective.py`
* **Evidence:**
  1. `CLEAR_BOARD` Fail-Fast Violation: In `VirtualXiangqiSimulation.validate_full_board_routes()` (`src/simulation/runtime.py`), if `CLEAR_BOARD` stage failed, the validator silently fell back to `q_curr = q_after_post_lift` and proceeded to attempt `SERVICE_RETREAT`. If retreat succeeded, `passed_routes` was incremented, masking clear-board failures.
  2. Missing Coverage Telemetry & Dual Modes: Full board route validation only tested an ad-hoc 20-route sample without reporting validation mode (`SAMPLED` vs `EXHAUSTIVE`), total possible ordered routes (8010), coverage fraction, or enforcing the invariant `passed_routes + failed_routes == tested_routes`.
  3. Hardcoded Extrema in Viewer Diagnostics: Frontend `robot-3d-viewer/main.mjs` hardcoded extrema formulas (`520 + d`, `180`, `200 + d`, `176.5 + d`, `543.5 + d`) in `computeGeometricPrecheck()` instead of dynamically evaluating transformed `BoardCells` and physical corners via authoritative `BoardPose`.
  4. Metric Wording Imprecision: The 625.1 mm reach metric (which is flange-to-base approach distance) was colloquially described as "Max TCP distance".
* **Fix Summary:**
  1. Enforced strict fail-fast in `validate_full_board_routes()`: if `CLEAR_BOARD` fails, the route fails immediately with `route_passed = False`, `failed_routes += 1`, `worst_route` records stage `"CLEAR_BOARD"`, and `SERVICE_RETREAT` is never evaluated or executed.
  2. Implemented dual validation modes: `SAMPLED` (`exhaustive=False`, status `FULL_BOARD_ROUTES_SAMPLE_SAFE`) and `EXHAUSTIVE` (`exhaustive=True`, status `FULL_BOARD_ROUTES_EXHAUSTIVE_SAFE`). Added explicit telemetry fields (`validation_mode`, `possible_ordered_routes` = 8010, `tested_routes`, `passed_routes`, `failed_routes`, `coverage_fraction`, `exhaustive`, `all_routes_safe`) and enforced accounting invariant `passed_routes + failed_routes == tested_routes`.
  3. Refactored `computeGeometricPrecheck()` in `robot-3d-viewer/main.mjs` and `compute_geometric_precheck()` in `src/simulation/placement.py` to evaluate all 90 cells and 4 board corners dynamically via authoritative `BoardPose` transformations, computing dynamic $d_{\text{max}}$, $H_{\text{max}}$, `near_grid_depth_mm`, and `far_grid_depth_mm`.
  4. Corrected metric wording in `index.html` and documentation: labeled 625.1 mm strictly as "Max flange approach distance" ($D_{\text{flange\_app}} = 625.1\text{ mm} < 650.0\text{ mm}$), distinct from TCP distance ($550.3\text{ mm}$).
  5. Implemented comprehensive test suite `tests/unit/test_phase3_final_g90_corrective.py` covering G90F-01 through G90F-14 (14/14 tests PASSED).
* **Regression Test:** `tests/unit/test_phase3_final_g90_corrective.py` (14/14 tests PASSED), all 7 Node.js viewer tests PASSED.
* **Last Verified Functional HEAD:** e8ac273

---

## I01 — Deprecated `WebSocketServerProtocol` Import in Telemetry Publisher
* **Status:** OPEN (Benign warning)
* **Severity:** LOW
* **Affected Files:** `src/hardware/telemetry_publisher.py`
* **Evidence:** Warning during pytest: `DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated`.
* **Action:** Low impact, server functions normally. Can be migrated to `websockets.asyncio.server.ServerConnection` in a future dependency cleanup.
* **Last Verified HEAD:** 12ce7330393a9014b0ad5e9013e845c8a3bf525e
