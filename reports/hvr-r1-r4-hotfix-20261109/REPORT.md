# HVR fixed-profile constructor hotfix — 2026-11-09

Root cause: scoped HardwareManager constructed FR5Robot() without teaching_points_path. The current physical driver explicitly selects fixed calibration only when that argument is supplied, so HVR inadvertently queried controller points and mixed user1/user0 normalization, failing on firmware without by-ID WObj access.

Fix passes configured IP, dry-run and resolved fixed profile path, matching the shared manager contract. Error hint identifies robot R1-R4/frame failures before generic camera-calibration wording. No robot teaching data, hardware profile, GPU dependencies or gameplay rules modified.

Verification: 35 HVR namespace/session/lifecycle/launcher tests passed. Regression uses the actual constructor and loads the real fixed profile with a mocked SDK, asserting zero GetRobotTeachingPoint, GetActualWObjNum or GetWObjCoordWithID calls. No physical hardware acceptance.

Patch artifact: dist/xiangqi-r1-r4-fix.zip for the previously published xiangqi-gpu-light-20261109 ZIP. It contains app/main.py, app/src/modes/vsc_v3/hardware/hardware_manager.py, updated integrity manifest and instructions. No config/calibration/runtime/session overwrite. Existing source installations pull fix/fix-capsule; existing capsule installations apply the patch then start.bat without ML reinstallation. Original full ZIP is unchanged and requires this patch.
