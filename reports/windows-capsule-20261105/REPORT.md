# Windows capsule — delivery evidence (2026-11-05)

## Artifact

- Build baseline: need-review, eb6945739f82a79f2c731521a661449d121a6a65 plus capsule changes, before the final source commit. Source file hashes and original build dirty status are recorded in manifest.json. All 184 runtime source/asset hashes were subsequently checked against the final delivery worktree and matched.
- Release: dist/Xiangqi-Capsule-Windows-x64-20261105.zip
- Size: 386,706,814 bytes (368.8 MiB).
- SHA256: c5d1a6570d41954ffbeb0dbc0fb7451b275fa943f2bc09fbd1f61606f1120f5e
- Sidecar: dist/Xiangqi-Capsule-Windows-x64-20261105.zip.sha256
- Operator: extract full ZIP to writable local folder, open START.bat, select mode. No event-PC Python/Node/Git/CUDA install or pip/npm/setup/download step. CPU baseline, Windows 10/11 x64 desktop with browser.

## Contents and changes

Official app-local CPython 3.12.10 with isolated _pth, 47 pinned Python packages/CPU dependencies, local Moonfish, best.pt and both CChess ONNX models, optional local board/hand checkpoints, tracked FR3/CAD/board assets, locked Three.js, CJK font and license notices. SHA256 manifest covers immutable payload; settings/state and newly created game journals/logs remain mutable.

Builder uses tracked runtime allowlist and explicit model inputs, integrity-checked caches, source/dependency provenance and offline packaged-interpreter smoke gate. It excludes workstation venv, .env, logs and session journals. Runtime/model/cache/ZIP remain outside Git. Stock PyBullet demo datasets, headers, static libraries and test directories are omitted; app-specific FR3/board assets are retained.

Launcher fixes CPU/local engine, ignores inherited workstation runtime/credential settings, validates release/settings, writes actionable error log and enters existing game menu. Existing physical read-only startup, operator enable/stop/recovery gates are retained. It does not clear recovery journals or auto-enable/move the arm.

Two necessary source adaptations: bundled CJK font fallback for English-only Windows; relocation/Unicode-safe PyBullet asset resolver and preservation of its native path. No robot poses, motion commands, safety thresholds, game rules or pending/recovery transaction behavior changed.

## Commands and observed results

1. `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_windows_capsule.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_session_modes.py,tests/unit/test_client_mode_controls.py`
   - 66 passed, exit 0; no serial tests selected. Log logs/capsule/unit-release.log (ignored).
   - Covers missing/corrupt payload, full-manifest path traversal, settings validation, source allowlist, cache integrity/reuse, offline socket guard, mutable journal preservation, font fallback, moved URDF cache and Unicode data-only cache, existing mode/control/startup behavior.
2. `BUILD_CAPSULE.bat --models D:/Projects/xiangqi_robot_TrainningAI_Final_6/models --output dist/Xiangqi-Capsule-Windows-x64-20261105`
   - Exit 0, actual ZIP and sidecar created. Log logs/capsule/build-release.log.
   - Packaged interpreter --smoke, PATH only System32: full SHA256 verification; all imported runtime libraries local to capsule; actual Moonfish handshake/subprocess; actual ONNX CPU model sessions; actual YOLO CPU inference; PyBullet DIRECT; headless Pygame home renderer and CJK glyph metrics. Python socket connect prohibited during model/engine checks. No camera/controller opened.
3. Final ZIP SHA256 verified before extraction; extraction CRC checked. No workstation journals/logs/venv/env in ZIP. Required native runtime files present; stock demo data absent.
4. Extracted untouched FINAL ZIP into `dist/acceptance/Bàn giao hoàn chỉnh/`. Ran its own runtime with only System32 on PATH:
   - `runtime/python.exe -u -B -I tools/capsule/acceptance_probe.py <relocated-capsule-root>`
   - Exit 0. Log logs/capsule/final-acceptance.log. Proof state/acceptance.json in relocated folder.
   - All offline runtime/model checks PASS; Moonfish returned legal opening move b0c2; real VirtualXiangqiSimulation constructed all 32 pieces; existing local HTTP viewer served HTML/Three.js/WASM with correct MIME; actual main.py opened/rendered home menu and shut down via QUIT, no physical session. Screenshot state/main-home-window.png visually inspected.
5. Native runtime observation in a fresh packaged process (PATH System32 only): GetModuleHandleW/GetModuleFileNameW confirmed msvcp140.dll, msvcp140_1.dll, vcruntime140.dll, vcruntime140_1.dll and python3.dll loaded from this capsule's runtime directory, not System32. Exit 0, logs/capsule/native-runtime-proof.log.
6. Independent review inspected 301 native PE import/delay-import tables (zero parse failures), then fixes and native-path code. No remaining blocker reported. No reviewer hardware calls.
7. Source compilation, README links/anchors/fences and git diff --check PASS.

## Defects caught during packaging and addressed

- Initial pip install exhausted system-drive temp space; retried with task temp on D. Builder now puts its temporary wheel work on build drive. No unrelated data deleted.
- Missing generic MSVCP140 / MSVCP140_1 could be silently supplied by build PC. Bundle now includes Microsoft-signature-verified VC DLL quartet and requires python3.dll. Actual loaded-module locations verified as above.
- Generated URDF cached absolute old-root paths. Resolver compares resolved content instead of trusting mtime.
- Bullet Windows narrow path APIs failed on a Vietnamese extraction directory despite model checks passing. Resolver now preserves ASCII short aliases, or creates a process-owned ASCII temporary directory containing only mesh/texture data; no cwd change, drive mapping, journal/profile/executable copy. Repeated initialization is locked; cache retained until process exit. Real Unicode-path world initialization now passes.
- Initial viewer probe closed a large WASM response after one byte, causing server ConnectionResetError. Probe now drains the response; final acceptance log has no such error. This was a probe defect, not production server remediation.

## Acceptance boundary

Software release is built and locally verified with isolated runtime, stripped tool PATH, network-blocked checks and actual relocation into Unicode/space-containing path. It has NOT been run on a separate clean Windows installation/VM or exercised for an entire UI game/browser rendering session. Browser assets/geometry, real virtual-world startup, local AI/model inference and actual app boot/menu/shutdown have the explicit evidence above.

No camera recognition accuracy, physical Ethernet/device commissioning, controller fault recovery or loaded arm/gripper/gameplay acceptance was performed. A package cannot supply a missing device driver or make a different robot's teaching/calibration valid. Keep the existing operator/board/motion gates and commission the actual event kit; the earlier KNOWN_ISSUES remain applicable. No automatic enable/reset/motion, no physical probe, no changes to camera/robot calibration.

Historical whole-repository LAST_REVIEWED_HEAD remains unchanged. This is packaging plus scoped regression evidence, not a whole-branch review or merge approval. Old candidate ZIP/staging outputs were moved to ignored build/capsule-cache/retired; use only the dated final ZIP above.

## Final distribution

Source/pipeline and updated README are delivered on branch `final`; portable ZIP and its SHA256 sidecar are release assets under tag `capsule-windows-x64-20261105`, rather than large binaries in Git history. Release URL: https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105.

Pre-delivery gate: all 184 runtime source/asset hashes match the tested ZIP; local ZIP SHA256 matches sidecar; 19 capsule tests rerun PASS, exit 0 (logs/capsule/final-delivery-tests.log); README local links/anchors/fences and staged whitespace checked. Runtime code is unchanged from the 66-test and actual relocated-bundle acceptance above. Release assets must retain the exact size/digest recorded here.
