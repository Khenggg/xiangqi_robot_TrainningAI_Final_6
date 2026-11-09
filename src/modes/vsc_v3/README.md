# Player vs Robot: isolated vsc-v3 logic

Donor: feat/vsc-v3@2caa9ac. provenance.json records original donor source hashes. Imports are rewritten into this package; other game modes keep their existing modules. No SDK code or donor pin configuration is restored.

Call config.configure(current_config, selected_mode, app_root, camera_recalibration=False) before constructing the scoped state/manager/input classes. This selects donor game, turn, camera, AI and picking logic with a mode-private config. Current measured robot geometry, fixed teaching profile, frame and gripper wiring are copied into that private config; current global config is never replaced.

Physical adapter subclasses the current FR5Robot. Its physical primitives and preflight checks remain current. The scoped donor move sequence restores PvP foot-point/logical fallback and donor capture ordering, while typed hardware failures are converted to donor exceptions. It does not reconnect during a move. Startup uses current fixed teaching points and explicit activation, with no startup HOME or gripper command. Cleanup delegates current deactivation.

This donor stack does not own a viewer, network relay or application-wide session lifecycle; the VscV3Session facade owns those connections and optional view-only showcase adapters.
