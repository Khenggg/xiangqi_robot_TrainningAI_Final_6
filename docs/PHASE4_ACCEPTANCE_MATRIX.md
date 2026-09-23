# Phase 4 — Acceptance Matrix & Commissioning Verdict Standards

**Document ID:** `DOC-P4-ACCEPTANCE-001`<br>
**System:** FAIRINO FR3 Xiangqi Robotic System<br>
**Target Branch:** `docs/phase4a-final-evidence-corrective`<br>
**Applicability:** Phase 4 Physical Commissioning Sign-Off Gate  

---

## 1. Executive Summary & Gate Function

This document defines the quantitative and qualitative acceptance criteria for **Phase 4: Physical Calibration & Validation**. The criteria herein serve as the authoritative gate between laboratory commissioning and autonomous gameplay (Phase 5).

No autonomous gameplay moves or high-speed operations may be authorized until every subsystem in this matrix has achieved a confirmed status of **`PASS`** or an operator-approved **`PASS_WITH_WARNING`**.

### 1.1 Six-Stage Physical Connection & Commissioning Lifecycle
The physical runtime transitions through six strictly ordered, decoupled states:

```
1. DISCONNECTED
        │
        ▼ (connect() establishes telemetry-only RPC; does NOT call RobotEnable or Mode)
2. CONNECTED / TELEMETRY-ONLY
        │
        ▼ (Operator envelope clearance + explicit enable gate)
3. EXPLICIT ENABLE (RobotEnable(1) executed; drives energized, brakes released)
        │
        ▼ (Explicit mode selection)
4. EXPLICIT MODE CONFIGURATION (Mode(0) executed; manual/remote operational mode set)
        │
        ▼ (TCP calibrated + R1-R4 taught + PhysicalTeachingPointBoardPoseProvider SE(3) pass)
5. CALIBRATED
        │
        ▼ (Transit clearances verified + gripper pulse ladder tuned + bin validated)
6. MOTION AUTHORIZED (Authorized for Phase 3B MotionResolver/MotionExecutor pipeline)
```

> [!IMPORTANT]
> **STATE DECOUPLING PRINCIPLE:**
> In compliance with physical safety invariants:
> - `Connected != Enabled` (RPC connection is telemetry-only; drives remain de-energized).
> - `Enabled != Mode Configured` (Drive power is independent of controller operational mode).
> - `Mode Configured != Calibrated` (Controller readiness does not imply geometric board registration).
> - `Calibrated != Motion Authorized` (Valid kinematics do not authorize autonomous trajectories until clearance and capture interlocks are cleared).

---

## 2. Verdict & Provenance Taxonomy

### 2.1 Engineering Provenance Classification
All numerical values and parameters in commissioning documents are explicitly tagged under one of the following provenance classes:

| Provenance Class | Definition | Authority & Mutability |
| :--- | :--- | :--- |
| **`AUTHORITATIVE_CODE_CONTRACT`** | Hard-coded tolerance or boundary enforced in production Python modules (e.g. `BoardCalibrationTolerancePolicy`, `CAPTURE_BIN_VALIDATED`). | Code contract; non-negotiable without explicit software PR. |
| **`PROJECT_GEOMETRY`** | Standard Xiangqi dimensions ($320\times360\text{ mm}$ playable grid, $40\text{ mm}$ pitch, piece $D=22.5\text{ mm}, H=9.43\text{ mm}$). | Physical reference truth of standard game pieces and board. |
| **`CURRENT_SOFTWARE_DEFAULT`** | Software default parameters ($Z_{\text{safe}}=40.0\text{ mm}$, nominal pulse $=0.30\text{ s}$, deadtime $=0.10\text{ s}$). | Active software default; refined empirically during Phase 4. |
| **`CURRENT_CANONICAL_TOOL_GEOMETRY_ESTIMATE`** | Estimated geometric tool dimension (~150 mm flange-to-grasp center; historical CAD: 147.5 mm). | Engineering estimate; subject to physical tooling measurement. |
| **`PROPOSED_INITIAL_COMMISSIONING_LIMIT`** | Initial conservative commissioning parameter (e.g. speed override $\le 10\%$). | Commissioning safety limit; not a production software default (`MOVE_SPEED = 50`). |
| **`PROPOSED_INITIAL_TEST_VALUE`** | Heuristic lab starting points, review thresholds, or operator caution targets. | Engineering trial targets; tuned on physical hardware. **Not authoritative hard-fail thresholds.** |
| **`PROPOSED_MEASUREMENT_TOLERANCE`** | Proposed lab caliper tolerance guidelines (e.g. piece $D\pm0.3\text{ mm}, H\pm0.25\text{ mm}$). | Measurement reference; not defined in project geometry schema. |
| **`CONFIGURED_SOFTWARE_MODEL`** | End-effector wiring assignment modeled in software (DO1=OPEN, DO0=CLOSE). | Software configuration; pending physical wiring confirmation. |
| **`PHASE4_ACCEPTANCE_CRITERION`** | Overall system integration criteria (e.g. 90/90 cell reachability). | Integration sign-off gate; evaluated across the workspace. |
| **`PHYSICAL_E2E_ACCEPTANCE`** | Physical operational criteria (human corridor clearance, non-displacement of adjacent pieces). | End-to-end integration invariant verified by visual/physical inspection. |
| **`TBD_PHYSICAL_VALIDATION`** | Hardware identifiers or parameters unassigned until physical commissioning (Tool IDs, bin pose). | Unset; must be measured and recorded in Phase 4 log. |
| **`PHYSICALLY_VALIDATED`** | Empirical values measured, tested, and signed off in `phase4_physical_validation_log.md`. | Verified on physical hardware; promoted to production configuration. |

### 2.2 Operational Verdict Categories & Escalation

| Verdict Category | Formal Definition | Operational Consequence | Escalation & Remediation |
| :--- | :--- | :--- | :--- |
| **`PASS`** | 100% compliance with nominal engineering contracts and geometric tolerances. | Authorized to proceed to next commissioning step. | None required. Log data. |
| **`PASS_WITH_WARNING`** | Metric exceeds nominal warning boundary but remains safely within the hard failure threshold. | Conditionally authorized to proceed under heightened operator supervision. | Requires written notation and root-cause justification in the physical validation log. |
| **`REVIEW_AND_PAUSE`** | Measurement misses a proposed trial target (e.g. ping latency, TCP residual, spirit level, jaw opening). | **Pause progression and review setup.** | Check mechanical seating, alignment, or test parameters. Do NOT automatically classify as a hardware fault. |
| **`FAIL_RETRY`** | Non-systematic, transient execution failure (e.g. piece surface slip, operator timing error). | Halt current test step. Reset piece to initial condition. | Up to 2 retries permitted. If failure persists on 3rd attempt, escalate to `FAIL_RECALIBRATE`. |
| **`FAIL_RECALIBRATE`** | Systematic geometric, kinematic, or registration error violating authoritative code contracts. | **Immediate Halt of Autonomous Motion.** Invalidate downstream calibration. | Roll back to Section 3 (TCP) or Section 5 (R1–R4). Complete recalibration mandatory. |
| **`FAIL_HARDWARE`** | Electrical short, uncommanded disconnect, controller hardware fault, or damaged component. | **Immediate Drive De-energize (`RobotEnable(0)`).** Lock out system. | Hardware inspection required. Do not power on until repaired and re-inspected. |
| **`FAIL_SAFETY`** | Emergency stop tripped, trajectory collision, cable over-tension, or human exclusion incursion. | **Emergency Halt.** System hard locked. | Incident review mandatory. Commissioning suspended pending formal safety clearance. |

---

## 3. Comprehensive Subsystem Acceptance Criteria

### 3.1 Mechanical, Fixture & Environmental Integrity
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Base Mounting Rigidity** | Zero displacement under manual push (`PROPOSED_INITIAL_TEST_VALUE`) | Observable compliance | Base plate rocking or loose fasteners | Unstable $\to$ `FAIL_HARDWARE` |
| **Board Fixture Stability** | Zero displacement under manual check (`PROPOSED_INITIAL_TEST_VALUE`) | Slip $0.5 - 1.0\text{ mm}$ under load | Slip $> 1.0\text{ mm}$ under load | If slip $>1.0\text{ mm} \to$ `REVIEW_AND_PAUSE` & re-clamp |
| **Board Surface Leveling** | Inclination $< 0.5^\circ$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.5^\circ - 1.0^\circ$ | Inclination $> 1.0^\circ$ | If $>1.0^\circ \to$ `REVIEW_AND_PAUSE` & adjust shims |
| **Camera Mount Isolation** | Zero vibration transfer from arm (`PROPOSED_INITIAL_TEST_VALUE`) | Visible vibration on video | Camera shifted during test | Shift $\to$ `FAIL_SAFETY` |
| **Piece Dimensions (Calipers)**| $D = 22.5\text{ mm}, H = 9.43\text{ mm}$ (`PROJECT_GEOMETRY`); Dev $\le \pm 0.30 / 0.25\text{ mm}$ (`PROPOSED_MEASUREMENT_TOLERANCE`) | $D$ dev $0.3-0.5\text{ mm}$ | $D$ dev $> 0.5\text{ mm}$ | Out-of-spec piece $\to$ `FAIL_RETRY` |

---

### 3.2 Controller RPC & Electrical Safety
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Controller IP Address** | `config.ROBOT_IP = 192.168.58.2` (`AUTHORITATIVE_CODE_CONTRACT`) | — | Mismatched controller IP | Unreachable $\to$ `FAIL_HARDWARE` |
| **Workstation Subnet** | Configured on `192.168.58.0/24` (e.g. `.10`) (`RECOMMENDED_LAB_SUBNET_EXAMPLE`) | — | IP collision with `.2` | Conflict $\to$ `FAIL_HARDWARE` |
| **Network Ping Latency** | $< 2.0\text{ ms}$, $0\%$ drop (`PROPOSED_INITIAL_TEST_VALUE`) | $2.0 - 10.0\text{ ms}$ | $> 10.0\text{ ms}$ or packet loss | If $>2.0\text{ ms} \to$ `REVIEW_AND_PAUSE`; packet loss $\to$ `FAIL_HARDWARE` |
| **RPC Telemetry Read** | Error code `0`, drives de-energized (`AUTHORITATIVE_CODE_CONTRACT`) | Latency $> 200\text{ ms}$ | Non-zero SDK error code | SDK error $\to$ `FAIL_HARDWARE` |
| **Brake Disengage Behavior** | Smooth click, zero arm drop (`PROPOSED_INITIAL_TEST_VALUE`) | Audible friction | Servo hunting or drive fault | Drive trip $\to$ `FAIL_HARDWARE` |
| **Commissioning Speed Limit** | Speed override locked $\le 10\%$ (`PROPOSED_INITIAL_COMMISSIONING_LIMIT`) | $11\% - 25\%$ | $> 25\%$ during initial phase | $>25\% \to$ `FAIL_SAFETY` |

---

### 3.3 Tool Center Point (TCP) & End-Effector
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **`TCP_CALIBRATION` ID** | Tool Frame ID `TBD` (`TBD_PHYSICAL_VALIDATION`) | — | Undefined on controller | Undefined $\to$ `FAIL_SAFETY` |
| **`TCP_CALIBRATION` Residual**| Residual $< 0.30\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.30 - 0.50\text{ mm}$ | $> 0.50\text{ mm}$ | If $>0.30\text{ mm} \to$ `REVIEW_AND_PAUSE`; $>0.50\text{ mm} \to$ Re-calibrate |
| **`TCP_GRASP` ID** | Tool Frame ID `TBD` (`TBD_PHYSICAL_VALIDATION`) | — | Undefined on controller | Undefined $\to$ `FAIL_SAFETY` |
| **`TCP_GRASP` Z Offset** | $\approx 150.0\text{ mm}$ (`CURRENT_CANONICAL_TOOL_GEOMETRY_ESTIMATE`) | $145.0 - 155.0\text{ mm}$ | $< 140\text{ mm}$ or $> 160\text{ mm}$ | Out of range $\to$ `REVIEW_AND_PAUSE` |
| **Legacy 218mm Offset** | **Strictly Prohibited** (`LEGACY_OBSOLETE`) | — | Value loaded into controller | If found $\to$ `FAIL_SAFETY` |
| **Tool DO Wiring Model** | DO1 = OPEN, DO0 = CLOSE (`CONFIGURED_SOFTWARE_MODEL`) | — | Inverted physical actuation | Inverted $\to$ Swap channel config |
| **Tool DO Deadtime** | $0.10\text{ s}$ (`CURRENT_SOFTWARE_DEFAULT`) | Deadtime $< 0.05\text{ s}$ | Zero deadtime / simultaneous outputs | Simultaneous $\to$ `FAIL_HARDWARE` |
| **Gripper Opening Stroke** | Clear opening $> 32.0\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $28.0 - 32.0\text{ mm}$ | $< 28.0\text{ mm}$ (clips piece) | If $<32\text{ mm} \to$ `REVIEW_AND_PAUSE` pulse duration |
| **Nominal Open Pulse ($t_{\text{open}}$)**| Minimum reliable stroke pulse (`CURRENT_SOFTWARE_DEFAULT = 0.30s`) | $0.20 - 0.30\text{ s}$ | Motor strain buzz | If strain $\to$ `REVIEW_AND_PAUSE` & reduce pulse |
| **Nominal Close Pulse ($t_{\text{close}}$)**| Retention $\ge 1\text{ N}$ pull (`PROPOSED_INITIAL_TEST_VALUE`) | $0.20 - 0.30\text{ s}$ | Piece crushing or motor stall | If slip/crush $\to$ `REVIEW_AND_PAUSE` & tune pulse |

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
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Safe Transit Clearance ($Z_{\text{safe}}$)**| $40.0\text{ mm}$ default (`CURRENT_SOFTWARE_DEFAULT`); $\ge 25.0\text{ mm}$ piece margin | $15.0 - 25.0\text{ mm}$ | $< 15.0\text{ mm}$ | $<15\text{ mm} \to$ `FAIL_RECALIBRATE` |
| **Camera Enclosure Clearance** | $\ge 50.0\text{ mm}$ from wrist (`PROPOSED_INITIAL_TEST_VALUE`) | $30.0 - 50.0\text{ mm}$ | $< 30.0\text{ mm}$ | $<30\text{ mm} \to$ `FAIL_SAFETY` |
| **Pick Height ($Z_{\text{pick}}$)** | $4.715\text{ mm}$ baseline (`PROVISIONAL_SIMULATION / GEOMETRIC STARTING VALUE`); jaw clearance $\ge 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | Board clear $1.0 - 1.5\text{ mm}$| Jaws contact board surface | If clearance $<1.5\text{ mm} \to$ `REVIEW_AND_PAUSE` |
| **Place Height ($Z_{\text{place}}$)** | Flush release; drop $< 0.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | Drop $0.5 - 1.0\text{ mm}$ | Drop $> 1.0\text{ mm}$ or board deflects | If drop/deflect $\to$ `REVIEW_AND_PAUSE` & tune Z |
| **Tool Verticality Cant** | Square error $< 0.5^\circ$ (`PROPOSED_INITIAL_TEST_VALUE`) | $0.5^\circ - 1.0^\circ$ | $> 1.0^\circ$ | If $>0.5^\circ \to$ `REVIEW_AND_PAUSE` & align tool |
| **Wrist Singularity Margin ($J_5$)**| $|J_5| \ge 15.0^\circ$ across all cells (`PROPOSED_INITIAL_TEST_VALUE`) | $|J_5| \in [10.0, 15.0]^\circ$| $|J_5| < 10.0^\circ$ | If $<10^\circ \to$ Re-evaluate tool yaw $Rz$ |

---

### 3.6 Reachability & Kinematic Conditioning
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Four Corners Reachability** | 4 / 4 cells pass with code `0` (`AUTHORITATIVE_CODE_CONTRACT`) | Audible cable drag | Controller IK error | IK Error $\to$ `FAIL_RECALIBRATE` |
| **Representative Center/Edges** | 5 / 5 cells pass; no config flip (`AUTHORITATIVE_CODE_CONTRACT`) | Axis velocity peak | Arm branch flip during move | Branch flip $\to$ `FAIL_SAFETY` |
| **90-Cell Approach Sweep** | 90 / 90 cells reachable at $Z_{\text{safe}}$ (`PHASE4_ACCEPTANCE_CRITERION`) | Minor joint posture jerk | Any cell unreachable | Unreachable $\to$ `FAIL_RECALIBRATE` |
| **Spot Piece Pick Success Rate** | 10 / 10 clean picks ($100\%$) (`PROPOSED_INITIAL_TEST_VALUE`) | 1 slip with clean recovery | $\ge 2$ pick failures | $\ge 2$ fails $\to$ `REVIEW_AND_PAUSE` & re-evaluate grip |

---

### 3.7 Capture Bin & Gameplay End-to-End
| Check Item | Target Contract & Provenance | Warning / Caution Boundary | Hard Failure / Action Threshold | Verdict Rule |
| :--- | :--- | :--- | :--- | :--- |
| **Capture Bin Pose Status** | `CAPTURE_BIN_VALIDATED = False` interlock (`AUTHORITATIVE_CODE_CONTRACT`); unverified legacy default (`LEGACY_UNVERIFIED`) | — | Unvalidated physical bin motion | Unverified $\to$ `FAIL_SAFETY` |
| **Bin Corridor Human Clearance** | Corridor outside human player zone (`PHYSICAL_E2E_ACCEPTANCE`) | Transit within $100\text{ mm}$ | Corridor sweeps over human side | Incursion $\to$ `FAIL_SAFETY` |
| **Captured Piece Drop** | Lands completely inside bin (`PROPOSED_INITIAL_TEST_VALUE`) | Bounces near rim | Drops outside bin onto table | Drop fail $\to$ `FAIL_RETRY` & tune bin Z |
| **Single-Piece Move Accuracy** | Radial placement error $\le 1.5\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | $1.5 - 2.0\text{ mm}$ | $> 2.0\text{ mm}$ | $>2.0\text{ mm} \to$ `REVIEW_AND_PAUSE` & tune Z/TCP |
| **Capture Move Invariant 1** | Captured piece removed **first** (`AUTHORITATIVE_CODE_CONTRACT`) | — | Attacker moved before capture | Invariant break $\to$ `FAIL_SAFETY` |
| **Capture Move Invariant 2** | Attacker undisturbed during extraction (`PHYSICAL_E2E_ACCEPTANCE`)| Slight vibration | Attacker piece knocked/moved | Displaced $\to$ `FAIL_SAFETY` |
| **Adjacent Pieces Disturbance** | Zero contact with adjacent pieces (`PHYSICAL_E2E_ACCEPTANCE`) | Minor brush without move | Adjacent piece displaced | Displaced $\to$ `FAIL_RECALIBRATE` |
| **Board Bump Detection** | Auto-halt if board moves $> 2.0\text{ mm}$ (`PROPOSED_INITIAL_TEST_VALUE`) | — | Autonomous move after board bump | Motion after bump $\to$ `FAIL_SAFETY` |

---

## 4. Commissioning Sign-Off Gate Criteria

To successfully close Phase 4 and approve the robotic platform for Phase 5 (Autonomous Game Play), the following conditions must be satisfied:

1. **Zero Active Safety Violations:** Zero occurrences of unhandled E-stop events, cable pinches, or trajectory incursions.
2. **100% BoardPose Pass:** All geometric fit metrics pass within warning/hard-fail limits with documented residual values via `PhysicalTeachingPointBoardPoseProvider`.
3. **Calibrated Provenance Table Complete:** All canonical configuration parameters in Section 11 of the validation log are populated with empirical measurements and operator signatures.
4. **90-Cell Validation Verified:** The 90-cell CSV log is fully populated and counters demonstrate $100\%$ IK reachability at $Z_{\text{safe}}$ and $Z_{\text{pick}}$ (`PHASE4_ACCEPTANCE_CRITERION`).
5. **Phase 3B Architecture Compliance:** Trajectories are executed through the authoritative pipeline: `PieceMoveIntent / CaptureIntent` $\to$ `MotionResolver` $\to$ `MotionPlan` $\to$ `MotionExecutor` $\to$ `RobotBackend`.
6. **Lead Commissioning Engineer Sign-Off:** Written sign-off executed by the Lead Commissioning Engineer (secondary safety reviewer sign-off recommended where lab staffing permits).
