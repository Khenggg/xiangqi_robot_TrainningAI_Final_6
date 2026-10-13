# Windows viewer startup repair — 2026-10-09

## Findings and scope

- VERIFIED: SETUP_WINDOWS.bat originally installed only Python dependencies while the viewer imports local Three.js through /vendor/three/. A fresh checkout without node_modules would fail module loading. Setup now runs npm ci --include=dev with the existing lockfile, checks exit codes, and validates required assets.
- VERIFIED: RUN.bat discarded arguments and checked an obsolete moonfish-avx2.exe path. It now forwards arguments, checks the actual Python Moonfish entrypoint, and preserves Python exit status.
- VERIFIED under injected bad OS associations: pre-fix Python3.12 HTTP returned application/octet-stream for main.mjs and text/plain for Three.js; fixed server returns text/javascript for both. The actual observed original session currently returned correct MIME and rendered without this patch, so MIME is a preventive repair, not a confirmed historical root cause.
- UNCONFIRMED: the exact reason for the earlier one-off main.mjs resource error. Opening the same already-running server reproduced successful rendering; no browser errors were captured in that fresh tab. Do not claim a historical root cause from that generic log alone.

## Changes

- src/core/launch_options.py: deterministic JS/MJS MIME plus check_viewer_assets (no device access).
- main.py: actionable missing-viewer-asset error before opening HTTP server; existing port-busy handling retained.
- SETUP_WINDOWS.bat: installs pinned Three.js and checks asset availability; reports missing npm.
- RUN.bat: forwards CLI arguments, returns Python exit code and corrects Moonfish notice.
- tests/unit/test_viewer_startup.py: actual HTTP under bad MIME maps, missing assets and validation without starting threads.
- docs/START_PROJECT.md, CURRENT_STATE.md, KNOWN_ISSUES.md: setup/start instructions and evidence limits.

## Verification

| Check | Result |
|---|---|
| tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_viewer_startup.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_project_logging.py -ParallelOnly | PASS: 22, exit 0; Python3.11.15. PYTEST_ADDOPTS uses isolated basetemp. |
| Python3.12.10 reports/viewer-startup-fix-20261009/verify_python312.py | PASS: actual baseline/fixed HTTP headers, exit 0; python312-http.json/log. |
| npm.cmd ci --include=dev --no-audit --no-fund | PASS: exit 0, npm-ci.log. |
| Python3.12 import check matching setup: cv2, pygame, numpy, requests, torch, ultralytics, onnxruntime, pybullet, websockets, hardware_manager, launch_options | PASS: exit 0; imports only. |
| cmd /c RUN.bat --help with stdin from nul | PASS: Python3.12.10, help shown, exit 0. |
| cmd /c RUN.bat --viewer-port 0 with stdin from nul | PASS: invalid port rejected, exit 2. |
| CUA browser against isolated Python3.12 HTTP8098 / virtual telemetry8898 | PASS: robot/gripper/board render, SIMULATION/IDLE, reload/autoconnect, disconnect/reconnect; no error/warn logs. browser-proof.json and viewer-python312.jpg. |
| Independent gpt-6-luna medium static review | No blockers in scoped baseline comparison. Reviewer did not rerun tests. |
| Full SETUP_WINDOWS.bat installer | NOT RUN as a whole to avoid reinstalling the user's active Python environment; npm and exact import/asset validation components exercised separately. |
| Camera / FR3 actuation / physical play | NOT RUN. Virtual backend enforced for isolated verification; no camera was opened. |

First targeted run hit a pytest temporary-directory cleanup PermissionError after tests executed; rerun with a worktree basetemp finished with exit 0. Tests were not weakened.

## Delivery

Verified changes copied to the main dirty checkout only after SHA256 comparison with each original file. Existing unrelated changes preserved; no commit, merge, reset or push. The user's old game server was not stopped. Isolated test servers were closed cleanly. Restart the old game and reload the page to load updated Python server code.

The optional STEP loader still uses a CDN. This patch does not provide an offline CAD-loader bundle or prove physical commissioning.
