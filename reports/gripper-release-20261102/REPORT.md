# Gripper does not release — 2026-11-02

## Follow-up: user-requested short board release

Operator reports full release opening pushes neighboring pieces, then jaws narrow
after lifting. Source confirms place_at used OPEN_MAX then POST_RELEASE_LIFT then
CLOSE_TO_SAFE_GAP. User explicitly requested opening for 0.06s.

Added GRIPPER_ACTION_RELEASE and GRIPPER_RELEASE_PULSE_SEC=0.06; config validation
and gripper_ctrl use the existing interlocked pulse/cleanup path. place_at now
uses RELEASE and lifts without the old safe-gap close (only valid from full-open).
OPEN_MAX remains 0.30s for initial preparation and the capture bin. Twin release
intent supports the new action. No hardware command issued in this change.

Command (venv Scripts first on PATH, PYTEST_ADDOPTS=-x, DRY_RUN=1,
ROBOT_BACKEND=VIRTUAL, Windows/Python 3.12.10):

`tools/test_fast.ps1 -Workers 2 -Tests @('tests/unit/test_gripper_event_contract.py', 'tests/unit/test_legacy_physical_robot_gates.py')`

PASS: 29 tests, exit 0, pytest 3.73s / runner 9.75s, no serial tests selected.
New probes verify 0.06s DO0-only opening then both OFF, place order without
reclosing, and failed release prevents lift while attempting both OFF. Exact
source review checked new action/pulse/validation/twin dispatch. Graph impact
remains checkout-wide (797 files / zero symbols), not an isolated task delta.
Actual loaded release, travel width and repeated pick clearance NOT RUN; no
sensor provides millimeter opening. RPC overhead affects effective pulse duration.
App restart required. No full regression, calibration or arm/controller changes.

## Update after operator rewiring — direction verified, game release pending

The operator swapped the two gripper control wires and confirmed empty jaws,
stationary arm, direct observation and hands clear. Two separate authorized
single-channel tests passed fresh measured idle and controller [0,0,0] gates:

- DO1 ON once, nominal 0.30s at 14:12:53; operator observed **closing**.
  Evidence: `rewire-channel1-result-141253.json`.
- DO0 ON once, nominal 0.30s at 14:16:11; operator observed **opening**.
  Evidence: `rewire-channel0-result-141610.json`.

Each test acknowledged both outputs OFF before/after, exit 0 and no controller
fault before/after. No arm/mode/enable/reset commands. Electrical OFF was not
independently measured. The observations verify direction after rewiring; they
do not establish the original electrical cause or full opening stroke.

Updated only the gameplay mapping/comment in `config.py` to OPEN=DO0, CLOSE=DO1.
Pulse timings and calibration unchanged. `FR5Robot.__init__` caches these values;
the running app needs restarting before play. No hot reload or game replay run.
The alternate PhysicalFR3Backend/TwoOutputGripperDriver has separate legacy
defaults and is outside this gameplay mapping change.

Fresh mock verification: Windows, venv Python 3.12.10, DRY_RUN=1,
ROBOT_BACKEND=VIRTUAL, PYTEST_ADDOPTS=-x, venv Scripts first on PATH:

`tools/test_fast.ps1 -Workers 2 -Tests @('tests/unit/test_legacy_physical_robot_gates.py', 'tests/unit/test_gripper_event_contract.py', 'reports/gripper-release-20261102/test_open_once.py')`

PASS: 33 tests, exit 0, pytest 2.81s / runner 6.93s; no serial tests selected.
Graph detect_changes returned 797 checkout-wide files and zero impacted symbols;
it cannot isolate this config delta. Exact source review verified cached config
consumption and OPEN/CLOSE/safe-gap dispatch. No full regression or physical
piece-release cycle run. The historical findings below describe pre-rewire state.

## Observed game failure

User reports the robot picked a piece during play but did not open to release it.
Game log `logs/20261102_133219_3a98732d/events.jsonl` for move
`4277667ea73745bf924b9366369fa735` shows, in local time +07:00:

- 13:42:14.682 CLOSE DO0 for 0.80s.
- 13:42:17.744 RELEASE stage starts after PLACE_LAND.
- 13:42:17.896 OPEN MAX DO1 for 0.30s, then RELEASE completes.
- 13:42:18.496 POST_RELEASE_LIFT starts.
- 13:42:19.187 CLOSE TO SAFE GAP DO0 for 0.06s, after lifting.
- 13:42:23.023 FEN mismatch: destination row 2 / col 4 should contain a black
  cannon, but camera sees an empty cell.

This establishes that the open operation is present in the execution path. It
does not establish electrical output voltage, jaw travel or actual release.
The subsequent small close happens after lifting, not before the open request.

## Explicitly authorized isolated physical output test

User removed the piece, reported empty jaws and explicitly requested an observed
open test. The assistant announced one DO1 pulse, nominal 0.30s, followed by both
DOs OFF; no arm motion. No additional pulse was run after the result.

`open_once.py --execute` ran at 13:52:37–13:52:38 +07:00, exit 0. It received
three distinct fresh PHYSICAL FR3 states from the existing app WebSocket,
validated stationary joints / IDLE motion / IDLE stage / blocked game commands,
then checked controller errors. The measured arm was at the saved HOME pose.
The output-only test used bounded single-attempt XML-RPC, not a new SDK owner or
an additional controller state-stream connection.

Requests, each acknowledged with return code 0:

1. DO0 OFF.
2. DO1 OFF.
3. Deadtime 0.10s, fresh controller-fault check [0,0,0].
4. DO1 ON once.
5. Wait 0.30s after acknowledgement.
6. DO0 OFF, DO1 OFF; both acknowledged.

Controller errors before and after were [0,0,0]. Network dispatch/response time
adds to the nominal pulse duration; this is not a hardware-timed 0.300s pulse.
Evidence: `open-result-135237.json` and `preflight.json`.

**Operator observation:** jaws stayed still; no motor sound. Operator states
the hardware and wiring remain as previously used.

## Diagnosis boundary

VERIFIED: an isolated, acknowledged DO1 open request also fails to produce
observed motor motion. This symptom does not require game/FEN execution to occur.
No controller fault was reported during the isolated test.

UNKNOWN: whether the DO1 pin physically switched, whether the driver input
received it, motor/driver electrical condition, and any mechanical binding.
No jaw-position sensor or electrical measurement is available in this setup.
Raw GetToolDO is unsupported by this controller (-506); an SDK acknowledgement
cannot replace physical output or jaw feedback.

Keep the existing DO1=open / DO0=close mapping. Do not infer that a longer pulse,
reversed channels or simultaneous ON would repair the issue. The next useful
evidence is the existing driver's visible indicators/terminal identification or
an electrical output check by someone qualified, rather than repeating game moves.

## Software verification and unchanged scope

`tools/test_fast.ps1 -Workers 2 -ParallelOnly -Tests reports/gripper-release-20261102/test_open_once.py`
with venv Python 3.12.10: 4 mock tests PASS, exit 0, 2.33s pytest / 4.15s runner.
They cover mutual exclusion, initial-OFF failure, ON failure cleanup/no replay,
and trying the other OFF even when one OFF fails. They do not prove physical
gripper operation.

No production code, pulse calibration, DO mapping, robot enable/mode, safety
configuration, arm pose, journal or board state was changed by this task.
One explicitly authorized isolated physical output test was performed; the jaw
issue remains unresolved pending electrical/driver evidence.
