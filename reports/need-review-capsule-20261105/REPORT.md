# need-review capsule r2 — 2026-11-05

## Scope and artifact

Current remote baseline: need-review 30649c465808 (includes 568d435 robot PvP/session/exit feature). Integrated portable capsule on top of this baseline; not a replacement with the older final branch. Current main/game/PvP/session/input/exit source preserved unchanged; only UI font and virtual native-path adaptations touch runtime source.

Artifact: dist/Xiangqi-Capsule-NeedReview-Windows-x64-20261105-r2.zip
Size: 386,975,679 bytes (369.0 MiB).
SHA256: dc9bbc820b4e479c904c084c9619439d743dc4e8d037a0394bfd04fa327f1754
Release destination: https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-need-review-windows-x64-20261105-r2

One START.bat; app-local CPython 3.12.10, 47 pinned CPU packages, local weights/engine, viewer JS/CAD and CJK font. No Python/Node/Git/CUDA install, pip/npm or first-run downloads on event PC. Four current game modes retained, including HUMAN_VS_HUMAN_ROBOT and actual localhost Black client. Existing physical motion ownership/verification gates retained. No physical controller/camera accessed or actuated by this work.

Builder source allowlist excludes workstation .env, venv, runtime journal and logs. Explicit team-model input; full payload provenance/size/SHA256 manifest, versioned ZIP + sidecar. Signature verification now uses Windows PowerShell 5 native Security module tree rather than relying on a tool-provided pwsh. CPU dependencies reused only after all 47 requested distribution versions matched the known successful cache. Source requirement contents unchanged apart from EOL in cache reconciliation.

## Verification

1. Project runner: tools/test_fast.ps1 -Workers 2 -Tests <eight files below>. 105 PASS (93 parallel + 12 serial), exit 0, 24.02s. Exact log logs/capsule/need-review-tests.log (ignored).
   - test_windows_capsule.py
   - test_robot_pvp.py
   - test_pvp_room_and_client.py
   - test_exit_confirmation.py
   - test_robot_pvp_main_ui.py
   - test_session_buttons.py
   - test_session_modes.py
   - test_client_mode_controls.py
   Two websockets deprecation warnings in serial phase. Existing baseline publication documented broader failures; this is not a full-suite PASS.
2. Actual tools/capsule/build.py build, output dated need-review-r2. Packaged interpreter with PATH System32-only --smoke PASS: full original immutable-manifest verification; all runtime imports app-local; real ONNX CPU sessions, YOLO CPU inference, Moonfish subprocess handshake, PyBullet DIRECT, Pygame/CJK renderer. No network allowed in model/engine checks.
3. Operator guide clarified main/host vs Black-window exit wording after first build copy; READ_ME_FIRST and manifest entry synchronized and ZIP recreated before final acceptance. No runtime code changed in this documentation finalization. Final ZIP SHA256 and extraction CRC verified; release contains no inherited app logs/journals/venv/env.
4. Untouched FINAL ZIP extracted into `dist/acceptance/NeedReview - Bàn giao mới r2/`. Its own runtime executed tools/capsule/acceptance_probe.py with PATH System32 only. Exit 0; all six checks true in state/acceptance.json; log logs/capsule/need-review-acceptance.log.
   - Offline runtime/models, local AI returns legal b0c2, actual 32-piece virtual world.
   - Existing loopback HTTP server serves viewer HTML/Three.js/WASM correctly.
   - Actual bundled -m src.ui.pvp_client --help; separate bundled child constructs ClientApp, renders Black window, receives localhost welcome/state, sends canonical move request to room host, exits. No executor or physical transaction called by this probe.
   - Real main.py starts new menu, renders new mode buttons and real exit-confirmation dialog. Probe feeds Enter and intercepts only exit_application with SystemExit so evidence can be recorded. This proves menu/dialog routing, not production os._exit cleanup. Dedicated existing subprocess exit tests passed in step 1.
   - Main window screenshot visually inspected: new 2 NGƯỜI + ROBOT / VÀO PHÒNG buttons and exit modal visible.
5. All 187 current runtime source/asset hashes match manifest; launcher.py and READ_ME_FIRST match current packaging source/guide. New main/PvP/session/exit files present and match need-review baseline. ZIP size/hash match sidecar. README local links/anchors/fences and whitespace checks performed before delivery.
6. Independent code review: no integration blocker; corrected documentation to scope confirmation to main/host window. Black client X closes directly. Packaging includes current modules and launches Black with sys.executable/app-local module paths.

## Changes delivered

Packaging tooling/build launcher, tested isolated runtime/native DLL strategy, Unicode/relocation-safe virtual mesh paths, bundled CJK fallback; README old numbered format synchronized to actual current modes/controls and direct new ZIP link as first heading. Operator/build guide describes source-vs-release ZIP, O/room/same-PC client, local mode/host settings, exit distinction and calibration boundary. Separate need-review release/tag; older final release is not overwritten.

## Limits

No fresh second-PC/clean-Windows or full UI game/browser acceptance; no camera accuracy, driver/network commissioning, real robot/gripper motion or controller recovery acceptance. Robot/camera profiles are kit-specific; portable software does not make a moved camera or another robot calibrated. Existing KNOWN_ISSUES and broader regression gaps remain. No whole-repo/merge approval; historical LAST_REVIEWED_HEAD is unchanged.
