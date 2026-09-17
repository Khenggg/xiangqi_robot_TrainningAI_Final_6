# REPO_MAP.md — SUBSYSTEM DIRECTORY & TASK ROUTING TABLE

> **Purpose:** Prevent repository-wide scanning by mapping responsibilities, owned authorities, direct dependencies, and task routing. When assigned a task, consult the Routing Table and open ONLY the mapped files.

---

## 1. CORE SUBSYSTEM MAP

### `src/simulation/runtime.py`
* **Purpose:** Simulation Coordinator & Master Runtime State Machine.
* **Authority Owned:**
  * High-level Pick & Place orchestration (PREPOSITION, LIFT, TRANSIT, LAND)
  * `RuntimeOperationState` transitions (IDLE, MOTION, VALIDATING_LOCAL, VALIDATING_ROUTES, BOARD_ADJUSTMENT, SERVICE_MOVE, RESETTING)
  * Execution-equivalent 90-cell and full-board route validation orchestration
  * Dynamic board relocation lifecycle & version synchronization
  * Telemetry command handler dispatch & in-process recovery actions
* **Direct Dependencies:** `VirtualFR3Backend`, `VirtualPhysicalWorld`, `CollisionGuard`, `BoardPlacementState`, `PlacementPrecheckAnalyzer`.
* **Inspect When:**
  * Pick/place trajectory failures or sequencing errors
  * Validation busy-rejections or state-invariance leaks
  * Board relocation requests, swept-volume checks, or version mismatch
  * Runtime recovery, reset actions, or jogging commands

---

### `src/simulation/virtual_fr3_backend.py`
* **Purpose:** Virtual FAIRINO FR3 Motion Authority.
* **Authority Owned:**
  * Joint motion (`move_joint`, `move_joint_with_lift_recovery`)
  * Cartesian motion (`move_cartesian`, MoveL via analytical IK interpolation)
  * Dry-run trajectory planning (`plan_cartesian`) with step-by-step collision checks
  * Robot state snapshots (`RobotStateSnapshot`, joint angles, TCP pose, flange pose, gripper state)
  * Preposition, IK solving (`solve_tcp_ik`), and `allowed_grasp_piece_id` lifecycle
* **Direct Dependencies:** `FR3Kinematics`, `CollisionGuard`, `VirtualPhysicalWorld`.
* **Inspect When:**
  * Robot fails to reach a Cartesian target or joint configuration
  * Collision guard rejects MoveL / MoveJ trajectories
  * Planner vs execution drift or joint-limit violations
  * Recovery / retreat / service motions

---

### `src/simulation/placement.py`
* **Purpose:** Authoritative Dynamic Board Placement Geometry & Pre-check Analyzer.
* **Authority Owned:**
  * `BoardPlacementState`: Pure math computing board corners, center, and grid origin from `(forward_shift_mm, safe_transit_height_mm, board_height_offset_mm)`.
  * Forward shift mapping: `robot_x = nominal_x0 - forward_shift_m`, `world_z = nominal_z0 + forward_shift_m`.
  * `PlacementPrecheckAnalyzer`: Fast geometric pre-check for approach reachability and land angle margins.
* **Direct Dependencies:** Canonical geometry constants, NumPy.
* **Inspect When:**
  * Board origin, cell coordinates, or surface height mismatches
  * Pre-check candidate analysis discrepancies
  * Placement version calculation or packet serialization issues

---

### `src/kinematics/fr3.py`
* **Purpose:** Fairino FR3 Analytical & Numerical Kinematics.
* **Authority Owned:**
  * 6-DOF Forward Kinematics (FK) and Inverse Kinematics (IK)
  * Joint limits, condition numbers, manipulability metrics, and singularity handling
* **Direct Dependencies:** URDF / DH parameters of FAIRINO FR3 cobot.
* **Inspect When:**
  * IK solver returns unreachable or unexpected joint configurations
  * Near-singularity or high condition number warnings during Land/Lift

---

### `src/simulation/physics/world.py`
* **Purpose:** PyBullet Simulation World & Contact Dynamics.
* **Authority Owned:**
  * PyBullet physics client lifecycle, stepping, and settling dynamics (`step_until_settled`)
  * Board box collider relocation and swept-volume collision detection (`check_board_swept_volume_collision`)
  * Xiangqi piece cylinder multibodies and physical state tracking
  * Gripper grasp attachment, target piece filtering, and release mechanics
  * FR3 robot articulated link visual/kinematic synchronization
* **Direct Dependencies:** `pybullet`, `VirtualGripper`, `XiangqiPieceBody`, `BoardPlacementState`.
* **Inspect When:**
  * Piece physical states (FALLING, SETTLING, RESTING, OUT_OF_BOUNDS) behaving incorrectly
  * Grasp attachment failing or ambiguous candidate errors
  * Board swept-volume collision false-positives or misses
  * PyBullet robot arm joint tracking discrepancies

---

### `src/simulation/physics/collision_guard.py`
* **Purpose:** Fail-Safe Collision Validation Oracle.
* **Authority Owned:**
  * Static configuration validation (`validate_configuration`)
  * Trajectory sample collision validation (`validate_trajectory`)
  * Self-collision distance check (link-to-link margin >= 0.5 mm)
  * Link-to-board and link-to-piece collision checks
  * Single candidate grasp proxy exemption (strictly rejects wildcard `*`)
* **Direct Dependencies:** `pybullet`, `VirtualPhysicalWorld`, `VirtualGripper`.
* **Inspect When:**
  * Motion unexpectedly rejected by collision guard
  * Self-collision false-alarms or undetected tunneling
  * Gripper proxy link collision behavior with pieces

---

### `src/simulation/physics/gripper.py`
* **Purpose:** Virtual Suction / Mechanical Gripper Proxy Model.
* **Authority Owned:**
  * Gripper proxy collision bodies and transform synchronization with robot TCP
  * Grasp eligibility evaluation (distance tolerance <= 15mm, vertical tilt tolerance <= 15 deg)
  * Strict single-piece attachment constraint
* **Direct Dependencies:** `pybullet`, `XiangqiPieceBody`.
* **Inspect When:**
  * Grasp eligibility logic fails at valid grasp poses
  * Gripper proxy bodies collide with board or pieces prematurely

---

### `src/simulation/physics/piece.py` & `src/simulation/physics/state.py`
* **Purpose:** Rigid-Body Piece Model & Typed Result Contracts.
* **Authority Owned:**
  * `PiecePhysicalState` enum and consecutive settled steps tracking
  * Typed result objects: `PickResult`, `PlaceResult`, `GraspResult`, `MotionPlanResult`
* **Inspect When:**
  * API contract mismatches on pick, place, or grasp return types
  * Piece settling threshold or velocity threshold tuning

---

### `src/hardware/telemetry_publisher.py` & `tools/simulation/run_simulation_server.py`
* **Purpose:** WebSocket Server & Real-time State Broadcaster.
* **Authority Owned:**
  * WebSocket broadcasting at `ws://127.0.0.1:8765`
  * Incoming viewer JSON command parsing and forwarding to runtime coordinator
* **Inspect When:**
  * Telemetry stream disconnected or viewer not updating
  * Viewer commands (JOG, RESET, SET_BOARD_PLACEMENT) unhandled

---

### `robot-3d-viewer/` (`main.mjs`, `board.mjs`, `ruler.mjs`, `index.html`)
* **Purpose:** Three.js Digital Twin Visualization & User Controls.
* **Authority Owned:**
  * Three.js rendering of FR3 arm, board, pieces, coordinate axes, and 3D ruler
  * HUD badge displaying live `operation_state`
  * Service & Manual Control panel (jogging buttons, recovery buttons)
  * Coordinate transformations (`world_x = -robot_y`, `world_y = robot_z`, `world_z = -robot_x`)
* **Inspect When:**
  * Visual rendering glitches or piece positions out of sync with PyBullet
  * Ruler measurement inaccuracies or ruler listener race-conditions
  * UI buttons failing to dispatch WebSocket command packets

---

### Datasets & Scene Configs (`shared/`)
* **`shared/virtual_fr3_scene.json`:** Authoritative nominal scene placement and tool configuration.
* **`shared/virtual_physics.json`:** Physics simulation parameters (friction, restitution, settle steps).
* **`shared/cell_reachability_dataset.json`:** Precomputed nominal approach/grasp IK seeds for all 90 cells.

---

## 2. TASK → FILES ROUTING TABLE

When working on a specific task, restrict your scope strictly to the mapped files:

| Task Type | Primary Files to Inspect | Supporting / Verification Files | Tests to Run |
| :--- | :--- | :--- | :--- |
| **Dynamic Board Visual / Placement** | `src/simulation/placement.py`<br>`src/simulation/runtime.py`<br>`robot-3d-viewer/board.mjs` | `robot-3d-viewer/main.mjs`<br>`robot-3d-viewer/ruler.mjs`<br>`src/simulation/physics/world.py` | `pytest tests/unit/test_phase3_dynamic_board_placement.py`<br>`node tests/unit/test_viewer_single_motion_authority.mjs` |
| **Collision Guard / Self-Collision** | `src/simulation/physics/collision_guard.py`<br>`src/simulation/virtual_fr3_backend.py` | `src/simulation/physics/world.py`<br>`src/simulation/physics/gripper.py` | `pytest tests/unit/test_phase3_final_closure.py`<br>`pytest tests/unit/test_phase3_final_master.py -k collision` |
| **Pick & Place / Grasp Contract** | `src/simulation/runtime.py`<br>`src/simulation/physics/world.py`<br>`src/simulation/physics/gripper.py` | `src/simulation/physics/state.py`<br>`src/simulation/virtual_fr3_backend.py` | `pytest tests/unit/test_phase3_isolation_and_fail_fast.py -k pick`<br>`pytest tests/unit/test_phase3_final_master.py -k grasp` |
| **Kinematics / Reachability / IK** | `src/kinematics/fr3.py`<br>`src/simulation/virtual_fr3_backend.py` | `shared/cell_reachability_dataset.json` | `pytest tests/unit/test_phase3_final_closure.py -k reachability` |
| **Viewer UI / HUD / Jogging** | `robot-3d-viewer/index.html`<br>`robot-3d-viewer/main.mjs`<br>`robot-3d-viewer/styles.css` | `src/simulation/runtime.py`<br>`src/hardware/telemetry_publisher.py` | `node tests/unit/test_viewer_single_motion_authority.mjs`<br>`pytest tests/unit/test_phase3_final_master.py -k jog` |
| **Reset / In-Process Recovery** | `src/simulation/runtime.py`<br>`src/simulation/virtual_fr3_backend.py` | `src/simulation/physics/world.py`<br>`robot-3d-viewer/main.mjs` | `pytest tests/unit/test_phase3_isolation_and_fail_fast.py -k reset`<br>`pytest tests/unit/test_phase3_final_master.py -k reset` |
| **Ruler / 3D Dimension Tape** | `robot-3d-viewer/ruler.mjs`<br>`robot-3d-viewer/main.mjs` | `src/simulation/placement.py` | `node tests/unit/test_viewer_coordinate_ruler.mjs`<br>`pytest tests/unit/test_phase3_final_master.py -k ruler` |
