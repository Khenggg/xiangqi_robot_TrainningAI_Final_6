# Phase 4 — Quick Laboratory Commissioning Checklist

**Document ID:** `DOC-P4-CHECKLIST-001`  
**Location:** Keep Open On Tablet / Workstation Beside FAIRINO FR3 Robot  
**Primary Standard:** `docs/PHASE4_PHYSICAL_VALIDATION_RUNBOOK.md`  

---

## 1. Before Power-On

- [ ] **Workspace Perimeter:** Clear general laboratory safety perimeter around the robot reach envelope of loose tools, beverages, packaging, and unneeded cabling.
- [ ] **E-Stop Access:** Physical emergency stop button uncoiled, inspected, and held by secondary observer / within immediate arm's reach of operator.
- [ ] **Base Mounting Rigidity:** Check robot base mounting bolts. Shake robot base firmly—zero mechanical flex or tilt.
- [ ] **Board Fixture:** Xiangqi board clamped to table against mechanical reference stops. Zero sliding or rocking under finger push.
- [ ] **Camera Gantry:** Overhead camera mount rigid and isolated from robot base plate vibration.
- [ ] **Tool Mechanical Integrity:** Gripper flange adapter torqued; mechanism free of debris; rubber jaw pads clean and degreased.
- [ ] **Cable Slack:** Tool umbilical cable routed with adequate slack across Joints 4, 5, and 6. Manually verify rotation freedom.
- [ ] **Leveling Spirit Check:** Board spirit level $< 1.0^\circ$ pitch and roll (`PROPOSED_INITIAL_TEST_VALUE`).

---

## 2. After Controller Connection (Telemetry-Only State)

> **Lifecycle Gate:** `DISCONNECTED` $\to$ `CONNECTED / TELEMETRY-ONLY`.<br>
> Connection via `connect()` is strictly telemetry-only: does **NOT** call `RobotEnable(1)` or switch controller mode.<br>
> Principle: `Connected != Enabled != Mode Configured != Calibrated != Motion Authorized`.

- [ ] **Network Link:** Workstation IP (configured on `192.168.58.0/24`, e.g. `.10`) ping to FR3 controller (`config.ROBOT_IP = 192.168.58.2`) $< 2\text{ ms}$, 0% drop (`PROPOSED_INITIAL_TEST_VALUE`).
- [ ] **SDK RPC Initialized:** Telemetry-only connection established via SDK (`GetSDKVersion()`).
- [ ] **Safety Status Query:** `GetRobotState()` reports normal status (no emergency stop latch, no joint drive faults).
- [ ] **Joint Telemetry Query:** `GetActualJointPosDegree()` values read successfully and match visual robot posture.
- [ ] **Flange Pose Query:** `GetActualToolFlangePose(0)` reads valid Cartesian coordinate in Base Frame (`user=0`).
- [ ] **Motor Drives Off:** Robot servo drives remain completely de-energized (`RobotEnable` status = 0).

---

## 3. Before Robot Enable & Mode Configuration

- [ ] **Operator Confirmation:** Visual scan of arm envelope. Announce clearly: *"Arm energizing"*.
- [ ] **Speed Override Locked:** Controller speed override locked to $\le 10\%$ (`PROPOSED_INITIAL_COMMISSIONING_LIMIT`).
- [ ] **Safe Default Frame:** Controller confirmed in Base Frame (`user=0`).
- [ ] **Controlled Enable:** Invoke `RobotEnable(1)` via authorized commissioning gate (`EXPLICIT ENABLE` state). Listen for normal mechanical brake clicks.
- [ ] **Mode Configuration:** Invoke `Mode(0)` explicitly (`EXPLICIT MODE CONFIGURATION` state).
- [ ] **Hold Position Inspection:** Arm holds position solidly with zero hunting, hum, or joint drift.

---

## 4. Before First Arm Movement

- [ ] **Trajectory Cleared:** High clearance path between current pose and Home/Idle pose verified.
- [ ] **Jog Direction Verification:** In manual mode, jog Joint 1 by $+1^\circ$. Confirm movement direction matches convention.
- [ ] **Initial Transit to Home:** Move slowly ($\le 10\%$ speed) to canonical Home position. Finger resting on E-Stop.
- [ ] **Gripper Safe Idle:** Verify Tool DO0 (Close) and DO1 (Open) are both LOW (`0V`). Zero drive voltage on gripper actuator.
- [ ] **Gripper Pulse Test:** Execute single 0.15s Open pulse, then 0.15s Close pulse. Verify actuator movement direction and deadtime (`CURRENT_SOFTWARE_DEFAULT = 0.10s`).

---

## 5. Before Board Contact / Teaching (R1–R4 — Calibrated State)

- [ ] **Calibration Tool Mounted:** Calibrated pointer stylus mounted in tool holder (`TCP_CALIBRATION`, Tool Frame ID `TBD`).
- [ ] **Semantics Confirmed:** Operator confirms R1–R4 are **grid crosshairs** in strictly `(row, col)` convention:
  - `R1`: `(row=0, col=0)` — Row 0, Col 0 (Black Left Chariot)
  - `R2`: `(row=0, col=8)` — Row 0, Col 8 (Black Right Chariot)
  - `R3`: `(row=9, col=8)` — Row 9, Col 8 (Red Right Chariot)
  - `R4`: `(row=9, col=0)` — Row 9, Col 0 (Red Left Chariot)
- [ ] **Slip-of-Paper Method Ready:** 0.1 mm paper strip in hand to detect surface contact without deflecting board.
- [ ] **Single Orientation Maintained:** Tool orientation held strictly vertical across all 4 points.
- [ ] **Points Captured in User=0:** All 4 points recorded in Base Frame with identical tool/user IDs.
- [ ] **BoardPose Provider Run:** Compute fit metrics via `PhysicalTeachingPointBoardPoseProvider.from_controller(backend)` (or offline via `PhysicalTeachingPointBoardPoseProvider.from_teaching_points(...)` / `calibrate_board_from_teaching_points(...)`):
  - Width: $320.0 \pm 3.0\text{ mm}$ (warning $>3\text{ mm}$, hard fail $>5\text{ mm}$)
  - Height: $360.0 \pm 3.0\text{ mm}$ (warning $>3\text{ mm}$, hard fail $>5\text{ mm}$)
  - RMS residual: $\le 2.0\text{ mm}$ (warning $>2\text{ mm}$, hard fail $>3\text{ mm}$)
  - Board tilt: $\le 2.5^\circ$ (warning $>2.5^\circ$, hard fail $>5.0^\circ$)
  - Status: Must achieve `PASS` or `PASS_WITH_WARNING` before proceeding.

---

## 6. Before Board Transit & Gameplay Tests (Motion Authorized State)

- [ ] **Grasp TCP Active:** Switch tool frame to `TCP_GRASP` (Tool Frame ID `TBD`, ~150 mm flange-to-grasp center `CURRENT_CANONICAL_TOOL_GEOMETRY_ESTIMATE`).
- [ ] **Safe Transit Height Confirmed:** $Z_{\text{safe}} = +40.0\text{ mm}$ above board surface (`CURRENT_SOFTWARE_DEFAULT`) verified to clear pieces.
- [ ] **Pick Height Calibrated:** $Z_{\text{pick}}$ tuned via approach ladder starting from $4.715\text{ mm}$ (`PROVISIONAL_SIMULATION / GEOMETRIC STARTING VALUE`). Jaw clearance target $\ge 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`).
- [ ] **Place Height Calibrated:** $Z_{\text{place}}$ tuned. Piece released flush without drop bounce or board crushing.
- [ ] **Four Corners Reached:** Playable cells `(row=0, col=0)`, `(row=0, col=8)`, `(row=9, col=8)`, `(row=9, col=0)` visited at $Z_{\text{safe}}$ with zero cable tension or singularity.
- [ ] **Capture Bin Taught & Interlock Verified:** Waypoints `BIN_APPROACH`, `BIN_DROP`, `BIN_RETREAT` taught and corridor validated outside human zone. Note: Physical capture requires clearing `CAPTURE_BIN_VALIDATED = False`.
- [ ] **Single-Cell Move Tested:** Piece picked from `(row=4, col=4)` and placed at `(row=4, col=5)`. Placement error target $\le 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`).
- [ ] **Vision Board State Synced:** Overhead camera detection confirms piece placement matches physical board state.

---

## 7. Shutdown & Secure Lab

- [ ] **Park Arm:** Command robot to canonical parked Home position.
- [ ] **Outputs De-energized:** Verify all Tool DOs and Controller DOs are forced LOW.
- [ ] **Disable Drives:** Command `RobotEnable(0)`. Confirm mechanical brakes engage.
- [ ] **Controller Disconnect:** Close SDK connection cleanly.
- [ ] **Data Logged:** Record all calibrated constants and sign-offs in `phase4_physical_validation_log.md`.
- [ ] **Power Down:** Switch off robot main controller cabinet and tool power supply. Lock out if leaving unattended.
- [ ] **Sign-Off:** Lead Commissioning Engineer signature recorded.
