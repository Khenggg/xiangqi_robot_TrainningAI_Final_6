# Phase 4 — Acceptance Matrix & Commissioning Verdict Standards

**Document ID:** `DOC-P4-ACCEPTANCE-001`  
**System:** FAIRINO FR3 Xiangqi Robotic System  
**Target Branch:** `integration/unified-fr3-system`  
**Applicability:** Phase 4 Physical Commissioning Sign-Off Gate  

---

## 1. Executive Summary & Gate Function

This document defines the quantitative and qualitative acceptance criteria for **Phase 4: Physical Calibration & Validation**. The criteria herein serve as the authoritative gate between laboratory commissioning and autonomous gameplay (Phase 5).

No autonomous gameplay moves or high-speed operations may be authorized until every subsystem in this matrix has achieved a confirmed status of **`PASS`** or an operator-approved **`PASS_WITH_WARNING`**.

### 1.1 Five-State Physical Connection & Commissioning Lifecycle
The physical runtime transitions through five strictly ordered states:
```
DISCONNECTED
     │
     ▼ (connect() - strictly read-only RPC, no RobotEnable, no Mode switch)
CONNECTED / READ-ONLY
     │
     ▼ (Operator safety gate: visual envelope clear + explicit enable)
EXPLICIT ENABLE (RobotEnable(1), Mode(0), brake release)
     │
     ▼ (TCP calibration + R1-R4 teaching + BoardPoseProvider SE(3) pass)
CALIBRATED
     │
     ▼ (Transit clearances verified + gripper pulse ladder tuned + bin validated)
MOTION READY (Authorized for Phase 3B MotionResolver/MotionExecutor pipeline)
```

---

## 2. Verdict & Provenance Taxonomy

### 2.1 Engineering Provenance Classification
All numerical values in commissioning documents are explicitly tagged under one of the following provenance classes:

| Provenance Class | Definition | Authority & Mutability |
| :--- | :--- | :--- |
| **`AUTHORITATIVE_CODE_CONTRACT`** | Hard-coded tolerance or boundary enforced in production Python modules (e.g. `BoardCalibrationTolerancePolicy`). | Code contract; non-negotiable without explicit software PR. |
| **`PROJECT_GEOMETRY`** | Standard Xiangqi dimensions ($320\times360\text{ mm}$, $40\text{ mm}$ pitch, piece $D=22.5\text{ mm}, H=9.43\text{ mm}$). | Rigid physical truth of game pieces and board. |
| **`CURRENT_SOFTWARE_DEFAULT`** | Software default parameters ($Z_{\text{safe}}=40.0\text{ mm}$, $t_{\text{pulse}}=0.30\text{ s}$, deadtime $=0.10\text{ s}$). | Active defaults; refined empirically during Phase 4. |
| **`PROPOSED_INITIAL_TEST_VALUE`** | Heuristic lab starting points or targets (e.g. TCP residual $<0.3\text{ mm}$, ping $<2\text{ ms}$, clearance $\ge 50\text{ mm}$). | Engineering guidelines; tuned on physical hardware. |
| **`TBD_PHYSICAL_VALIDATION`** | Hardware identifiers or parameters unassigned until physical commissioning (e.g. Tool IDs, bin pose). | Unset; must be measured and recorded in Phase 4 log. |
| **`PHYSICALLY_VALIDATED`** | Empirical values measured, tested, and signed off in `phase4_physical_validation_log.md`. | Verified on physical hardware; promoted to production config. |

### 2.2 Operational Verdict Categories & Escalation

| Verdict Category | Formal Definition | Operational Consequence | Escalation & Remediation |
| :--- | :--- | :--- | :--- |
| **`PASS`** | 100% compliance with nominal engineering contracts and geometric tolerances. | Authorized to proceed to next commissioning step. | None required. Log data. |
| **`PASS_WITH_WARNING`** | Metric exceeds nominal warning boundary but remains safely within the hard failure threshold. | Conditionally authorized to proceed under heightened operator supervision. | Requires written notation and root-cause justification in the physical validation log. |
| **`FAIL_RETRY`** | Non-systematic, transient execution failure (e.g. piece surface slip, operator timing error). | Halt current test step. Reset piece to initial condition. | Up to 2 retries permitted. If failure persists on 3rd attempt, escalate to `FAIL_RECALIBRATE`. |
| **`FAIL_RECALIBRATE`** | Systematic geometric, kinematic, or registration error violating physical contracts. | **Immediate Halt of Autonomous Motion.** Invalidate downstream calibration. | Roll back to Section 3 (TCP) or Section 5 (R1–R4). Complete recalibration mandatory. |
| **`FAIL_HARDWARE`** | Electrical short, motor stall, damaged wiring, controller error, or broken mechanical fastener. | **Immediate Drive De-energize (`RobotEnable(0)`).** Lock out system. | Hardware technician service required. Do not power on until repaired and re-inspected. |
| **`FAIL_SAFETY`** | Emergency stop tripped, collision event, cable over-tension, or human exclusion zone violation. | **Emergency Halt.** System hard locked. | Incident review mandatory. Commissioning suspended pending formal safety clearance. |

---

## 3. Comprehensive Subsystem Acceptance Criteria

### 3.1 Mechanical, Fixture & Environmental Integrity
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Base Mounting Rigidity** | Zero displacement under manual push (`PROPOSED_INITIAL_TEST_VALUE`) | Observable compliance | Base plate rocking / bolt loose | Loose $\to$ `FAIL_HARDWARE` |
| **Board Fixture Stability** | Zero displacement under finger load (`PROPOSED_INITIAL_TEST_VALUE`) | Slip $0.5 - 1.0\text{ mm}$ | Slip $> 1.0\text{ mm}$ under load | $>1.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Board Surface Leveling** | Inclination $< 0.5^\circ$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.5^\circ - 1.0^\circ$ | Inclination $> 1.0^\circ$ | $>1.0^\circ \to$ `FAIL_RECALIBRATE` |
| **Camera Mount Isolation** | Zero vibration transfer from arm (`PROPOSED_INITIAL_TEST_VALUE`) | Visible vibration on video | Camera shifted during test | Shift $\to$ `FAIL_SAFETY` |
| **Piece Dimensions (Calipers)**| $D = 22.5\pm0.3\text{ mm}, H = 9.43\pm0.25\text{ mm}$ (`PROJECT_GEOMETRY`) | $D$ dev $0.3-0.5\text{ mm}$ | $D$ dev $> 0.5\text{ mm}$ | Bad piece $\to$ `FAIL_RETRY` |

---

### 3.2 Controller RPC & Electrical Safety
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Controller IP Address** | `config.ROBOT_IP = 192.168.58.2` (`AUTHORITATIVE_CODE_CONTRACT`) | — | Mismatched IP subnet | Unreachable $\to$ `FAIL_HARDWARE` |
| **Workstation Subnet** | Configured on `192.168.58.0/24` (e.g. `.10`) (`AUTHORITATIVE_CODE_CONTRACT`) | — | IP collision with `.2` | Conflict $\to$ `FAIL_HARDWARE` |
| **Network Ping Latency** | $< 2.0\text{ ms}$, $0\%$ drop (`PROPOSED_INITIAL_TEST_VALUE`) | $2.0 - 10.0\text{ ms}$ | $> 10.0\text{ ms}$ or packet loss | Packet loss $\to$ `FAIL_HARDWARE` |
| **RPC Read-Only Connect** | Error code `0`, no `RobotEnable(1)` (`AUTHORITATIVE_CODE_CONTRACT`) | Latency $> 200\text{ ms}$ | Non-zero SDK error code | Error $\to$ `FAIL_HARDWARE` |
| **Brake Disengage Behavior** | Smooth click, zero arm drop (`PROPOSED_INITIAL_TEST_VALUE`) | Audible rubbing | Servo hunting / current trip | Current trip $\to$ `FAIL_HARDWARE` |
| **Speed Override Enforcement** | Controller locked at $\le 10\%$ (`CURRENT_SOFTWARE_DEFAULT`) | $11\% - 25\%$ | $> 25\%$ during initial phase | $>25\% \to$ `FAIL_SAFETY` |

---

### 3.3 Tool Center Point (TCP) & End-Effector
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`TCP_CALIBRATION` ID** | Tool Frame ID `TBD` (`TBD_PHYSICAL_VALIDATION`) | — | Undefined on controller | Undefined $\to$ `FAIL_SAFETY` |
| **`TCP_CALIBRATION` Residual**| Residual $< 0.30\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.30 - 0.50\text{ mm}$ | $> 0.50\text{ mm}$ | $>0.50\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **`TCP_GRASP` ID** | Tool Frame ID `TBD` (`TBD_PHYSICAL_VALIDATION`) | — | Undefined on controller | Undefined $\to$ `FAIL_SAFETY` |
| **`TCP_GRASP` Z Offset** | $\approx 150.0\text{ mm}$ from flange (`CURRENT_SOFTWARE_DEFAULT`) | $145.0 - 155.0\text{ mm}$ | $< 140\text{ mm}$ or $> 160\text{ mm}$ | Out of range $\to$ `FAIL_RECALIBRATE` |
| **Legacy 218mm Offset** | **Strictly Prohibited** (`AUTHORITATIVE_CODE_CONTRACT`) | — | Value loaded into controller | If found $\to$ `FAIL_SAFETY` |
| **Tool DO Wiring Model** | DO1 = OPEN, DO0 = CLOSE (`CONFIGURED_SOFTWARE_MODEL`) | — | Inverted wiring | Inverted $\to$ `FAIL_HARDWARE` |
| **Tool DO Mutual Exclusion** | Hardware deadtime $\ge 100\text{ ms}$ (`CURRENT_SOFTWARE_DEFAULT`) | Deadtime $50 - 100\text{ ms}$| Both DO0 & DO1 active | Simultaneous $\to$ `FAIL_HARDWARE` |
| **Gripper Opening Stroke** | Clear opening $> 32.0\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $28.0 - 32.0\text{ mm}$ | $< 28.0\text{ mm}$ (clips piece) | $<28\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Nominal Open Pulse ($t_{\text{open}}$)**| Minimum reliable stroke pulse (`CURRENT_SOFTWARE_DEFAULT = 0.30s`) | $0.20 - 0.30\text{ s}$ | $> 0.30\text{ s}$ (motor stall) | Stall $\to$ `FAIL_HARDWARE` |
| **Nominal Close Pulse ($t_{\text{close}}$)**| Retention $\ge 1\text{ N}$ pull (`PROPOSED_INITIAL_TEST_VALUE`) | $0.20 - 0.30\text{ s}$ | $> 0.30\text{ s}$ or piece crush | Crush $\to$ `FAIL_RECALIBRATE` |

---

### 3.4 BoardPose Geometric Reconstruction (Authoritative Code Contracts)
> These limits are enforced directly by `BoardCalibrationTolerancePolicy` in `src/domain/board_pose_provider.py`. All values are `AUTHORITATIVE_CODE_CONTRACT`.

| Metric | Canonical Contract | Warning Threshold | Hard Failure Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Board Width (R1–R2, R4–R3)** | $320.00\text{ mm}$ | $|\Delta| \in (3.0, 5.0]\text{ mm}$ | $|\Delta| > 5.00\text{ mm}$ | $>5.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Board Height (R2–R3, R1–R4)**| $360.00\text{ mm}$ | $|\Delta| \in (3.0, 5.0]\text{ mm}$ | $|\Delta| > 5.00\text{ mm}$ | $>5.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Edge Symmetry Difference** | $0.00\text{ mm}$ | — | $> 5.00\text{ mm}$ | $>5.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Diagonal Difference** | $0.00\text{ mm}$ | — | $> 8.00\text{ mm}$ | $>8.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Kabsch RMS Fit Residual** | $0.00\text{ mm}$ | $\text{RMS} \in (2.0, 3.0]\text{ mm}$| $\text{RMS} > 3.00\text{ mm}$ | $>3.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Max Corner Residual** | $0.00\text{ mm}$ | — | $> 5.00\text{ mm}$ | $>5.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Max Plane Residual** | $0.00\text{ mm}$ | — | $> 3.00\text{ mm}$ | $>3.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Board Tilt Angle** | $0.00^\circ$ | $\theta \in (2.5, 5.0]^\circ$ | $\theta > 5.00^\circ$ | $>5.0^\circ \to$ `FAIL_RECALIBRATE` |
| **Frame Consistency** | User Frame = 0 | — | `user_id != 0` or Tool Mismatch| Mismatch $\to$ `FAIL_SAFETY` |

---

### 3.5 Operational Heights & Clearances
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Safe Transit Clearance ($Z_{\text{safe}}$)**| $40.0\text{ mm}$ default (`CURRENT_SOFTWARE_DEFAULT`); $\ge 25.0\text{ mm}$ piece margin | $15.0 - 25.0\text{ mm}$ | $< 15.0\text{ mm}$ | $<15\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Camera Enclosure Clearance** | $\ge 50.0\text{ mm}$ from wrist (`PROPOSED_INITIAL_TEST_VALUE`) | $30.0 - 50.0\text{ mm}$ | $< 30.0\text{ mm}$ | $<30\text{ mm} \to$ `FAIL_SAFETY` |
| **Pick Height ($Z_{\text{pick}}$)** | $4.715\text{ mm}$ baseline (`PROVISIONAL_SIMULATION / GEOMETRIC STARTING VALUE`); jaw clearance $\ge 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | Board clear $1.0 - 1.5\text{ mm}$| Jaws touch/pinch board | Jaw contact $\to$ `FAIL_RECALIBRATE` |
| **Place Height ($Z_{\text{place}}$)** | Flush release; drop $< 0.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | Drop $0.5 - 1.0\text{ mm}$ | Drop $> 1.0\text{ mm}$ or crush | Crush $\to$ `FAIL_RECALIBRATE` |
| **Tool Verticality Cant** | Square error $< 0.5^\circ$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.5^\circ - 1.0^\circ$ | $> 1.0^\circ$ | $>1.0^\circ \to$ `FAIL_RECALIBRATE` |
| **Wrist Singularity Margin ($J_5$)**| $|J_5| \ge 15.0^\circ$ across all cells (`PROPOSED_INITIAL_TEST_VALUE`) | $|J_5| \in [10.0, 15.0]^\circ$| $|J_5| < 10.0^\circ$ | $<10.0^\circ \to$ `FAIL_RECALIBRATE` |

---

### 3.6 Reachability & Kinematic Conditioning
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Four Corners Reachability** | 4 / 4 cells pass with code `0` (`AUTHORITATIVE_CODE_CONTRACT`) | Audible cable drag | Controller IK error | IK Error $\to$ `FAIL_RECALIBRATE` |
| **Representative Center/Edges** | 5 / 5 cells pass; no config flip (`AUTHORITATIVE_CODE_CONTRACT`) | Axis velocity peak | Arm branch flip during move | Branch flip $\to$ `FAIL_SAFETY` |
| **90-Cell Approach Sweep** | 90 / 90 cells reachable at $Z_{\text{safe}}$ (`AUTHORITATIVE_CODE_CONTRACT`) | Minor joint posture jerk | Any cell unreachable | Unreachable $\to$ `FAIL_RECALIBRATE` |
| **Spot Piece Pick Success Rate** | 10 / 10 clean picks ($100\%$) (`PROPOSED_INITIAL_TEST_VALUE`) | 1 slip with clean recovery | $\ge 2$ pick failures | $\ge 2$ fails $\to$ `FAIL_RECALIBRATE` |

---

### 3.7 Capture Bin & Gameplay End-to-End
| Check Item | Target Contract / Provenance | Warning Limit | Hard Failure Limit | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Capture Bin Pose Status** | `CAPTURE_BIN_VALIDATED = False` interlock (`AUTHORITATIVE_CODE_CONTRACT`); unverified legacy default (`LEGACY_UNVERIFIED`) | — | Unvalidated physical bin motion | Unverified $\to$ `FAIL_SAFETY` |
| **Bin Corridor Human Clearance** | $100\%$ corridor outside human zone (`AUTHORITATIVE_CODE_CONTRACT`) | Transit within $100\text{ mm}$ | Corridor sweeps over human side | Incursion $\to$ `FAIL_SAFETY` |
| **Captured Piece Drop** | Lands completely inside bin (`PROPOSED_INITIAL_TEST_VALUE`) | Bounces near rim | Drops outside bin onto table | Drop fail $\to$ `FAIL_RETRY` |
| **Single-Piece Move Accuracy** | Radial placement error $\le 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $1.5 - 2.0\text{ mm}$ | $> 2.0\text{ mm}$ | $>2.0\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Capture Move Invariant 1** | Captured piece removed **first** (`AUTHORITATIVE_CODE_CONTRACT`) | — | Attacker moved before capture | Invariant break $\to$ `FAIL_SAFETY` |
| **Capture Move Invariant 2** | Attacker undisturbed during extraction (`AUTHORITATIVE_CODE_CONTRACT`)| Slight vibration | Attacker piece knocked/moved | Displaced $\to$ `FAIL_SAFETY` |
| **Adjacent Pieces Disturbance** | Zero contact with adjacent pieces (`AUTHORITATIVE_CODE_CONTRACT`) | Minor brush without move | Adjacent piece displaced | Displaced $\to$ `FAIL_RECALIBRATE` |
| **Board Bump Detection** | Auto-halt if board moves $> 2.0\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | — | Autonomous move after board bump | Motion after bump $\to$ `FAIL_SAFETY` |

---

## 4. Commissioning Sign-Off Gate Criteria

To successfully close Phase 4 and approve the robotic platform for Phase 5 (Autonomous Game Play), the following conditions must be satisfied:

1. **Zero Active Safety Violations:** Zero occurrences of unhandled E-stop events, cable pinches, or trajectory incursions.
2. **100% BoardPose Pass:** All geometric fit metrics pass within warning/hard-fail limits with documented residual values.
3. **Calibrated Provenance Table Complete:** All canonical configuration parameters in Section 11 of the validation log are populated with empirical measurements and operator signatures.
4. **90-Cell Validation Verified:** The 90-cell CSV log is fully populated and counters demonstrate $100\%$ IK reachability at $Z_{\text{safe}}$ and $Z_{\text{pick}}$.
5. **Phase 3B Architecture Compliance:** Trajectories are executed through the authoritative pipeline: `PieceMoveIntent` / `CaptureIntent` $\to$ `MotionResolver` $\to$ `MotionPlan` $\to$ `MotionExecutor` $\to$ `RobotBackend`.
6. **Lead Commissioning Engineer Sign-Off:** Written sign-off executed by the Lead Commissioning Engineer (secondary safety officer review recommended where lab staffing permits).
