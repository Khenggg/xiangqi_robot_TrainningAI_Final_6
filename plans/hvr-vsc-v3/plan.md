# HVR vsc-v3 isolation

Mode: scoped implementation, independent worker ownership and review
Risk: high-risk — physical execution path; retain current calibrated hardware settings.

- [x] Vendor donor stack with isolated imports/config and provenance.
- [x] Add HVR facade and observational 3D bridge.
- [x] Route only HVR at launcher boundary and dispose before switching modes.
- [x] Verify donor turn/capture/retry plus other-mode routing and existing PvP/selfplay regressions. Review no cross-mode changes.

Prior packaging edits remain in the working tree; no new GPU build or release during this migration.

Verification 2026-11-09: 93 tests passed (88 parallel + 5 serial), covering donor namespace/config, turn/AI commits, logical fallback/captures, actual virtual board projection, retained startup/retirement, SDK/camera closure and other-mode regressions. After portable font adjustment, 23 focused tests passed again. No shared runtime files changed except explicit mode dispatch in main.py; new code is under src/modes. No physical hardware acceptance or new ZIP yet.

Review findings resolved: fatal SystemExit converted to normal errors; cleanup failures retain owner and block new sessions; active retirement failure freezes gameplay and requires F2; readers must stop before capture release, then current SDK closes before ownership is cleared.
