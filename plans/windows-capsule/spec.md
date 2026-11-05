# Windows portable capsule
Date: 2026-11-05
Status: current need-review integration

## Scope
User explicitly requests a complete capsule copyable to another Windows machine. Keep current game/robot execution and safety gates; add a portable release build and isolated launcher, not another install-on-first-run wrapper.

## P1 stories and acceptance
- Operator extracts ZIP and opens START.bat on Windows 10/11 x64 with a desktop browser; no Python/Node/Git/CUDA install or dependency download at event time.
- Full release contains isolated CPython, CPU vision dependencies, Moonfish, required local models, Three.js/CAD assets and checked source assets. No original session journal, log, environment credential or virtualenv copied.
- Launcher checks release completeness, reports failures with local log, starts existing mode selector. No automatic hardware enable/reset/move; physical capabilities retain application gates.
- Team can rebuild with a developer command, cached downloads and model directory; release records source/dependency/file SHA256 provenance and licenses. Missing required assets fail the build.
- Acceptance here: targeted tests; real packaged interpreter check including YOLO/ONNX, Moonfish, PyBullet and viewer assets with external Python/Node removed from PATH; relocate to a path with spaces/Unicode and rerun offline checks; build ZIP and publish SHA256 locally.

## Boundary
Windows 10/11 x64 desktop, sufficient memory/storage and browser. CPU baseline; no CUDA requirement. Device drivers, robot/camera physical setup, Ethernet and recalibration after moving equipment are hardware commissioning, not solved by bundling software. Fresh second-PC and loaded robot acceptance must be explicitly distinguished from isolated/relocated checks on this PC.

Current mode acceptance: preserve HUMAN_VS_HUMAN_ROBOT host + localhost Black client using packaged Python; actual dialog path retains operator consent and no hardware calls. Publish separate need-review capsule rather than reusing final ZIP.
