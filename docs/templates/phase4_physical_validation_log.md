# Phase 4 — Physical Commissioning & Validation Log

**Log Document ID:** `LOG-P4-YYYYMMDD-RUN01`  
**Test Date:** `YYYY-MM-DD`  
**Location / Facility:** `Robotics Lab / Station 1`  
**Lead Operator:** `[Name / Title]`  
**Secondary Observer / Safety Officer:** `[Name / Title]`  
**Overall Validation Status:** `[PENDING / PASS / PASS_WITH_WARNING / FAIL]`  

---

## 1. Hardware & System Configuration

### 1.1 Robot Manipulator Information
* **Manufacturer & Model:** FAIRINO FR3
* **Controller Serial Number:** `[Enter S/N]`
* **Controller Firmware Version:** `[e.g. v3.7.2]`
* **Manipulator Arm Serial Number:** `[Enter S/N]`
* **Controller IP Address:** `192.168.58.6`
* **Host Workstation IP Address:** `192.168.58.2`
* **Active Speed Override During Test:** `[e.g. 10% / 25%]`

### 1.2 Gripper Mechanism Information
* **Gripper Mechanism:** Custom Bidirectional DC Motor / Rack-and-Pinion
* **Driver Interface:** Two-Output Flange DO Interface (`TwoOutputGripperDriver`)
* **Open Control Channel:** Tool DO1 (Active HIGH pulse)
* **Close Control Channel:** Tool DO0 (Active HIGH pulse)
* **Jaw Opening Stroke:** `[Measured stroke, mm]` (Target: $\ge 32\text{ mm}$)
* **Jaw Pad Material:** `[Silicone / Neoprene Rubber]`

### 1.3 Tool Center Point (TCP) Configuration
* **`TCP_CALIBRATION` (Tool Frame 1):**
  * Calibration Mode: `[Mode A: Calibrated Pointer Tip / Mode B: Jaw Corner Contact]`
  * Offset from Flange: $X = \text{______}\text{ mm}$, $Y = \text{______}\text{ mm}$, $Z = \text{______}\text{ mm}$
  * Calibration Residual: `[______ mm]` (Requirement: $< 0.5\text{ mm}$)
* **`TCP_GRASP` (Tool Frame 2):**
  * Description: Geometric center between closed rubber jaw pads
  * Offset from Flange: $X = 0.00\text{ mm}$, $Y = 0.00\text{ mm}$, $Z = \text{______}\text{ mm}$ (Nominal CAD: $\approx 150.0\text{ mm}$)
  * Legacy 218mm Check: Confirmed NOT active `[YES / NO]`

### 1.4 Board & Fixture Information
* **Board Identifier / Type:** `[e.g. Standard Wood Xiangqi Board #1]`
* **Physical Outer Dimensions:** Measured: `______ mm` × `______ mm`
* **Grid Crosshair Spacing:** Measured: `______ mm` pitch (Canonical: $40.0\text{ mm}$)
* **Board Spirit Level Deviation:** $X\text{-axis} = \text{______}^\circ$, $Y\text{-axis} = \text{______}^\circ$ (Requirement: $< 1.0^\circ$)
* **Clamping / Fixture Method:** `[Corner Toggle Clamps / Vacuum / Magnetic / Stop Blocks]`

---

## 2. R1–R4 Teaching Readings

> All points taught in Base Frame (`user=0`) using `TCP_CALIBRATION` (Tool Frame 1).  
> Contact verified using $0.1\text{ mm}$ paper slip method.

| Point | Feature / Cell | X (mm) | Y (mm) | Z (mm) | Rx (deg) | Ry (deg) | Rz (deg) | Joint Angles [J1..J6] (deg) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R1** | (0, 0) Black Left Chariot | | | | | | | `[ , , , , , ]` |
| **R2** | (8, 0) Black Right Chariot| | | | | | | `[ , , , , , ]` |
| **R3** | (8, 9) Red Right Chariot  | | | | | | | `[ , , , , , ]` |
| **R4** | (0, 9) Red Left Chariot   | | | | | | | `[ , , , , , ]` |

* **Operator Initials:** `______`
* **Capture Timestamp:** `YYYY-MM-DD HH:MM:SS`
* **Active User Frame:** `user = 0` (Confirmed: `[YES / NO]`)

---

## 3. BoardPose Reconstruction & Geometric Fit Metrics

> Computed via `BoardPoseProvider.from_teaching_points()` using recorded R1–R4 coordinates.

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
| Pulse Duration (s) | Measured Jaw Opening (mm) | Motor Sound / Vibration | Stall / Heating Observed? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **0.10 s** | | `[Smooth / Weak / Stalled]` | `[NO / YES]` | |
| **0.15 s** | | `[Smooth / Normal / Stalled]`| `[NO / YES]` | |
| **0.20 s** | | `[Smooth / Normal / Stalled]`| `[NO / YES]` | |
| **0.25 s** | | `[Smooth / Hard Stop / Buzz]`| `[NO / YES]` | |
| **0.30 s** | | `[Hard Stop / Excessive]` | `[NO / YES]` | *Upper safety limit* |

* **Selected Nominal Open Pulse:** `______ s` (Recommended: Minimum duration achieving $>32\text{ mm}$ opening)

### 4.2 Closing Pulse Trials (DO0 = HIGH) with $22.5\text{ mm}$ Piece
| Pulse Duration (s) | Grip Security (1N pull test) | Piece Tilt / Deformation | Motor Stall Buzz? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **0.10 s** | `[Loose / Slips / Secure]` | `[None / Slight / Severe]` | `[NO / YES]` | |
| **0.15 s** | `[Loose / Slips / Secure]` | `[None / Slight / Severe]` | `[NO / YES]` | |
| **0.20 s** | `[Slips / Secure / Crushing]`| `[None / Slight / Severe]` | `[NO / YES]` | |
| **0.25 s** | `[Secure / Excessive]` | `[None / Slight / Severe]` | `[NO / YES]` | |
| **0.30 s** | `[Excessive / Motor Strain]` | `[Severe / Jaw Splay]` | `[YES - DANGER]`| *Do not exceed* |

* **Selected Nominal Close Pulse:** `______ s`
* **Configured Deadtime:** `0.10 s` (Hardware interlock confirmed: `[YES / NO]`)
* **Configured Settle Time:** `0.25 s`

---

## 5. Tool Orientation & Clearance Trials

### 5.1 Tool Verticality & Yaw Alignment
* **Machinist Square Perpendicularity:** $X\text{-axis error} = \text{______}^\circ$, $Y\text{-axis error} = \text{______}^\circ$ (Requirement: $< 0.5^\circ$)
* **Chosen Tool Orientation Vector:** $Rx = \text{______}^\circ$, $Ry = \text{______}^\circ$, $Rz = \text{______}^\circ$
* **Historical Orientation Comparison:** Deviation from historical $[-179.164, -3.047, -26.304] = \text{______}^\circ$
* **Joint 5 Singularity Margin:** $J_5$ angle at board center = $\text{______}^\circ$ (Requirement: $|J_5| \ge 15.0^\circ$)

### 5.2 Transit Clearance ($Z_{\text{safe}}$)
* **Nominal Clearance Above Board:** `40.0 mm`
* **Smallest Clearance Over Pieces ($9.43\text{ mm}$):** Measured: `______ mm` (Requirement: $\ge 25.0\text{ mm}$)
* **Clearance Over Captured Piece Stack ($20.0\text{ mm}$):** Measured: `______ mm`
* **Clearance from Overhead Camera Mount:** Measured: `______ mm` (Requirement: $\ge 50.0\text{ mm}$)
* **Verdict:** `[PASS / FAIL]`

---

## 6. Pick & Place Height Empirical Trials

### 6.1 Pick Height ($Z_{\text{pick}}$) Trials at Cell (4, 4)
| Candidate $Z_{\text{pick}}$ (mm) | Jaw-to-Board Clearance (mm) | Piece Contact Center | Grip Retention Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **6.50 mm** | | Upper rim of piece | `[SLIPS / DROPS]` | Too high |
| **5.50 mm** | | Upper half | `[WEAK / TILTS]` | Marginal |
| **5.00 mm** | | Center band | `[SECURE]` | Good |
| **4.72 mm** | | Theoretical midpoint | `[SECURE]` | Software baseline |
| **4.50 mm** | | Center band | `[SECURE]` | Firm |
| **4.20 mm** | | Lower half | `[JAW CONTACTS BOARD]`| Danger |

* **Highest Reliable Pick Height ($Z_{\text{pick, max}}$):** `______ mm`
* **Lowest Safe Pick Height ($Z_{\text{pick, min}}$):** `______ mm`
* **Accepted Nominal Pick Height ($Z_{\text{pick, nominal}}$):** `______ mm`
* **Tolerance Band:** $\pm \text{______ mm}$

### 6.2 Place Height ($Z_{\text{place}}$) Trials at Cell (4, 5)
| Candidate $Z_{\text{place}}$ (mm) | Piece Drop Distance (mm) | Piece Bounce / Skid? | Board Deflection? | Final $\Delta XY$ (mm) |
| :--- | :--- | :--- | :--- | :--- |
| **6.00 mm** | $\approx 1.5\text{ mm}$ | `[YES - SKIDDED]` | `[NO]` | |
| **5.00 mm** | $\approx 0.5\text{ mm}$ | `[NO - CLEAN]` | `[NO]` | |
| **4.72 mm** | $\approx 0.2\text{ mm}$ | `[NO - FLUSH]` | `[NO]` | |
| **4.50 mm** | $0.0\text{ mm}$ | `[NO - FLUSH]` | `[SLIGHT TOUCH]` | |
| **4.00 mm** | $0.0\text{ mm}$ | `[CRUSH RISK]` | `[YES - DEFLECTED]` | Board pinched |

* **Accepted Nominal Place Height ($Z_{\text{place, nominal}}$):** `______ mm`
* **Pick == Place Evaluated?** `[EQUAL / DIFFERENT]`
  * If different, justify: `________________________________________________`

---

## 7. Capture-Bin Calibration & Safety Waypoints

* **Bin Physical Coordinates in Base Frame (`user=0`):**
  * `BIN_APPROACH`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
  * `BIN_DROP`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
  * `BIN_RETREAT`: $X = \text{______}$, $Y = \text{______}$, $Z = \text{______}$ mm
* **Trajectory Safety Verifications:**
  * Trajectory clears board border by $> 40\text{ mm}$: `[PASS / FAIL]`
  * Trajectory completely avoids human player seating zone: `[PASS / FAIL]`
  * Captured piece does not strike bin rim on descent: `[PASS / FAIL]`

---

## 8. Kinematic Reachability & Boundary Verification

### 8.1 Four Corners & Edge Cells
| Cell Name | Coordinate (col, row) | IK Status | Singularity Risk ($J_5$) | Cable Tension | Clearance OK? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Corner 1 (R1)** | (0, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 2 (R2)** | (8, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 3 (R3)** | (8, 9) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Corner 4 (R4)** | (0, 9) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Center** | (4, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Top Edge** | (4, 0) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Bottom Edge** | (4, 9) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Left Edge** | (0, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |
| **Right Edge** | (8, 4) | `[0 / Error]` | $J_5 = \text{______}^\circ$ | `[Normal / Tight]` | `[YES / NO]` |

### 8.2 90-Cell Reachability Summary (See Attached CSV for Detail)
* Total Cells Evaluated: `90 / 90`
* Approach Waypoint Reachable ($Z_{\text{safe}}$): `[____ / 90]`
* Pick Waypoint Reachable ($Z_{\text{pick}}$): `[____ / 90]`
* Kinematic Singularities Encountered: `[0 / Details]`
* Attached CSV Log: `docs/templates/phase4_cell_validation.csv` (Verified & Attached: `[YES]`)

---

## 9. End-to-End Gameplay Execution Tests

### 9.1 Single-Piece Move Test (Cannon (1, 2) $\to$ (4, 2))
* Controller Move Return Code: `0` (Confirmed: `[YES / NO]`)
* Piece Pick Execution: `[CLEAN / SLIPPED / RETRIED]`
* Transit Smoothness: `[SMOOTH / VIBRATION OBSERVED]`
* Placement Accuracy Measured: $\Delta X = \text{______}\text{ mm}$, $\Delta Y = \text{______}\text{ mm}$, Radial Error = $\text{______}\text{ mm}$ (Limit: $\le 1.5\text{ mm}$)
* Vision System Board State Agreement: `[CONFIRMED / DISCREPANCY]`
* Step Status: `[PASS / FAIL]`

### 9.2 Capture Move Test (Chariot (0, 0) captures (0, 9))
* Opponent Red Piece Extracted First: `[YES / NO - CRITICAL INVARIANT]`
* Attacking Black Piece Undisturbed During Extraction: `[YES / NO]`
* Red Piece Successfully Dropped in Bin: `[YES / NO]`
* Black Piece Picked and Moved to (0, 9): `[YES / NO]`
* Final Black Piece Placement Radial Error: `______ mm` (Limit: $\le 1.5\text{ mm}$)
* Adjacent Squares Undisturbed: `[CONFIRMED / DISPLACED]`
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

| Configuration Key | Provisional Baseline | Calibrated Value | Unit | Engineering Provenance Summary |
| :--- | :--- | :--- | :--- | :--- |
| `PICK_TCP_HEIGHT_MM` | `4.715` | `______` | mm | Calibrated contact ladder, Station 1 |
| `PLACE_TCP_HEIGHT_MM`| `4.715` | `______` | mm | Calibrated flush release, Station 1 |
| `TOOL_ROTATION_RX` | `-179.164` | `______` | deg | Square-aligned perpendicularity |
| `TOOL_ROTATION_RY` | `-3.047` | `______` | deg | Square-aligned perpendicularity |
| `TOOL_ROTATION_RZ` | `-26.304` | `______` | deg | Grid-parallel jaw alignment |
| `GRIPPER_OPEN_PULSE` | `0.30` | `______` | s | Minimum reliable stroke duration |
| `GRIPPER_CLOSE_PULSE`| `0.30` | `______` | s | Minimum reliable grip duration |
| `CAPTURE_BIN_DROP_X` | `[Legacy]` | `______` | mm | Registered bin position (user=0) |
| `CAPTURE_BIN_DROP_Y` | `[Legacy]` | `______` | mm | Registered bin position (user=0) |
| `CAPTURE_BIN_DROP_Z` | `[Legacy]` | `______` | mm | Registered bin position (user=0) |

---

## 12. Final Commissioning Sign-Off

### 12.1 Engineering Verdict
- [ ] **ACCEPTED (FULL PASS):** All 20 sections validated within nominal tolerances. Approved for Phase 5 Autonomous Play.
- [ ] **CONDITIONALLY ACCEPTED (PASS WITH WARNING):** Non-critical warnings noted and mitigated. Re-inspection required in 30 days.
- [ ] **REJECTED (FAIL / RECALIBRATION REQUIRED):** System violates safety or geometric contracts. Autonomous motion locked out.

### 12.2 Signatures
* **Commissioning Engineer Signature:** `_____________________________` Date: `YYYY-MM-DD`
* **Safety Officer / Reviewer Signature:** `___________________________` Date: `YYYY-MM-DD`
