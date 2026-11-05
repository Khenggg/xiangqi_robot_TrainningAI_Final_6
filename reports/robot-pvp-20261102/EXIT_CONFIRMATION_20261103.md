# One-confirmation exit — 2026-11-03

User requested Exit/Stay, with immediate exit after consent and no hardware
prerequisites. The old recovery loop rejected manual-disable confirmation until
stop proof existed, and rejected forced exit while pending/ownership flags were
set. This trapped the disconnected session.

`src/ui/exit_confirmation.py` provides the confirmation and process exit.
`main.py` routes window X, focused Ctrl+C, terminal interruption, camera-q and
recovery-window X/Ctrl+C through it. Enter/Y or Exit confirms; Escape/N or Stay
cancels. A second X keeps the question open. `os._exit(0)` intentionally bypasses
potentially blocked cleanup, atexit and worker joins. No SDK/DO/reset/enable
command is sent. Saved journal records are neither deleted nor marked complete.
F2 mode disposal, New Game and Surrender retain their existing behavior.

## Verification

PASS — command (PowerShell, venv Python3.12.10, pytest9.1.1, Windows):

```powershell
$env:PATH=(Join-Path (Get-Location) '.venv312\Scripts')+';'+$env:PATH
$env:PYTEST_ADDOPTS='-x'
$env:DRY_RUN='1'
$env:ROBOT_BACKEND='VIRTUAL'
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_exit_confirmation.py,tests/unit/test_robot_pvp_main_ui.py
```

Exit0,12 passed (1 parallel +11 serial),9.78s. Evidence:
`exit-confirmation-tests.txt`. Real subprocess exits despite a blocked non-daemon
thread and bypasses atexit; existing journal fixture remains unchanged. Headless
Pygame tests cover keyboard/mouse confirmation/cancellation. Actual main-loop
mock game tests cover two turns, cancelled exit, confirmed exit and existing
surrender/new-game flow, plus real terminal SIGINT cancelled without shutdown.
SIGINT only queues a flag for the UI thread; its original handler is restored
when the launcher returns. Integration tests replace the process-exit function so
pytest itself remains alive. Hardware was not operated; no live restart/full
regression/merge performed. Existing process was closed separately after user
confirmed disabled servo/power; journal backed up before closing.

Graph search/detect_changes: NOT AVAILABLE (`Transport closed`). Exact source
and callers inspected as fallback. Change confined to software exit admission;
no coordinate/calibration/planning/controller changes.

Scoped independent review: initial terminal Ctrl+C cancellation finding repaired
with queued SIGINT and an actual-launcher regression check. Final review found
no remaining issue in the exit delta. `git diff --check`: PASS, exit0.
