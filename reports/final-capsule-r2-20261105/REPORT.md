# Final capsule r2 — 2026-11-05

User corrected delivery branch to final. Normal merge of need-review55c5fd5 (built from new robot-PvP baseline30649c4) into final774483a. Conflicts resolved to current need-review runtime/tools/test contents, preserving historical status records and unioning feature IDs. No source motion/PvP/session/input/exit logic changed during this merge; independent review verified exact matching source. New README/build-guide branch and download references use final.

## Final artifact

- ZIP: dist/Xiangqi-Capsule-Windows-x64-20261105-r2.zip
- Size: 386748507 bytes (368.8 MiB).
- SHA256: c0616011ef822978d269744516d1f99c0796e76419bb28cdab49374d4c227e15
- Release/tag: https://github.com/Khenggg/xiangqi_robot_TrainningAI_Final_6/releases/tag/capsule-windows-x64-20261105-r2
- START.bat in the extracted root; no event-machine dependency install. CPU runtime/models/engine/viewer/font/native runtime included. All four current modes, including localhost Black client for 2 NGƯỜI + ROBOT.

Payload is the tested current runtime described in reports/need-review-capsule-20261105/REPORT.md, repackaged with final-r2 root/filename. Archive prefix changes and ZIP metadata change the checksum; runtime source is unchanged. Source manifest records build baseline30649c4 and exact payload hashes, not an invented later merge SHA. All187 source/asset hashes match the final worktree. During Git merge, board_renderer and operator guide line endings changed; normalized-content equivalence was verified and exact tested bytes restored before final comparison. No logic adaptation was needed.

## Fresh verification after merge

- Same eight-file project runner selection as the integration report, 2workers:105 PASS (93parallel+12serial), exit0,20.29s; logs/capsule/final-r2-tests.log. Two websockets deprecation warnings.
- ZIP SHA256/CRC verified. Untouched final ZIP extracted into `dist/acceptance/Final - Bàn giao r2/`. Its bundled interpreter with PATH System32-only ran current acceptance_probe.py; all six checks true, exit0, logs/capsule/final-r2-acceptance.log.
- Actual YOLO CPU inference and both ONNX sessions; local Moonfish legal b0c2; real32-piece virtual world; loopback viewer HTML/Three.js/WASM; actual Black child subprocess ClientApp/room handshake/state/render/request; actual main menu + real exit modal. Only probe OS-exit helper replaced with SystemExit for recording; production exit cleanup not claimed. Dedicated existing subprocess exit tests also passed.
- Runtime/source187 hashes, launcher and bundled READ_ME_FIRST checked against ZIP. No inherited workstation journal/log/venv/env. README first heading directly downloads this ZIP; source clone/pull/menu/four-mode descriptions match final. Independent review found no remaining merge/integration blocker.

## Distribution and boundaries

Source + synchronized README pushed on final with user identity hiimthinh123 <hiimthinh123@gmail.com>. Versioned ZIP and SHA256 are GitHub Release assets, not Git blobs. Earlier unpublished need-review release draft was stopped/deleted after user correction; original final release remains separate and unchanged. The already-pushed need-review source commit is retained without force-rewriting history.

No physical camera/controller/robot/gripper operations. Clean second-PC/full UI game/browser and physical event-kit acceptance remain unverified; fixed hardware profile/calibration is kit-specific. No full-suite/whole-repo or merge-safety certification beyond the scoped integration. Existing broader regression gaps and known hardware issues remain. Historical LAST_REVIEWED_HEAD unchanged.
