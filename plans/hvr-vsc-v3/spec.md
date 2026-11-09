# Isolated vsc-v3 Player vs Robot

Confirmed: HUMAN_VS_ROBOT uses feat/vsc-v3@2caa9ac game/input/AI/vision logic; retain present physical configuration (DO0 open, DO1 close, timings, fixed profile), retain read-only 3D showcase. No changes to other modes, global config, shared SDK or shared game logic. GPU release build waits until this change is verified.

Acceptance: only HVR selects the scoped donor runtime. Other three modes retain current factories/state/control. Donor modules use scoped imports/config; never replace global config or shared sys.modules. Models and camera calibration use current resource directory. Showcase cannot command robot or commit camera results. Cleanup waits for donor workers before SDK/camera closure. No hardware actuation in automated verification.

Known compatibility boundary: vsc-v3 lacks digital twin, journal and current virtual executor; the bridge is an explicit display-only addition, not part of donor gameplay decisions. Preserve measured physical arm and committed-board projection; verify virtual showcase behavior separately before claiming parity.
