# Player vs Robot: isolated vsc-v3 runtime

Only `HUMAN_VS_ROBOT` selects `src/modes/vsc_v3_session.py`. Its private donor stack is recorded from `feat/vsc-v3@2caa9ac6d25fe430632ec503cc3f973bf36fcb2c` in `src/modes/vsc_v3/provenance.json`. Human input, board stability, AI turns, foot-point selection, capture retry and local state updates use this stack. Other modes retain their existing session factory, journal, game state and executor.

The private adapter uses the current driver/SDK, fixed teaching profile, timing, rotations, geometry and physical validation. The user-requested wiring reversal restores DO1-open/DO0-close; pulse durations remain unchanged. It does not rewrite global config or the shared driver. Startup enables using that driver; it adds no startup HOME/gripper commands. Donor logical-cell fallback is local to this mode; shared pick policies are unchanged.

The outer application still owns the home menu, window scaling and exit confirmation. The private session owns difficulty, game input and AI. MODE SELECT / Escape returns to the outer menu when its workers are idle. Failed startup/retirement keeps the resource owner and requires F2 to retry closure before any new mode can open resources. Camera reads must stop before release; SDK closure must succeed before the owner is discarded.

The 3D showcase is an observational adapter, not part of donor decisions. Physical display borrows the existing SDK connection for arm telemetry and observes gripper commands; it never opens another robot connection. Committed board positions, including reset/rollback/scans, are projected with stable piece identities. Simulation replays AI motion after the donor commits. Projection errors cannot turn hardware failure into success, reject a successful move, or commit a FEN. Board-only and --no-viewer do not open the showcase.

This preserves the vsc-v3 in-memory gameplay model; it does not add the shared runtime's durable journal/typed transaction semantics to the donor. Hardware absence never counts as successful physical motion. Actual camera/FR3 acceptance and visual inspection of an entire 3D game remain required; automated checks use mocked physical IO.

The complete GPU-light fixed ZIP includes this migration, the explicit R1–R4 fixed-profile constructor argument and DO1-open/DO0-close configuration. The older 20261109 unpatched ZIP needs its separate patches; the new complete ZIP does not.
