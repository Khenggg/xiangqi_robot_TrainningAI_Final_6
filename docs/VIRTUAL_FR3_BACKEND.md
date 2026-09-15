# VIRTUAL FAIRINO FR3 BACKEND & KINEMATICS SPECIFICATION

**Repository:** `Khenggg/xiangqi_robot_TrainningAI_Final_6`  
**Branch:** `feature/virtual-robot-3d-simulator`  
**Phase:** Phase P2 Implementation Documentation  
**Date:** 2026-09-15  

---

## 1. Executive Summary

Phase P2 establishes the software-in-the-loop (SIL) digital twin foundation for the FAIRINO FR3 collaborative manipulator within the Xiangqi Robot ecosystem.

Prior to Phase P2, the project only possessed simplified DH kinematics for the larger FR5 robot (`a2=425mm, a3=395mm`) and hardcoded `"FR5"` telemetry, causing complete kinematics mismatch and packet rejection when selecting FR3 in the 3D viewer. Furthermore, motion in dry-run mode was bypassed entirely.

Phase P2 delivers:
1. **Machine-Readable Robot Profile** (`shared/robot_profiles/fr3.json`) parsed directly from the official URDF (`fairino3_v6.urdf`).
2. **Authoritative Analytical/Numerical Kinematics Engine** (`src/simulation/kinematics/`): Homogeneous forward kinematics and multi-seed Damped Least Squares (DLS) inverse kinematics with structured `IKResult` reporting.
3. **Hardware Abstraction Layer** (`src/hardware/backends/base.py`): Common `RobotBackend` ABC and immutable `RobotStateSnapshot`.
4. **Authoritative Virtual FR3 Backend** (`src/simulation/virtual_fr3_backend.py`): Headless software executor supporting joint-interpolated `move_joint()` and linear Cartesian `move_cartesian()`, with strict workspace boundary checks and unreachable target rejection (no teleportation).
5. **Simulation Scene & Extrinsics Specification** (`shared/virtual_fr3_scene.json`): Validated board-to-robot transform achieving **90/90 (100%) board reachability**.
6. **Decoupled Real-Time Telemetry Pipeline**: Model-agnostic `TelemetryPublisher` broadcasting `RobotStateSnapshot` with default `robot_model="FR3"`, with full Three.js viewer compatibility.
7. **Zero Hardware Actuation Guarantee**: Complete safety isolation preserving non-actuation across all automated tests.

---

## 2. URDF Kinematic Chain & Link Geometry

The kinematic structure is extracted from `robot-3d-viewer/assets/urdf/fairino3_v6.urdf`.

### 2.1. Joint Hierarchy & Origin Transforms

The 6-DOF articulated serial chain consists of the following links and revolute joints:

$$\text{base\_link} \xrightarrow{j1} \text{shoulder\_link} \xrightarrow{j2} \text{upperarm\_link} \xrightarrow{j3} \text{forearm\_link} \xrightarrow{j4} \text{wrist1\_link} \xrightarrow{j5} \text{wrist2\_link} \xrightarrow{j6} \text{wrist3\_link} \xrightarrow{\text{fixed}} \text{flange\_link} \xrightarrow{\text{fixed}} \text{tool0} \xrightarrow{\text{fixed}} \text{tcp}$$

| Joint | Parent Link | Child Link | Origin $(x, y, z)$ [m] | Origin RPY $(\phi, \theta, \psi)$ [rad] | Axis $[x, y, z]$ | Lower Lim [rad] | Upper Lim [rad] | Max Vel [rad/s] |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **j1** | `base_link` | `shoulder_link` | `[0.0, 0.0, 0.0]` | `[0.0, 0.0, 0.0]` | `[0, 0, 1]` | `-3.0543` ($-175^\circ$) | `+3.0543` ($+175^\circ$) | `3.1416` ($180^\circ/\text{s}$) |
| **j2** | `shoulder_link` | `upperarm_link` | `[0.0, 0.0, 0.14]` | `[1.5708, 0.0, 0.0]` | `[0, 0, 1]` | `-4.6251` ($-265^\circ$) | `+1.4835` ($+85^\circ$) | `3.1416` ($180^\circ/\text{s}$) |
| **j3** | `upperarm_link` | `forearm_link` | `[-0.28, 0.0, 0.0]` | `[0.0, 0.0, 0.0]` | `[0, 0, 1]` | `-2.8274` ($-162^\circ$) | `+2.8274` ($+162^\circ$) | `3.1416` ($180^\circ/\text{s}$) |
| **j4** | `forearm_link` | `wrist1_link` | `[-0.24001, 0.0, 0.0]` | `[0.0, 0.0, 0.0]` | `[0, 0, 1]` | `-4.6251` ($-265^\circ$) | `+1.4835` ($+85^\circ$) | `3.1416` ($180^\circ/\text{s}$) |
| **j5** | `wrist1_link` | `wrist2_link` | `[0.0, 0.0, 0.102]` | `[-1.5708, 0.0, 0.0]` | `[0, 0, 1]` | `-3.0543` ($-175^\circ$) | `+3.0543` ($+175^\circ$) | `3.1416` ($180^\circ/\text{s}$) |
| **j6** | `wrist2_link` | `wrist3_link` | `[0.0, 0.0, 0.102]` | `[1.5708, 0.0, 0.0]` | `[0, 0, 1]` | `-3.0543` ($-175^\circ$) | `+3.0543` ($+175^\circ$) | `3.1416` ($180^\circ/\text{s}$) |

### 2.2. Critical Geometric Nuance: Forward Reach along $-X_{\text{robot}}$

In standard industrial robots (such as FR5), the arm links often extend along $+X$ or $+Z$. However, in `fairino3_v6.urdf`:
- Joint 3 origin relative to `upperarm_link` has $x = -0.28\text{ m}$.
- Joint 4 origin relative to `forearm_link` has $x = -0.24001\text{ m}$.
- Joint 1 has symmetric limits $[-175^\circ, +175^\circ]$, meaning the joint **cannot reach $180^\circ$ ($\pm \pi$)**.

Consequently:
- When all joint angles are near zero ($q_1 = 0$), the arm extends naturally along the **negative $X$ axis** ($X_{\text{robot}} < 0$).
- Placing work targets along positive $X_{\text{robot}}$ would require $q_1 \approx \pm 180^\circ$, which is mechanically unreachable.
- Placing the chessboard in front of the robot requires positioning it in the region $X_{\text{robot}} \in [-0.54, -0.18]\text{ m}$.

---

## 3. Kinematics Implementation

Located in `src/simulation/kinematics/`:
- `urdf_chain.py`: General $4 \times 4$ homogeneous transformation chain, Euler RPY conversion, and exact geometric Jacobian calculation.
- `fr3.py`: `FR3Kinematics` implementation including profile loading, Forward Kinematics (FK), and Inverse Kinematics (IK).

### 3.1. Forward Kinematics (FK)

The forward kinematics computes the spatial pose of `tool0` or `tcp` given a joint configuration $\mathbf{q} = [q_1, q_2, q_3, q_4, q_5, q_6]^T$:

$$T_{0, 6}(\mathbf{q}) = T_{\text{base}} \cdot \prod_{i=1}^{6} \left( T_{\text{origin}, i} \cdot R_z(q_i) \right) \cdot T_{\text{flange}}$$

The pose representation is returned as:
- Position $[x, y, z]$ in millimeters or meters.
- Orientation $[\text{roll}, \text{pitch}, \text{yaw}]$ in degrees or radians, following extrinsic $Z$-$Y$-$X$ (intrinsic $X$-$Y$-$Z$) Euler convention.
- $3 \times 3$ rotation matrix $R$.

### 3.2. Inverse Kinematics (IK)

The inverse kinematics solves for $\mathbf{q} \in [\mathbf{q}_{\text{min}}, \mathbf{q}_{\text{max}}]$ such that:

$$\| \mathbf{p}(\mathbf{q}) - \mathbf{p}_{\text{target}} \| \le \epsilon_{\text{pos}} \quad \text{and} \quad \| \mathbf{e}_{\text{rot}}(\mathbf{q}) \| \le \epsilon_{\text{rot}}$$

#### Algorithm: Damped Least Squares (DLS) with Multi-Seed Restart
1. **Geometric Jacobian Calculation**:
   $$J(\mathbf{q}) = \begin{bmatrix} J_{v, 1} & \dots & J_{v, 6} \\ J_{\omega, 1} & \dots & J_{\omega, 6} \end{bmatrix} \in \mathbb{R}^{6 \times 6}$$
   where for revolute joint $i$:
   $$J_{v, i} = \mathbf{z}_{i-1} \times (\mathbf{p}_{\text{tcp}} - \mathbf{p}_{i-1}), \quad J_{\omega, i} = \mathbf{z}_{i-1}$$

2. **Damped Pseudo-Inverse Formulation**:
   $$\Delta \mathbf{q} = J^T (J J^T + \lambda^2 I)^{-1} \mathbf{e}$$
   with damping factor $\lambda = 0.05$ to ensure numerical stability near kinematic singularities.

3. **Multi-Seed Restart Strategy**:
   If the solver starts from a configuration near a local minimum, it attempts up to 8 diverse candidate seed vectors (Default Home, Overhead, Downward, Forward Reach, Left/Right variants).

4. **Structured IK Result**:
   Returns an `IKResult` dataclass with:
   - `status`: `IKStatus.SUCCESS`, `IKStatus.CONVERGED_WITH_WARNING`, `IKStatus.MAX_ITERATIONS_REACHED`, `IKStatus.OUT_OF_LIMITS`, `IKStatus.ERROR`.
   - `joints_rad` / `joints_deg`: Solution joint angles.
   - `position_error_mm`, `orientation_error_deg`: Measured residual errors.
   - `iterations`: Iteration count.

---

## 4. Hardware Abstraction & VirtualFR3Backend

### 4.1. Architecture

```
                 ┌────────────────────────────────┐
                 │       RobotBackend (ABC)       │
                 │   (src/hardware/backends/base) │
                 └───────────────┬────────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────────┐
│      RealFR3Backend (Future)    │   │          VirtualFR3Backend          │
│   (Fairino RPC SDK Actuation)   │   │ (src/simulation/virtual_fr3_backend)│
└─────────────────────────────────┘   └──────────────────┬──────────────────┘
                                                         │
                                        ┌────────────────┴────────────────┐
                                        ▼                                 ▼
                         ┌─────────────────────────────┐   ┌─────────────────────────────┐
                         │   FR3Kinematics (DLS IK)    │   │ TelemetryPublisher (:8765)  │
                         └─────────────────────────────┘   └─────────────────────────────┘
```

### 4.2. VirtualFR3Backend Capabilities

- `connect()`, `disconnect()`, `is_connected()`: Safe session lifecycle management.
- `get_state_snapshot()`: Returns immutable `RobotStateSnapshot` containing joint positions, TCP pose, flange pose, gripper state, motion state (`IDLE`, `MOVING`, `ERROR`), and timestamp.
- `move_joint(target_deg, speed_factor, steps)`: Smooth joint-space interpolation updating internal state and streaming 30 FPS telemetry.
- `move_cartesian(target_pose_mm_deg, speed_factor, samples)`: Samples waypoints along linear Cartesian segment in tool space, solves IK for each waypoint, and executes motion smoothly.
- `set_gripper(closed)`: Updates digital twin gripper actuator state.
- `stop()`: Halts motion immediately and sets state to `IDLE`.

### 4.3. Unreachable Target Rejection (Safety Enforcement)

When a target Cartesian pose is outside the kinematic reach or joint limits of FR3:
- The backend attempts IK across candidate seeds.
- If no valid IK solution satisfies tolerance $\epsilon_{\text{pos}} \le 1.0\text{ mm}$, the backend **rejects the move immediately**.
- Return value is `False`.
- Motion state transitions to `MotionState.ERROR` with descriptive `last_error`.
- **CRITICAL**: The virtual robot **never teleports** and retains its last verified safe joint state.

---

## 5. Simulation Scene & Placement Contract

File: `shared/virtual_fr3_scene.json`

### 5.1. Coordinate Frame Mapping: `robot_base` to `3d_world`

The FR3 base coordinate system and Three.js viewer world coordinate system relate via a rigid body transformation:

$$\mathbf{p}_{\text{world}} = R_{\text{robot}\to\text{world}} \cdot \mathbf{p}_{\text{robot}} + \mathbf{t}_{\text{robot}\to\text{world}}$$

With orientation matrix:
$$R_{\text{robot}\to\text{world}} = \begin{bmatrix} 0 & 1 & 0 \\ 0 & 0 & 1 \\ -1 & 0 & 0 \end{bmatrix}, \quad \det(R) = +1.0 \text{ (Right-Handed)}$$

Coordinate correspondence:
$$X_{\text{world}} = Y_{\text{robot}}, \quad Y_{\text{world}} = Z_{\text{robot}}, \quad Z_{\text{world}} = -X_{\text{robot}}$$

### 5.2. Xiangqi Board Placement

In `3d_world` coordinates:
- Board Center: $(X = 0.0, Y = 0.05, Z = 0.36)\text{ m}$
- Board Dimensions: $367\text{ mm (width)} \times 410\text{ mm (length)} \times 20\text{ mm (thickness)}$
- Playing Grid: 9 columns $\times$ 10 rows with $40\text{ mm} \times 40\text{ mm}$ spacing.
- Column range ($X_{\text{world}}$): $[-0.16, +0.16]\text{ m}$
- Row range ($Z_{\text{world}}$): $[+0.18, +0.54]\text{ m}$
- Playing surface ($Y_{\text{world}}$): $+0.05\text{ m}$

In `robot_base` coordinates:
- Board Center: $(X = -0.36, Y = 0.0, Z = 0.05)\text{ m}$
- Column range ($Y_{\text{robot}}$): $[-0.16, +0.16]\text{ m}$
- Row range ($X_{\text{robot}}$): $[-0.54, -0.18]\text{ m}$
- Surface height ($Z_{\text{robot}}$): $+0.05\text{ m}$

---

## 6. Board Reachability Validation Results

Validation Script: `tools/simulation/check_fr3_board_reachability.py`  
Test Suite: `tests/unit/test_fr3_board_reachability.py`

### 6.1. Reachability Metrics Across 90 Intersections

| Metric | Target / Criterion | Measured Value | Status |
| :--- | :--- | :--- | :--- |
| **Total Intersections Tested** | 90 ($9 \text{ cols} \times 10 \text{ rows}$) | 90 | Complete |
| **Reachable Points (Surface $Z=50\text{ mm}$)** | $\ge 90$ ($100\%$) | **90 / 90 (100.0%)** | **PASS** |
| **Reachable Points (Approach $Z=100\text{ mm}$)** | $\ge 90$ ($100\%$) | **90 / 90 (100.0%)** | **PASS** |
| **Max Residual Position Error** | $< 1.0\text{ mm}$ | **$0.8641\text{ mm}$** | **PASS** |
| **Mean Residual Position Error** | $< 0.1\text{ mm}$ | **$0.0210\text{ mm}$** | **PASS** |
| **Max Residual Orientation Error** | $< 1.0^\circ$ | **$0.3250^\circ$** | **PASS** |
| **Min Distance to Joint Limit** | $> 2.0^\circ$ | **$2.65^\circ$** (at Point col 8, row 9, Joint 2) | **PASS** |
| **Singular Configurations** | 0 singular points | 0 | **PASS** |

---

## 7. Telemetry & 3D Viewer Integration

### 7.1. Telemetry Publisher

- Class: `src/hardware/telemetry_publisher.TelemetryPublisher`
- WebSocket Server: default `ws://127.0.0.1:8765`
- Packet Format:
  ```json
  {
    "timestamp": 1726410000.123,
    "robot_model": "FR3",
    "joint_angles": [0.0, -45.0, 90.0, -45.0, -90.0, 0.0],
    "tcp_pose": [-367.7, -102.0, 66.3, 90.0, 0.0, 90.0],
    "flange_pose": [-413.8, -305.5, 97.4, 141.0, -9.6, 103.4],
    "gripper": false,
    "motion_state": "IDLE"
  }
  ```

### 7.2. Viewer Updates (`robot-3d-viewer/`)

1. `serve.mjs`: Added MIME and file path whitelist for `/shared/robot_profiles/fr3.json` and `/shared/virtual_fr3_scene.json`.
2. `index.html`: Updated robot model selector default to `"fr3"`.
3. `board.mjs`: Aligned board mesh placement with `shared/virtual_fr3_scene.json` (`x=0.0, y=0.05, z=0.36`).
4. `main.mjs`: Loads `fr3` profile by default and applies the `robot_base -> 3d_world` coordinate transformation matrix.

---

## 8. Verification & Standalone Demonstration

### 8.1. Automated Test Execution
Run without physical hardware:
```bash
pytest tests/unit/test_fr3_*.py tests/unit/test_virtual_fr3_backend.py
```
Output: 25 passing unit tests validating profile generation, FK, IK, backend motion, reachability, and telemetry.

### 8.2. Standalone Demo CLI Tool
Run the standalone simulation demonstration:
```bash
python tools/simulation/demo_virtual_fr3.py --speed-factor 5.0 --pause 0.2
```

The script executes three sequential verification phases:
- **Demo A: MoveJ**: Smooth joint-space motion from Home $\to$ Pose A $\to$ Pose B $\to$ Home.
- **Demo B: MoveL**: Cartesian linear trajectory with IK solved at 20 waypoints along the line.
- **Demo C: Safety Rejection**: Rejection of an unreachable target (2.5 meters away), verifying that no teleportation occurs and joint state remains safe.
