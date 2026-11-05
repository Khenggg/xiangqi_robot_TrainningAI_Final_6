# Verified camera board, hardware recovery still blocked

Scope: urgent recovery diagnosis; two-player physical mode implementation paused.
No motion, enable, reset, gripper, calibration or session deletion performed.

## Evidence and cause

User attachment contains successful `camera.verified` and 32-piece baselines in
`logs/20261102_161136_33588977`, followed by generic PHYSICAL_ENABLE_FAILED at
16:14:11. Camera success does not resolve controller or measured-stop recovery.

Read-only `GetRobotErrorCode` at 2026-11-02T16:30:45.792414+07:00 returned
`[0, 1, 29]`: RPC success, controller main=1/sub=29. Exit 0. No SDK receiver or
motion owner opened. Exact query:

```powershell
.\.venv312\Scripts\python.exe -c 'import json,datetime; from src.hardware.rpc_transport import BoundedRPCProxy; c=BoundedRPCProxy("http://192.168.58.2:20003",timeout_s=1); print(json.dumps({"time":datetime.datetime.now().astimezone().isoformat(),"query":"GetRobotErrorCode","result":c.GetRobotErrorCode(),"actuation":False}))'
```

FAIRINO latest manual 4.0.1, appendix main=1/sub=29 describes joint feedback
speed over limit, not resettable. Firmware-specific parity and historical root
cause are not established. Do not confuse this main/sub pair with standalone
SDK/servo error 29.
Source: https://manual.fairino.support/latest/CobotsManual/appendix.html

`attach_journal(fresh_start=True)` creates a fresh opening board and archives old
transactions. It deliberately retains the need to inspect physical uncertainty
after interrupted work. `approve_recovery_after_verification` requires fresh
idle telemetry plus safe controlled-stop evidence. An active controller fault
correctly prevents that approval. Clearing application data cannot fix it.

## Changes

- HardwareManager reads a snapshot to report controller/error, stale/disconnected
  telemetry, or non-idle motion before the generic pending-board enable error.
- Recovery approval logs `recovery.hardware_blocked` / `ROBOT_NOT_READY` with
  `board_verified` and the specific hardware reason.
- V and F12 preserve a hardware-blocked diagnostic after camera verification;
  they no longer replace it with a board mismatch or manual piece correction.
- GameState exposes a transient hardware diagnostic to the left recovery panel.
  It is not persisted or used to authorize recovery/motion; cleared at new
  verification, recovery approval and reset.
- F4 wording says camera confirmed a board, not that the scanned board already
  matches the current FEN. F4 can legitimately scan a different layout.
- Existing enable/recovery/stop gates remain intact; no automatic motion/replay.

## Validation

Environment: Windows, Python 3.12.10, pytest 9.1.1; venv on PATH;
`DRY_RUN=1`, `ROBOT_BACKEND=VIRTUAL`, `PYTEST_ADDOPTS=-x`.

Final scoped command:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_recovery_block_diagnostics.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_reliability_recheck.py,tests/unit/test_f2_camera_and_frame_restart.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_client_mode_controls.py
```

PASS, exit 0: 77 parallel + 1 serial = 78 tests, runner 20.82s.
The serial test uses a mock robot and local WebSocket, not physical hardware.
Covered controller 1/29 and verified 32-piece opening, V/F4/F12, old/expected
pending board with no retire/commit/replay, stale/disconnected/moving telemetry,
missing stop proof, healthy stop recovery, cleared diagnostic on mismatch,
activation failure before enable, and persistent panel explanation. Reset cleanup
was inspected in source.
Two existing WebSocket deprecation warnings.

Exploratory legacy test run including `tests/test_emergency_client_move.py`:
FAIL, exit 2 (53 pass, 2 failures before fail-fast). One enable fixture needed
the now-read backend snapshot; updated to explicitly supply fresh idle telemetry
and included in the successful final run. Other legacy mouse test failed to
save rollback. A follow-up `PYTEST_ADDOPTS='-x -k test_v_'` run on that legacy
file also FAILED (1 pass, 2 failures): obsolete lightweight fixtures lack
`approve_recovery_after_verification` or `simulation_runtime`. These legacy
fixture contracts were not repaired in this bounded task. No whole-suite pass
is claimed.

Code review found the initial F4 matched-FEN wording error; corrected and test
uses a different scanned layout. Final scoped review reported no blocker.
Graph detect_changes reports 798 checkout-wide entries and no impacted symbols;
its baseline includes unrelated work and cannot isolate this patch. Exact-file
review and focused tests are the applicable evidence. LAST_REVIEWED_HEAD unchanged.

## Remaining boundary

Controller fault resolution and actual physical/full-game operation NOT VERIFIED.
No full regression or running-window UI acceptance performed. Existing process
must reload code; it was not killed/restarted here. Do not enable/HOME while the
controller still reports a fault. After controller recovery and physical
inspection, require fresh idle/stop proof and verified board before explicit
operator enable. Manufacturer-specific handling is required if 1/29 persists.
