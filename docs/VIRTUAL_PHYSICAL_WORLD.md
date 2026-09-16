# VIRTUAL PHYSICAL WORLD SPECIFICATION & RUNTIME ARCHITECTURE (PHASE P3)

**Repository:** `Khenggg/xiangqi_robot_TrainningAI_Final_6`  
**Branch:** `feature/virtual-robot-3d-simulator`  
**Status:** Implemented & Verified in Phase P3  
**Simulation Mode:** Headless PyBullet (`p.DIRECT`)  

---

## 1. Executive Summary

Phase P3 extends the Virtual FAIRINO FR3 Simulator by embedding a native **PyBullet** rigid-body physics engine into the simulation runtime. This transforms the 3D viewer from a passive kinematic joint visualizer into an interactive, physics-driven digital twin capable of:
- Simulating 32 Xiangqi pieces as discrete rigid bodies with contact dynamics, mass, friction, and restitution.
- Simulating a finite Xiangqi board with realistic surface elevation and boundary drop-offs.
- Modeling a procedural two-jaw gripper (`VirtualGripper`) with capture volume checks, candidate ambiguity rejection, and relative-transform invariant grasp attachments.
- Executing dynamic in-flight release and emergency force-drop primitives with physical ballistic velocity inheritance.
- Streaming real-time 3D rigid-body telemetry (`world_state`) over WebSocket to Three.js viewer at 30 FPS.

> [!IMPORTANT]
> **Zero Hardware Actuation Policy:** Phase P3 runs 100% in software simulation. No real robot RPC calls, network connections to `192.168.58.2`, or physical actuator triggers are made.

---

## 2. Unverified Physical Parameters Notice

Parameters derived directly from calibrated physical measurements (such as piece diameter $22.5\text{ mm}$, piece height $9.43\text{ mm}$, outer board dimensions $367 \times 410\text{ mm}$, grid spacing $40 \times 40\text{ mm}$) originate from the canonical source of truth `shared/physical_geometry.json`.

Dynamic parameters that have not been experimentally measured on the physical board (e.g. piece mass, coefficient of restitution, friction coefficients, contact stiffness) are explicitly cataloged in `shared/virtual_physics.json` under the metadata tag:
```json
{
  "parameter_provenance": "SIMULATION_ONLY_UNVERIFIED_PHYSICAL_PARAMETERS"
}
```
These values have been chosen conservatively for numerical stability in PyBullet:
- Piece Mass: $0.020\text{ kg}$ (20 grams)
- Lateral Friction: $0.50$
- Rolling Friction: $0.001$
- Spinning Friction: $0.001$
- Restitution: $0.05$ (low bounciness for stable settling)
- Physics Timestep: $1/240\text{ s}$ ($4.167\text{ ms}$) with 50 solver iterations per step (matching `shared/virtual_physics.json`).

---

## 3. Physical Coordinates and Reference Frames

The physical world operates strictly within the authoritative **Robot Base Coordinate Frame** ($X_{\text{robot}}, Y_{\text{robot}}, Z_{\text{robot}}$), ensuring identity transformation with the robot kinematics backend.

### 3.1. Canonical Reference Frames
1. **Robot Base Frame (`robot_base`)**:
   - Origin $(0, 0, 0)$: Base center of FR3.
   - $-X$: Extends forward across the board toward Row 9 (Player Red).
   - $+Y$: Extends laterally to the robot's left across columns (Col 0 $\to$ Col 8).
   - $+Z$: Extends vertically upward against gravity ($g = -9.81\text{ m/s}^2$).
2. **Three.js World Frame (`world_3d`)**:
   - Transformed via canonical scene rotation matrix $R_{\text{scene}}$:
     $$\begin{bmatrix} X_{\text{world}} \\ Y_{\text{world}} \\ Z_{\text{world}} \end{bmatrix} = \begin{bmatrix} 0 & 1 & 0 \\ 0 & 0 & 1 \\ -1 & 0 & 0 \end{bmatrix} \begin{bmatrix} X_{\text{robot}} \\ Y_{\text{robot}} \\ Z_{\text{robot}} \end{bmatrix}$$
   - $X_{\text{world}} = Y_{\text{robot}}$ (lateral along columns)
   - $Y_{\text{world}} = Z_{\text{robot}}$ (vertical height, up)
   - $Z_{\text{world}} = -X_{\text{robot}}$ (forward along rows)
   - Determinant $\det(R_{\text{scene}}) = +1.0$ (proper rotation, preserves chirality).

### 3.2. Board Physical Collider Bounds
- Center: $(-0.360, 0.000, 0.030)\text{ m}$ (in `robot_base`)
- Surface elevation $Z_{\text{surface}} = +0.050\text{ m}$
- Bounding Box:
  - $X \in [-0.565\text{ m}, -0.155\text{ m}]$ (Length: $410\text{ mm}$)
  - $Y \in [-0.1835\text{ m}, +0.1835\text{ m}]$ (Width: $367\text{ mm}$)
  - $Z \in [0.010\text{ m}, 0.050\text{ m}]$ (Thickness: $40\text{ mm}$)

---

## 4. Piece Spawning & Rigid-Body Modeling

All 32 Xiangqi pieces are spawned at simulation initialization based on canonical layout definitions in `shared/xiangqi_start_layout.json` and geometry from `src/domain/geometry.py`:

```
Side: Black (Robot, rows 0-4)
- 1 General (King):   black_king_0       (col=4, row=0)
- 2 Advisors:         black_advisor_0,1  (col=3,5, row=0)
- 2 Elephants:        black_elephant_0,1 (col=2,6, row=0)
- 2 Knights (Horses): black_knight_0,1   (col=1,7, row=0)
- 2 Rooks (Chariots): black_rook_0,1     (col=0,8, row=0)
- 2 Cannons:          black_cannon_0,1   (col=1,7, row=2)
- 5 Pawns (Soldiers): black_pawn_0..4    (col=0,2,4,6,8, row=3)

Side: Red (Opponent, rows 5-9)
- 1 General (King):   red_king_0         (col=4, row=9)
- 2 Advisors:         red_advisor_0,1    (col=3,5, row=9)
- 2 Elephants:        red_elephant_0,1   (col=2,6, row=9)
- 2 Knights (Horses): red_knight_0,1     (col=1,7, row=9)
- 2 Rooks (Chariots): red_rook_0,1       (col=0,8, row=9)
- 2 Cannons:          red_cannon_0,1     (col=1,7, row=7)
- 5 Pawns (Soldiers): red_pawn_0..4      (col=0,2,4,6,8, row=6)
```

Each piece is modeled in PyBullet as a `GEOM_CYLINDER` collision shape with cylinder axis along local $Z$:
- Radius $R = 11.25\text{ mm}$ ($0.01125\text{ m}$)
- Height $H = 9.43\text{ mm}$ ($0.00943\text{ m}$)
- Mass $m = 0.020\text{ kg}$
- Upright initial orientation: Identity quaternion $[0, 0, 0, 1]$.

---

## 5. Procedural Gripper & Grasp Kinematics

The gripper is managed by `VirtualGripper` configured via `shared/virtual_gripper_profile.json`.

### 5.1. Capture Volume
To initiate a physical grasp, the gripper must be positioned such that a target piece falls strictly within its geometric capture cylinder centered at `tcp_to_grasp_center` ($[0, 0, 0.035]\text{ m}$ in tool frame), defined strictly in `shared/virtual_gripper_profile.json`:
- Horizontal Capture Radius: $r_{xy} \le 16.0\text{ mm}$ ($0.016\text{ m}$)
- Vertical Half-Height: $|\Delta z| \le 12.0\text{ mm}$ ($0.012\text{ m}$)
- Stroke Limits: $\text{open\_width\_m} = 0.040\text{ m}$ ($40.0\text{ mm}$), $\text{closed\_width\_m} = 0.020\text{ m}$ ($20.0\text{ mm}$)
- Grasp Eligibility Check: Requires $\text{is\_closed} = \text{True}$.

### 5.2. Ambiguity Rejection
If more than one candidate piece falls within the capture volume simultaneously, the grasp fails with `GraspStatus.AMBIGUOUS`. This prevents non-deterministic multi-piece attachments.

### 5.3. Relative-Transform Invariant Attachment
When a grasp succeeds, the piece is attached rigidly to the gripper grasp frame via relative transform $T_{\text{gripper\_piece}}$:
$$T_{\text{gripper\_piece}} = T_{\text{gripper}}^{-1} \cdot T_{\text{piece}}$$
For any subsequent gripper pose $T_{\text{gripper}}(t)$ during arm trajectory execution, the world pose of the piece is evaluated analytically:
$$T_{\text{piece}}(t) = T_{\text{gripper}}(t) \cdot T_{\text{gripper\_piece}}$$
The piece preserves its canonical mass ($0.020\text{ kg}$) in PyBullet, while its pose is deterministically updated kinematically each simulation step via `resetBasePositionAndOrientation`. Collision pairs between the piece and the 3 gripper proxy bodies are temporarily disabled via `setCollisionFilterPair` to eliminate constraint conflicts. This guarantees zero slip, zero numerical drift, and exact preservation of relative offset regardless of arbitrary 6-DOF translation and rotation.

### 5.4. PyBullet Gripper Collision Proxies (Phase P3.1 & P3.2)
The gripper instantiates 3 kinematic PyBullet collision proxies driven directly by `shared/virtual_gripper_profile.json`:
- **Palm proxy:** Box shape ($60 \times 40 \times 30\text{ mm}$), positioned at $[0, 0, \text{palm\_dz}/2]$ from TCP.
- **Left jaw proxy:** Box shape ($8 \times 25 \times 35\text{ mm}$), translating along `travel_axis` ($X$) to $-w/2$.
- **Right jaw proxy:** Box shape ($8 \times 25 \times 35\text{ mm}$), translating along `travel_axis` ($X$) to $+w/2$.

**Attachment Collision Filtering Policy:**
- While attached: PyBullet collision pairs between the attached piece body and all 3 gripper proxy bodies are disabled via `p.setCollisionFilterPair(..., enableCollision=0)`. This prevents internal constraint fighting and solver explosion.
- Upon release / force-drop: Collision pairs between the piece and proxy bodies are immediately re-enabled via `p.setCollisionFilterPair(..., enableCollision=1)`.

---

## 6. Dynamic Release and Mid-Motion Force Drop Mechanics

### 6.1. True Mid-Motion Force Drop (Phase P3.1 & P3.2)
Phase P3.1/P3.2 implements authoritative mid-motion force drop evaluated synchronously within the robot state update listener (`_on_robot_state_update`):
1. **Trigger Condition:** Evaluated while `snapshot.motion_state == "MOVING"` and trajectory progress exceeds `progress_threshold` (e.g. 50%).
2. **Velocity Inheritance:** Velocity is estimated from backwards finite differences over historical trajectory steps where $\Delta t > 10^{-6}\text{ s}$:
   $$\mathbf{v} = \frac{\mathbf{p}(t) - \mathbf{p}(t - \Delta t)}{\Delta t}$$
   Guarantees non-zero release velocity ($> 0.02\text{ m/s}$, typically $0.5 - 1.5\text{ m/s}$ in fast moves).
3. **Independent Ballistic Flight:** The piece is detached and injected into PyBullet with inherited linear and angular velocities. The piece tumbles and settles on the board under gravity and friction while the robot arm independently continues along its trajectory to completion.
4. **`DropEvent` Diagnostics:** Captures full telemetry diagnostics matching dataclass fields in `state.py`:
   - `triggered: bool`
   - `timestamp: float`
   - `sim_time: float`
   - `robot_motion_state: str` ("MOVING")
   - `release_position: List[float]`
   - `release_linear_velocity: List[float]`
   - `release_angular_velocity: List[float]`
   - `attached_piece_id: Optional[str]`
   - `trajectory_progress: float`
   - `release_speed: float` (> 0.02 m/s)

### 6.2. Settling Criteria
A dropped or placed piece transitions from `FALLING` / `MOVING` to `RESTING` when its velocities remain below threshold for 20 consecutive simulation steps ($0.083\text{ s}$):
- $\|\mathbf{v}\| < 0.005\text{ m/s}$
- $\|\boldsymbol{\omega}\| < 0.050\text{ rad/s}$

### 6.3. Out-of-Bounds Detection
If a piece is dropped outside the finite board collider or knocked over the edge, it falls past the spatial boundary thresholds:
- $Z < -0.200\text{ m}$ (below table level), OR
- $|X - X_{\text{center}}| > \frac{L}{2} + 0.15\text{ m}$, OR
- $|Y - Y_{\text{center}}| > \frac{W}{2} + 0.15\text{ m}$

The piece is tagged with physical state `OUT_OF_BOUNDS`, signaling gameplay logic that a piece has left the valid playing area.

---

## 7. Telemetry Streaming Protocol (`world_state`)

The `TelemetryPublisher` broadcasts two interleaved JSON payloads over WebSocket port 8765:
1. `robot_state`: 6 joint angles, Cartesian TCP/flange poses, motion state (`IDLE`, `MOVING`, `ERROR`), and gripper digital output.
2. `world_state`: 3D poses and quaternions for all 32 pieces, gripper jaw width (`jaw_width_m`), grasp status (`closed`, `is_closed`), and attachment metadata.

### Example `world_state` Payload (matching `WorldStateSnapshot.to_dict()`):
```json
{
  "type": "world_state",
  "timestamp": 1726483200.123,
  "simulation_time": 4.521,
  "gripper": {
    "closed": true,
    "is_closed": true,
    "jaw_width_m": 0.020,
    "attached_piece_id": "black_cannon_0",
    "tcp_position_m": [-0.360, 0.080, 0.089],
    "grasp_position_m": [-0.360, 0.080, 0.054]
  },
  "pieces": [
    {
      "id": "black_cannon_0",
      "side": "b",
      "type": "c",
      "position_robot_base_m": [-0.360, 0.080, 0.054],
      "orientation_quaternion_robot_base": [0.0, 0.0, 0.0, 1.0],
      "position_3d_world_m": [0.080, 0.054, 0.360],
      "orientation_quaternion_3d_world": [-0.5, 0.5, 0.5, 0.5],
      "linear_velocity_m_s": [0.0, 0.0, 0.0],
      "angular_velocity_rad_s": [0.0, 0.0, 0.0],
      "physical_state": "attached",
      "attached": true,
      "tilt_deg": 0.0,
      "col_float": 1.0,
      "row_float": 2.0,
      "nearest_col": 1,
      "nearest_row": 2,
      "distance_to_nearest_intersection_m": 0.0,
      "pose_world": [0.080, 0.054, 0.360],
      "orientation_quat_world": [-0.5, 0.5, 0.5, 0.5],
      "pose_robot": [-0.360, 0.080, 0.054],
      "orientation_quat_robot": [0.0, 0.0, 0.0, 1.0],
      "is_grasped": true,
      "status": "attached"
    }
  ]
}
```

---

## 8. Verification & Demonstration Suite

The physical simulation subsystem is backed by comprehensive automated unit tests and an acceptance demonstration suite:
- `tests/unit/test_virtual_physical_world.py`: Verifies rigid body initialization, piece count (16 black, 16 red), and JSON serialization.
- `tests/unit/test_virtual_gripper.py`: Validates capture volume tolerances, ambiguity rejection, and velocity estimation.
- `tests/unit/test_grasp_attachment.py`: Validates relative-transform invariance under 6-DOF translation and rotation.
- `tests/unit/test_piece_drop.py`: Validates normal release settling, dynamic release velocity inheritance, off-board falling, and piece-on-piece collision resolution.
- `tests/unit/test_world_coordinate_parity.py`: Validates parity of all 90 board intersections between Python and Three.js.
- `tools/simulation/demo_virtual_physical_world.py`: Demonstrates all 4 acceptance scenarios:
  1. **Scenario A (Normal)**: Clean pick-and-place with hover approach, grasp, Cartesian transfer, and accurate placement ($< 0.1\text{ mm}$ residual).
  2. **Scenario B (Dynamic Drop)**: Mid-flight emergency force drop with ballistic flight and settling on board.
  3. **Scenario C (Off-Board)**: Transfer beyond board boundary, release into void, and out-of-bounds state detection.
  4. **Scenario D (Collision)**: Stacking two pieces directly and verifying stable contact resolution without numerical explosion.
