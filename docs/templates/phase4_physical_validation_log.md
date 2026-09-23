# Phase 4 — Physical Commissioning & Validation Log

**Log Document ID:** `LOG-P4-YYYYMMDD-RUN01`<br>
**Test Date:** `YYYY-MM-DD`<br>
**Location / Facility:** `Robotics Lab / Station 1`<br>
**Lead Commissioning Engineer:** `[Name / Title]`<br>
**Secondary Observer / Safety Officer:** `[Name / Title]`<br>
**Overall Validation Status:** `[PENDING / PASS / PASS_WITH_WARNING / FAIL]`  

---

## 1. Hardware & System Configuration

### 1.1 Robot Manipulator Information
* **Manufacturer & Model:** FAIRINO FR3
* **Controller Serial Number:** `[Enter S/N]`
* **Controller Firmware Version:** `[e.g. v3.7.2]`
* **Manipulator Arm Serial Number:** `[Enter S/N]`
* **Controller IP Address:** `192.168.58.2` (`config.ROBOT_IP`)
* **Host Workstation IP Address:** `192.168.58.10` (or valid IP on `192.168.58.0/24`)
* **Active Speed Override During Test:** `[e.g. 10% / 25%]`

### 1.2 Gripper Mechanism Information
* **Gripper Mechanism:** Custom Bidirectional DC Motor / Rack-and-Pinion
* **Driver Interface:** Two-Output Flange DO Interface (`TwoOutputGripperDriver`)
* **Open Control Channel:** Tool DO1 (Active HIGH pulse, `CONFIGURED_SOFTWARE_MODEL`)
* **Close Control Channel:** Tool DO0 (Active HIGH pulse, `CONFIGURED_SOFTWARE_MODEL`)
* **Jaw Opening Stroke:** `[Measured stroke, mm]` (Target: $\ge 32\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* **Jaw Pad Material:** `[Silicone / Neoprene Rubber]`

### 1.3 Tool Center Point (TCP) Configuration
* **`TCP_CALIBRATION` (Tool Frame ID `TBD`):**
  * Calibration Mode: `[Mode A: Calibrated Pointer Tip / Mode B: Jaw Corner Contact]`
  * Assigned Tool Frame ID on Controller: `[______]`
  * Offset from Flange: $X = \text{______}\text{ mm}$, $Y = \text{______}\text{ mm}$, $Z = \text{______}\text{ mm}$
  * Calibration Residual: `[______ mm]` (Target: $< 0.30\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* **`TCP_GRASP` (Tool Frame ID `TBD`):**
  * Description: Geometric center between closed rubber jaw pads
  * Assigned Tool Frame ID on Controller: `[______]`
  * Offset from Flange: $X = 0.00\text{ mm}$, $Y = 0.00\text{ mm}$, $Z = \text{______}\text{ mm}$ (Nominal CAD: $\approx 150.0\text{ mm}$, `CURRENT_SOFTWARE_DEFAULT`)
  * Legacy 218mm Check: Confirmed NOT active `[YES / NO]`

### 1.4 Board & Fixture Information
* **Board Identifier / Type:** `[e.g. Standard Wood Xiangqi Board #1]`
* **Physical Outer Dimensions:** Measured: `______ mm` × `______ mm`
* **Grid Crosshair Spacing:** Measured: `______ mm` pitch (Canonical: $40.0\text{ mm}$, `PROJECT_GEOMETRY`)
* **Board Spirit Level Deviation:** $X\text{-axis} = \text{______}^\circ$, $Y\text{-axis} = \text{______}^\circ$ (Requirement: $< 1.0^\circ$, `PROPOSED_INITIAL_TEST_VALUE`)
* **Clamping / Fixture Method:** `[Corner Toggle Clamps / Vacuum / Magnetic / Stop Blocks]`

---

## 2. R1–R4 Teaching Readings

> All points taught in Base Frame (`user=0`) using `TCP_CALIBRATION` (Configured Tool Frame ID).<br>
> Semantics strictly follow `(row, col)` convention at grid line intersections.<br>
> Contact verified using $0.1\text{ mm}$ paper slip method.

| Point | Feature / Cell (row, col) | X (mm) | Y (mm) | Z (mm) | Rx (deg) | Ry (deg) | Rz (deg) | Joint Angles [J1..J6] (deg) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R1** | (0, 0) Black Left Chariot | | | | | | | `[ , , , , , ]` |
| **R2** | (0, 8) Black Right Chariot| | | | | | | `[ , , , , , ]` |
| **R3** | (9, 8) Red Right Chariot  | | | | | | | `[ , , , , , ]` |
| **R4** | (9, 0) Red Left Chariot   | | | | | | | `[ , , , , , ]` |

* **Operator Initials:** `______`
* **Capture Timestamp:** `YYYY-MM-DD HH:MM:SS`
* **Active User Frame:** `user = 0` (Confirmed: `[YES / NO]`)
* **Active Tool Frame ID:** `______`

---

## 3. BoardPose Reconstruction & Geometric Fit Metrics

> Computed via `BoardPoseProvider.from_teaching_points()` using recorded R1–R4 coordinates.<br>
> Thresholds are authoritative code contracts (`AUTHORITATIVE_CODE_CONTRACT`).

| Geometric Metric | Canonical Contract | Warning Threshold | Hard Fail Threshold | Measured Value | Metric Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Width (R1–R2)** | $320.00\text{ mm}$ | $|\Delta| > 3.0\text{ mm}$ | $|\Delta| > 5.0\text{ mm}$ | `______ mm` | `[PASS/WARN/FAIL]` |
| **Width (R4–R3)** | $320.00\text{ mm}$ | $|\Delta| > 3.0\text{ mm}$ | $|\Delta| > 5.0\text{ mm}$ | `______ mm` | `[PASS/WARN/FAIL]` |
| **Height (R2–R3)**| $360.00\text{ mm}$ | $|\Delta| > 3.0\text{ mm}$ | $|\Delta| > 5.0\text{ mm}$ | `______ mm` | `[PASS/WARN/FAIL]` |
| **Height (R1–R4)**| $360.00\text{ mm}$ | $|\Delta| > 3.0\text{ mm}$ | $|\Delta| > 5.0\text{ mm}$ | `______ mm` | `[PASS/WARN/FAIL]` |
| **Edge Symmetry Diff** | $0.00\text{ mm}$ | — | $> 5.0\text{ mm}$ | `______ mm` | `[PASS/FAIL]` |
| **Diagonal 1 (R1–R3)** | $481.66\text{ mm}$ | — | — | `______ mm` | — |
| **Diagonal 2 (R2–R4)** | $481.66\text{ mm}$ | — | — | `______ mm` | — |
| **Diagonal Difference** | $0.00\text{ mm}$ | — | $> 8.0\text{ mm}$ | `______ mm` | `[PASS/FAIL]` |
| **RMS Fit Residual** | $0.00\text{ mm}$ | $> 2.0\text{ mm}$ | $> 3.0\text{ mm}$ | `______ mm` | `[PASS/WARN/FAIL]` |
| **Max Corner Residual** | $0.00\text{ mm}$ | — | $> 5.0\text{ mm}$ | `______ mm` | `[PASS/FAIL]` |
| **Max Plane Residual** | $0.00\text{ mm}$ | — | $> 3.0\text{ mm}$ | `______ mm` | `[PASS/FAIL]` |
| **Board Tilt Angle** | $0.00^\circ$ | $> 2.5^\circ$ | $> 5.0^\circ$ | `______ deg`| `[PASS/WARN/FAIL]` |

* **Overall BoardPose Validation Verdict:** `[PASS / PASS_WITH_WARNING / FAIL_RECALIBRATE]`
* **Computed Origin ($\mathbf{p}_0$ in Base Frame):** $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$
* **Computed Rotation Matrix ($\mathbf{R}_{\text{base}}^{\text{board}}$):**
  $$\begin{bmatrix} \text{__} & \text{__} & \text{__} \\ \text{__} & \text{__} & \text{__} \\ \text{__} & \text{__} & \text{__} \end{bmatrix}$$

---

## 4. Gripper Pulse Calibration Ladder

### 4.1 Opening Pulse Trials (DO1 = HIGH)
| Pulse Duration (s) | Measured Jaw Opening (mm) | Motor Sound / Vibration | Stall / Heating Observed? | Observations / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **0.10 s** | `______ mm` | `[______]` | `[NO / YES]` | |
| **0.15 s** | `______ mm` | `[______]` | `[NO / YES]` | |
| **0.20 s** | `______ mm` | `[______]` | `[NO / YES]` | |
| **0.25 s** | `______ mm` | `[______]` | `[NO / YES]` | |
| **0.30 s** | `______ mm` | `[______]` | `[NO / YES]` | *Current software default bound* |

* **Selected Nominal Open Pulse:** `______ s` (Target: Minimum duration achieving $>32\text{ mm}$ opening)

### 4.2 Closing Pulse Trials (DO0 = HIGH) with $22.5\text{ mm}$ Piece
| Pulse Duration (s) | Grip Security (1N pull test) | Piece Tilt / Deformation | Motor Stall Buzz? | Observations / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **0.10 s** | `[______]` | `[______]` | `[NO / YES]` | |
| **0.15 s** | `[______]` | `[______]` | `[NO / YES]` | |
| **0.20 s** | `[______]` | `[______]` | `[NO / YES]` | |
| **0.25 s** | `[______]` | `[______]` | `[NO / YES]` | |
| **0.30 s** | `[______]` | `[______]` | `[NO / YES]` | *Current software default bound* |

* **Selected Nominal Close Pulse:** `______ s`
* **Configured Deadtime:** `0.10 s` (`CURRENT_SOFTWARE_DEFAULT`, hardware interlock confirmed: `[YES / NO]`)
* **Configured Settle Time:** `0.25 s`

---

## 5. Tool Orientation & Clearance Trials

### 5.1 Tool Verticality & Yaw Alignment
* **Machinist Square Perpendicularity:** $X\text{-axis error} = \text{______}^\circ$, $Y\text{-axis error} = \text{______}^\circ$ (Target: $< 0.5^\circ$, `PROPOSED_INITIAL_TEST_VALUE`)
* **Chosen Tool Orientation Vector:** $Rx = \text{______}^\circ$, $Ry = \text{______}^\circ$, $Rz = \text{______}^\circ$
* **Historical Orientation Comparison:** Deviation from historical $[-179.164, -3.047, -26.304] = \text{______}^\circ$ (`HISTORICAL_MEASUREMENT`)
* **Joint 5 Singularity Margin:** $J_5$ angle at board center = $\text{______}^\circ$ (Target: $|J_5| \ge 15.0^\circ$, `PROPOSED_INITIAL_TEST_VALUE`)

### 5.2 Transit Clearance ($Z_{\text{safe}}$)
* **Nominal Clearance Above Board:** `40.0 mm` (`CURRENT_SOFTWARE_DEFAULT`)
* **Smallest Clearance Over Pieces ($9.43\text{ mm}$):** Measured: `______ mm` (Target: $\ge 25.0\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* **Clearance Over Captured Piece Stack ($20.0\text{ mm}$):** Measured: `______ mm`
* **Clearance from Overhead Camera Mount:** Measured: `______ mm` (Target: $\ge 50.0\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* **Verdict:** `[PASS / FAIL]`

---

## 6. Pick & Place Height Empirical Trials

### 6.1 Pick Height ($Z_{\text{pick}}$) Trials at Cell (row=4, col=4)
> Baseline starting point: $H_{\text{piece}} / 2 = 4.715\text{ mm}$ (`PROVISIONAL_SIMULATION / GEOMETRIC STARTING VALUE`).<br>
> All empirical observations below must be measured during live testing.

| Candidate $Z_{\text{pick}}$ (mm) | Jaw-to-Board Clearance (mm) | Piece Contact Band | Grip Security (1N pull) | Observations / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **6.50 mm** | `______ mm` | `[______]` | `[______]` | |
| **5.50 mm** | `______ mm` | `[______]` | `[______]` | |
| **5.00 mm** | `______ mm` | `[______]` | `[______]` | |
| **4.72 mm** | `______ mm` | `[______]` | `[______]` | Software baseline candidate |
| **4.50 mm** | `______ mm` | `[______]` | `[______]` | |
| **4.20 mm** | `______ mm` | `[______]` | `[______]` | Check board clearance |

* **Highest Reliable Pick Height ($Z_{\text{pick, max}}$):** `______ mm`
* **Lowest Safe Pick Height ($Z_{\text{pick, min}}$):** `______ mm`
* **Accepted Nominal Pick Height ($Z_{\text{pick, nominal}}$):** `______ mm`
* **Tolerance Band:** $\pm \text{______ mm}$

### 6.2 Place Height ($Z_{\text{place}}$) Trials at Cell (row=4, col=5)
> All empirical observations below must be measured during live testing.

| Candidate $Z_{\text{place}}$ (mm) | Piece Drop Distance (mm) | Piece Bounce / Skid? | Board Deflection? | Final Radial Error (mm) | Observations / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **6.00 mm** | `______ mm` | `[NO / YES]` | `[NO / YES]` | `______ mm` | |
| **5.00 mm** | `______ mm` | `[NO / YES]` | `[NO / YES]` | `______ mm` | |
| **4.72 mm** | `______ mm` | `[NO / YES]` | `[NO / YES]` | `______ mm` | |
| **4.50 mm** | `______ mm` | `[NO / YES]` | `[NO / YES]` | `______ mm` | |
| **4.00 mm** | `______ mm` | `[NO / YES]` | `[NO / YES]` | `______ mm` | |

* **Accepted Nominal Place Height ($Z_{\text{place, nominal}}$):** `______ mm`
* **Pick == Place Evaluated?** `[EQUAL / DIFFERENT]`
  * If different, justify: `________________________________________________`

---

## 7. Capture-Bin Calibration & Safety Waypoints

* **Interlock Status:** `CAPTURE_BIN_VALIDATED = False` (Confirmed active before validation: `[YES / NO]`)
* **Bin Physical Coordinates in Base Frame (`user=0`):**
  * `BIN_APPROACH`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
  * `BIN_DROP`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
  * `BIN_RETREAT`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
* **Trajectory Safety Verifications:**
  * Trajectory clears board border by $> 40\text{ mm}$: `[PASS / FAIL]`
  * Trajectory completely avoids human player seating zone: `[PASS / FAIL]` (`AUTHORITATIVE_CODE_CONTRACT`)
  * Captured piece does not strike bin rim on descent: `[PASS / FAIL]`
* **Interlock Clearance:** Post-validation `CAPTURE_BIN_VALIDATED = True` approved: `[YES / NO]`

---

## 8. Kinematic Reachability & Boundary Verification

### 8.1 Four Corners & Edge Cells (Strictly `(row, col)` convention)
| Cell Name | Coordinate (row, col) | IK Status | Singularity Margin ($J_5$) | Cable Tension | Clearance OK? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Corner 1 (R1)** | (0, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 2 (R2)** | (0, 8) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 3 (R3)** | (9, 8) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 4 (R4)** | (9, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Center** | (4, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Top Edge** | (0, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Bottom Edge** | (9, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Left Edge** | (4, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Right Edge** | (4, 8) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |

### 8.2 90-Cell Reachability Summary (See Attached CSV for Detail)
* Total Cells Evaluated: `90 / 90`
* Approach Waypoint Reachable ($Z_{\text{safe}}$): `[____ / 90]`
* Pick Waypoint Reachable ($Z_{\text{pick}}$): `[____ / 90]`
* Kinematic Singularities Encountered: `[0 / Details]`
* Attached CSV Log: `docs/templates/phase4_cell_validation.csv` (Verified & Attached: `[YES]`)

---

## 9. End-to-End Gameplay Execution Tests

### 9.1 Single-Piece Move Test (Red Cannon (row=2, col=1) $\to$ (row=2, col=4))
* Pipeline Verified: `PieceMoveIntent` $\to$ `MotionResolver` $\to$ `MotionPlan` $\to$ `MotionExecutor` $\to$ `PhysicalFR3Backend`
* Controller Move Return Code: `0` (Confirmed: `[YES / NO]`)
* Piece Pick Execution: `[CLEAN / SLIPPED / RETRIED]`
* Transit Smoothness: `[SMOOTH / VIBRATION OBSERVED]`
* Placement Accuracy Measured: $\Delta X = \text{______}\text{ mm}$, $\Delta Y = \text{______}\text{ mm}$, Radial Error = $\text{______}\text{ mm}$ (Target: $\le 1.5\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* Vision System Board State Agreement: `[CONFIRMED / DISCREPANCY]`
* Step Status: `[PASS / FAIL]`

### 9.2 Capture Move Test (Black Chariot (row=0, col=0) captures (row=9, col=0))
* Opponent Red Piece Extracted First: `[YES / NO - CRITICAL INVARIANT]` (`AUTHORITATIVE_CODE_CONTRACT`)
* Attacking Black Piece Undisturbed During Extraction: `[YES / NO]` (`AUTHORITATIVE_CODE_CONTRACT`)
* Red Piece Successfully Dropped in Bin: `[YES / NO]`
* Black Piece Picked and Moved to (row=9, col=0): `[YES / NO]`
* Final Black Piece Placement Radial Error: `______ mm` (Target: $\le 1.5\text{ mm}$, `PROPOSED_INITIAL_TEST_VALUE`)
* Adjacent Squares Undisturbed: `[CONFIRMED / DISPLACED]` (`AUTHORITATIVE_CODE_CONTRACT`)
* Step Status: `[PASS / FAIL]`

---

## 10. Failure & Anomaly Incident Log

| Incident # | Phase / Step | Observed Physical Anomaly | Root Cause Diagnosis | Action Taken / Recovery | Recalibration Required? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | | | | | `[YES / NO]` |
| **02** | | | | | `[YES / NO]` |
| **03** | | | | | `[YES / NO]` |

---

## 11. Final Accepted Physical Constants (To be Committed Post-Phase 4)

> **DO NOT MERGE INTO PRODUCTION CONFIG UNTIL SIGNED OFF BELOW.**

| Configuration Key | Provisional Baseline | Calibrated Value | Unit | Provenance Class | Engineering Provenance Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PICK_TCP_HEIGHT_MM` | `4.715` | `______` | mm | `PHYSICALLY_VALIDATED` | Calibrated contact ladder, Station 1 |
| `PLACE_TCP_HEIGHT_MM`| `4.715` | `______` | mm | `PHYSICALLY_VALIDATED` | Calibrated flush release, Station 1 |
| `SAFE_CLEARANCE_Z_MM`| `40.0` | `______` | mm | `PHYSICALLY_VALIDATED` | Safe transit plane above board surface |
| `TOOL_ROTATION_RX` | `-179.164` | `______` | deg | `PHYSICALLY_VALIDATED` | Square-aligned perpendicularity |
| `TOOL_ROTATION_RY` | `-3.047` | `______` | deg | `PHYSICALLY_VALIDATED` | Square-aligned perpendicularity |
| `TOOL_ROTATION_RZ` | `-26.304` | `______` | deg | `PHYSICALLY_VALIDATED` | Grid-parallel jaw alignment |
| `GRIPPER_OPEN_PULSE` | `0.30` | `______` | s | `PHYSICALLY_VALIDATED` | Minimum reliable stroke duration |
| `GRIPPER_CLOSE_PULSE`| `0.30` | `______` | s | `PHYSICALLY_VALIDATED` | Minimum reliable grip duration |
| `CAPTURE_BIN_DROP_X` | `[Legacy]` | `______` | mm | `PHYSICALLY_VALIDATED` | Registered bin position (user=0) |
| `CAPTURE_BIN_DROP_Y` | `[Legacy]` | `______` | mm | `PHYSICALLY_VALIDATED` | Registered bin position (user=0) |
| `CAPTURE_BIN_DROP_Z` | `[Legacy]` | `______` | mm | `PHYSICALLY_VALIDATED` | Registered bin position (user=0) |
| `CALIBRATION_TOOL_ID`| `[TBD]` | `______` | — | `PHYSICALLY_VALIDATED` | Controller tool frame for pointer stylus |
| `GRASP_TOOL_ID` | `[TBD]` | `______` | — | `PHYSICALLY_VALIDATED` | Controller tool frame for gripper jaws |

---

## 12. Final Commissioning Sign-Off

### 12.1 Engineering Verdict
- [ ] **ACCEPTED (FULL PASS):** All sections validated within nominal tolerances. Approved for Phase 5 Autonomous Play.
- [ ] **CONDITIONALLY ACCEPTED (PASS WITH WARNING):** Non-critical warnings noted and mitigated. Re-inspection required in 30 days.
- [ ] **REJECTED (FAIL / RECALIBRATION REQUIRED):** System violates safety or geometric contracts. Autonomous motion locked out.

### 12.2 Signatures
* **Lead Commissioning Engineer Signature:** `_____________________________` Date: `YYYY-MM-DD`
* **Safety Officer / Reviewer Signature (Recommended):** `___________________________` Date: `YYYY-MM-DD`
