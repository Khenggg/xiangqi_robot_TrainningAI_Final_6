# Physical game startup failure recovery — 2026-10-09

## Verified diagnosis

Observed session: logs/20261009_175604_de0b28bf.
- 17:57:39: camera index1 did not provide a readable frame. _init_camera raised Camera startup blocked; initialize_all cleaned partial resources and re-raised; main.py had no local handler, logged APP_UNHANDLED and closed the game.
- WindowsCamera process 21820 was present when inspected. Camera contention is plausible; exact contention vs index/driver/permissions cause remains unconfirmed. No camera was opened or forcibly closed during this task.
- Independent blocker at 17:57:38: the physical mirror refused an unset physical board surface contact offset. The calibration gate was preserved; this task does not make up an offset or prove physical parity.

## Repair

main.py now keeps the launcher active on initialize_all failure, clears hw, retains existing manager-owned partial cleanup, shows the failure with retry/log instructions and permits an explicit new selection. board_renderer.py wraps the message in a visible panel below the controls. Physical enable, startup device selection, collision/calibration gates and hardware configuration were not changed.

## Evidence

- tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_startup_failure_recovery.py,tests/unit/test_camera_startup_and_health.py,tests/unit/test_game_window.py -ParallelOnly: PASS, 25 tests, exit 0, Python3.11.15. PYTEST_ADDOPTS=--basetemp=reports/startup-camera-recovery-20261009/pytest-tmp. See tests.log.
- New tests execute the actual main.py with runpy: AI/robot/camera failures each exercised twice, home remains active, no viewer/telemetry started, partial cleanup called twice, no APP_UNHANDLED, no FR3 connection. Hardware startup stages are mocked.
- Python3.12.10 verify_python312.py: PASS, exit 0, actual entrypoint/UI rendering with two mocked camera failures and explicit retry; image retained as startup-error-python312.png and structured evidence python312-result.json. Final image panel verified visually. No physical devices used.
- Independent gpt-6-luna medium scoped review: no blocker; test source inspected but not executed by reviewer. Final panel backing was inspected inline and exercised by the Python3.12 probe.
- Probe rerun initially rejected its own historical log directory count; artifact assertion was corrected to select the newest session. No product code or tests were weakened to hide a device failure.

## Limits and delivery

Physical camera readability was NOT tested. FR3 motion was NOT performed. Physical calibration is still missing. Failures after initialize_all are outside the new recovery catch and may need their own handling if reproduced.

Copied verified files to main after baseline SHA256 checks; unrelated dirty changes retained. No commit, push, reset, or hardware actuation. Close competing camera applications yourself, rerun .\RUN.bat --physical, and choose a mode again. The GUI now reports startup errors instead of closing.
