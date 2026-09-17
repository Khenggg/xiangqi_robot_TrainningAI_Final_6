# PROJECT_CONTEXT.md — XIANGQI ROBOT ARCHITECTURAL SPECIFICATION

> **Purpose:** Single source of persistent architectural facts, coordinate contracts, authority boundaries, and physical geometry. Agents MUST read this file first instead of rediscovering constants and architecture.
> **Last Verified HEAD:** 7ce5e71 (Branch: `feature/virtual-robot-3d-simulator`)

---

## 1. PROJECT METADATA
* **Project Name:** Xiangqi Robot (Xiangqi Automated Playing System)
* **Active Phase:** Phase 3 (Virtual 3D Simulator & Digital Twin)
* **Robot Target:** FAIRINO FR3 (6-DOF Collaborative Industrial Arm)
* **Current Working Mode:** SIMULATION ONLY (`VirtualFR3Backend` + PyBullet `VirtualPhysicalWorld`)
* **Future Hardware Target:** Real FAIRINO FR3 via Ethernet RPC SDK (`RealFR3Backend` — strictly Phase 4)

---

## 2. END-TO-END SYSTEM ARCHITECTURE

```text
[Physical Board + Camera] (Real World)
           │
           ▼
[Vision & YOLO11 Pipeline] (1-class occupancy detector: src/vision/)
           │
           ▼
[Game Logic & Xiangqi AI] (Core rules, FEN, engine bestmove: src/core/, src/ai/)
           │
           ▼
[Robot Backend Interface] (BaseBackend contract: src/hardware/backends/base.py)
   ├── VirtualFR3Backend (CURRENT: src/simulation/virtual_fr3_backend.py)
   └── RealFR3Backend    (FUTURE: src/hardware/backends/real_fr3.py - DO NOT USE IN PHASE 3)
           │
           ▼
[Physics & Safety Authority]
   ├── PyBullet Physics World: Rigid bodies, contacts, swept-volume checks (src/simulation/physics/world.py)
   └── Collision Guard Oracle: Self-collision, board collision, proxy margins (src/simulation/physics/collision_guard.py)
           │ (WebSocket Telemetry: port 8765)
           ▼
[Three.js Digital Twin Viewer] (Visualization renderer: robot-3d-viewer/)
```

---

## 3. CORE AUTHORITY BOUNDARIES (NON-NEGOTIABLE)

1. **Robot Motion Authority:**
   * `VirtualFR3Backend` owns MoveJ, MoveL, IK/FK calculations, and robot state reporting.
   * `Three.js` (Viewer) is STRICTLY a visualization sink / renderer. It NEVER has authority to command robot motion or step physics independently.
2. **Physics & Collision Authority:**
   * PyBullet (`VirtualPhysicalWorld`) is the sole ground truth for rigid-body physics, piece contact, settling dynamics, and swept-volume collision detection.
   * `CollisionGuard` is the independent, fail-safe safety oracle. If validation fails or errors, it rejects motion (fail-safe).
3. **Execution-Equivalent Validation:**
   * Path/cell validations must use execution-equivalent planners (`backend.plan_cartesian(..., check_collision=True)`) without committing robot state.
   * PyBullet and backend robot configurations MUST be restored with 100% state invariance in `finally` blocks.
4. **Dynamic Board Placement Consistency:**
   * `placement_version` integer protects against stale planning. Any trajectory planned on version `N` MUST be rejected if current board version is `!= N`.

---

## 4. PHYSICAL GEOMETRY & COORDINATE CONTRACTS

### 4.1. Physical Dimensions
* **Board Dimensions:** `367 mm` (Width along Y) × `410 mm` (Length along X) × `10.5 mm` (Thickness Z).
* **Grid Topology:** 9 columns (Col 0..8) × 10 rows (Row 0..9).
* **Grid Spacing:** `40.0 mm` uniform (row-to-row spacing = 40.0 mm; column-to-column spacing = 40.0 mm).
* **Xiangqi Pieces:** Diameter = `22.5 mm`, Height = `9.43 mm` (Cylinder rigid bodies).
* **Nominal Grid Origin (Cell 0, 0 in Robot Base):** `[-0.180, -0.160, 0.0105] m`.

### 4.2. Coordinate Frame Conventions
* **Robot Base Frame:**
  * Rows increase along `-X_robot` (Row 0 is nearest robot base; Row 9 is furthest).
  * Columns increase along `+Y_robot` (Col 0 is robot right; Col 8 is robot left).
  * `+Z_robot` points vertically upwards.
* **Three.js Digital Twin Viewer Frame:**
  * `world_x = -robot_y`
  * `world_y = +robot_z`
  * `world_z = -robot_x`
* **Authoritative Tool Orientation:**
  * Downward grasp tool orientation: `[180.0, 0.0, 90.0]` degrees (RPY Euler in robot base).
  * Tool frame rigid invariant: Tool flange to suction tip TCP offset is rigid.

### 4.3. Calibration Status & Verification Tags
* Board dimensions: `[VERIFIED]` (Canonical CAD & URDF).
* Grid spacing (40mm): `[VERIFIED]` (Canonical standard board).
* Piece height (9.43mm) & diameter (22.5mm): `[VERIFIED]` (Simulation asset & CAD).
* Camera homography matrix (`perspective.npy`): `[INFERRED / PHYSICAL UNVERIFIED]` (Requires physical recalibration upon real camera mount in Phase 4).

---

## 5. PROJECT SAFETY DOCTRINE

1. **Simulation-Only In Phase 3:**
   * Strictly NO connection, commands, power-up, or actuation of a physical FAIRINO FR3 robot.
2. **No Silent Success / No Silent Failure:**
   * Every motion, grasp, and placement operation MUST return an explicit typed result object (`PickResult`, `PlaceResult`, `GraspResult`, `MotionPlanResult`).
   * Silent fallbacks or returning `True` when an underlying step failed are strictly forbidden.
3. **`UNKNOWN` is Valid and Truthful:**
   * When data or verification is incomplete, state `UNKNOWN` or `UNVERIFIED`. Do not fabricate synthetic pass results.
4. **Collision Guard Dominates:**
   * Collision margins (minimum 0.5 mm self-collision, link-to-board, link-to-gripper) must NEVER be weakened to force tests or motions to pass.
5. **Evidence-First Verification:**
   * Never claim a test passes or an issue is resolved without actual terminal execution evidence (pass count, exit code 0).
