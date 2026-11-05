# FR3 live read-only check — 2026-10-31

## WebApp 500 request inspection — approximately 13:04

The browser connector now exposes the existing robot WebApp tab. Passive DOM,
static JavaScript GETs and retained network-request reads only; no UI control,
controller write or command replay by the assistant. Sanitized request bodies
and responses are in `webapp-request-evidence.json`.

- Requests 1162/1165 run the saved Home/IDLE joint-and-pose targets via cmd 201.
  Both return HTTP 200/body success, followed by record_500_error requests with
  `500 Error:Joint command point error`. HTTP receipt is not execution success.
- Request 1167 runs R1 and is followed by `500 Error:Command execution failed`.
- Requests 1229/1232 attempt SetToolCoord(0,0,0,0,0,0,0,0,0,0,0), then
  asynchronous `500 Error:Command execution failed` is recorded. DOM still
  shows Tool1/Wobj0. Tool0 activation has not been verified successful.
- The TCP Apply implementation in /js/pages/robot_setting.js also sends
  modify_load for the chosen load after its HTTP setData promise resolves;
  retained requests 1230/1233 contain load0/weight=0/CoG=0. Their HTTP success
  does not establish the controller's actual payload configuration.
- /js/pages/teaching-management.js runGlobalTeachingPoint forwards joints,
  tcf, speed, acc and ovl via cmd 201, but no row tool/workpiece fields. This
  supports an active-frame mismatch hypothesis; backend behavior remains
  uninspected, so it is not proof of the historical collision's cause.
- /js/pages/index.js handles asynchronous feedback key 500 and logs it through
  record_500_error. The displayed 500 is not an HTTP 500 in these requests.
- Fresh read-only GetRobotErrorCode at 13:03:55 +07:00 returned [0,1,1].

Correction to earlier user guidance: TCP Apply also requests the associated
load configuration; it must not be described as solely selecting a coordinate
frame. Do not repeatedly Apply/run points while the controller fault persists.
No calibration values or production source were edited by this investigation.

## Follow-up after user clarification — 12:04

User confirmed the symptom occurs during a game move: abnormal physical posture,
not merely an activation failure. A fresh read-only check at 12:04:08 +07:00
again returned main=1/sub=1, active tool/user=1/0 and nearly the same joints.
Five checksum-valid packets were decoded; see `noon-status.json`.

Additional deterministic probes use only an explicit fake controller whose
motion command acknowledges success while its measured pose remains distant and
motion-done remains false. Real SDK construction is forbidden in the fixture.
All three probes pass, demonstrating these current boundaries:

1. Normal stage telemetry readiness accepts MOVING; only the explicit idle
   variant rejects it.
2. `pick_at()` can proceed through LAND and GRIP with unchanged distant feedback
   when fake MoveCart calls return 0. It does not read measured TCP or motion-done
   at that boundary; the nominal vertical command also uses MoveCart.
3. With fake APPROACH returning 0 and LAND returning 112, the trace still calls
   APPROACH completed without measured arrival. LAND failure correctly prevents
   GRIP. This reproduces the log-state pattern, not physical collision causality.

Relevant exact source: `src/hardware/robot_VIP.py:289`, `:618`, `:667`, `:828`;
`src/hardware/hardware_manager.py:235`.

Command (venv Scripts prepended to PATH):
`.\tools\test_fast.ps1 -Workers 2 -ParallelOnly -Tests reports/controller-check-20261031/test_execution_boundaries.py`

**PASS: 3 passed in 16.50s; runner exit code 0**, Python 3.12.10, pytest 9.1.1,
xdist 3.8.0, Windows. These are diagnostic boundary probes; no production fix
or physical replay was performed. FAIRINO documents blendT=-1 as blocking. The
test intentionally injects an unexpected successful return without arrival;
it does **not** establish that the real controller returned early in the incident.

Required repair direction remains: validate a start/recovery configuration and
route before the first game movement; keep tool/planning references consistent;
verify fresh measured arrival before descent/grip; use a separately validated
linear descent rather than assuming MoveCart is linear. None of these implies
that an automatic HOME or an unreviewed MoveL replacement is safe from this pose.

## Result

At 11:43:01–11:43:03 +07:00, the physical controller at 192.168.58.2 replied
successfully. Two hundred fresh state packets passed checksum; no bad checksum
was observed. No game application was running; the latest existing application
log remained `logs/20261030_202855_7a8a6252/events.jsonl`.

**VERIFIED:** a controller fault is present independently of the game process:
`GetRobotErrorCode()` returned `[0,1,1]` before and after sampling, and all 200
packets reported main=1/sub=1. FAIRINO describes 1/1 as a joint command point
error. This does not identify a broken joint or prove the historical collision's
cause. [FAIRINO controller fault table](https://manual.fairino.support/latest/CobotsManual/appendix.html).

## Measured state

| Field | Value |
|---|---|
| Robot/software | FR3-V1-001(V6.0), Web v3.8.5.1, controller V3.8.25-QX |
| Main/sub fault | 1 / 1 |
| Robot / mode | stopped / manual |
| Enable / emergency-stop feedback | 1 / 0 |
| Motion done / queued commands | 1 / 0 |
| Collision feedback | 0; not proof of no historical physical contact |
| Active tool / user | **1 / 0** |
| Fixed profile tool / user | **0 / 0**, `fr3-fixed-user0-20261028` |
| Joints, degrees | [39.335407, -193.809265, 66.309998, -74.555183, -87.617599, -46.046421] |
| Active TCP XYZ, mm | [188.040207, -35.083660, 487.682526] |
| Active TCP RPY, degrees | [177.067902, 68.628860, -147.121689] |
| Flange XYZ, mm | [348.595612, 148.428955, 395.625977] |
| Flange RPY, degrees | [-59.308147, -42.692135, 109.982063] |

Positions use controller robot base with user 0. TCP uses active tool 1; flange
is a different reference. Largest joint spread within the two-second window is
0.000653 degrees. This is not continuous observation since yesterday.

Read-only controller `GetForwardKin(current joints)` matches TCP within 0.000031
per XYZ/RPY component. Direct XML-RPC GetActual*, GetTCPOffset and GetWObjOffset
return 14 with zero payloads. These failed payloads were rejected; they are not
zero poses, zero offsets or evidence that tool 0 is selected.

## Comparison with the previous observation

Compared with `reports/live-pose-20261030/analysis.json`, measured at 20:40 on
October 30, largest joint change is **0.001526 degrees**. Current flange XYZ is
within **0.018 mm** of yesterday's reported TCP. Today's active TCP XYZ differs
from yesterday's TCP by **260.649 mm**.

Thus these observations do not show a return to HOME. They show nearly the same
joint configuration with a different active TCP context. Today's TCP and flange
are **260.633 mm** apart. This describes different reference points, not a
measured calibration error or collision offset.

FK of saved HOME joints now gives [-112.543434,180.055695,89.474068,5.128741,
-1.387268,-175.726746] in the active tool context rather than the saved tool-0
HOME pose. Yesterday's HOME-reference calculations cannot be reused as today's
tool-1 calculations. No tool definition was changed during this check.

**UNKNOWN:** who or what selected tool 1 and when. This discrepancy today does
not prove tool 1 caused yesterday's first abnormal movement. MoveCart explicitly
receives its tool argument, so active selection alone does not prove every
future command would use the wrong tool. Tool definition and planning reference
still require verification.

## Software boundaries still present

- `src/ui/input_handler.py:1100`: F12 verifies the board and clears application
  transaction/error state. It does not call ResetAllError, restore HOME or
  validate an arm recovery trajectory.
- `src/hardware/hardware_manager.py:235`: a fresh ERROR snapshot fails
  physical_telemetry_ready. Controller faults can block activation even with a
  successful network connection.
- `src/hardware/hardware_manager.py:501`: activation lacks a separate verified
  starting-joint/route contract.
- `src/hardware/robot_VIP.py:618` and `:667`: approach and nominal vertical
  movement both use MoveCart(config=-1). FAIRINO documents this as point-to-point
  motion with current-joint reference, not a guarantee of straight descent or
  of the pre-interruption configuration.
  [FAIRINO movement API](https://manual.fairino.support/latest/SDKManual/PythonRobotMovement.html).

These paths remain as in the prior investigation. No motion implementation fix
was made between that report and this check. Resetting a session does not repair
this trajectory/recovery weakness.

## Verification and limits

Command: `.\.venv312\Scripts\python.exe reports/controller-check-20261031/read_only_probe.py`

Exit code **0**. Evidence: `live-probe.json`, `comparison.json`, raw
`state-frames.bin`, and independent offline checks in `verification.json`.

Controller packets have 960 bytes; the SDK structure has 1236. The probe checks
packet length/checksum and decodes only the common prefix through enable-state.
It does not invent trailing fields by zero padding. FK independently validates
the observed joint/TCP prefix. The version difference is recorded, not asserted
to have caused the incident.

No RobotEnable, Mode, ResetAllError, Move*, gripper/output, StopMotion,
frame-setting or calibration command was sent. No production code, journal or
calibration was changed. No application was launched.

**NOT RUN:** physical recovery/replay, automatic HOME, stop release, collision
path validation, production regression. Fault clearance alone does not establish
that the current posture, TCP and route are suitable for game motion.
