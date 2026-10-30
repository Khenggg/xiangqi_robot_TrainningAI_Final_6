# Physical rollback removed

The rollback feature has been removed, including the earlier logical undo.
Z has no action; no reversal motion, rollback board scan, journal load or
rollback recovery prompt runs during gameplay or startup. Existing rollback
journal files are ignored. Historical design plans remain under
`plans/latest-cycle-physical-rollback/` for reference only.

The feature originated in `01a8c5e`, was revised in merge `63f0257`, and received
rollback-specific fixes in `3b2e02b` and `8e56b88`. These commits also contain
unrelated work, so the removal preserves the current PvP picking, Windows setup,
robot communication/motion safeguards, engine error handling and durable remote
FEN synchronization.

Win conditions remain: a side with no legal moves loses (including stalemate),
verified moves publish their final FEN before the remote result, resignation has
its own reason, and engine failures do not imply a win.
