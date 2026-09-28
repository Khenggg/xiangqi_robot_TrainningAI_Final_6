# FR3 gripper, board, and piece collision review — 2026-09-26

## Scope and physical contract

This review covers the dirty simulation worktree on `integration/unified-fr3-system` at HEAD `fab750a918c1457ae14bfda900572fb16f846e26`. Earlier local changes were preserved. No physical FR3 motion was authorized or run.

Frames and dimensions in the active configuration:

| Quantity | Frame and meaning | Active value |
| --- | --- | ---: |
| Flange to TCP | `wrist3_link` to fingertip midpoint, along +Z_tool | 168.3 mm |
| TCP to grasp center | tool frame; current proxy contract | 0 mm |
| Jaw axial span | TCP back toward flange | 35 mm |
| Palm axial span | behind jaws toward flange | 133.3 mm |
| Board surface | robot base +Z | 10.5 mm nominal |
| Piece height | cylinder axial height | 9.43 mm |
| Gripper or carried piece board margin | PyBullet closest-point distance | at least 0.5 mm before release |

Thus targeting a piece center places the fingertip TCP 4.715 mm above the board. A carried piece centered at that TCP contacts the board when lowered to the same pose. Placement now releases from 1 mm higher and lets the piece settle onto the board. Piece-to-board contact **after release** is intentional; penetration before release is rejected.

## Assessment of the five clues

1. **18.3 mm disagreement — confirmed.** The profile had `MEASURED_PHYSICAL` and 168.3 mm while the geometry enum rejected that status; a blanket exception handler silently substituted 150 mm. The active scene already used 168.3 mm. Loading now rejects invalid or disagreeing geometry, and backend/world use the canonical transform. The profile's provenance label is a configuration claim, not evidence of a traceable calibration certificate.
2. **Grasp center versus fingertip — the historical 12 mm claim does not describe this worktree.** The active gripper profile has zero TCP-to-grasp-center offset. The live 35 mm jaw and 133.3 mm palm proxy geometry is continuous from tip to flange, but its physical width and shape remain provisional. Nonzero grasp-center offsets now fail closed until runtime target conversion is implemented.
3. **Low joint-space transit — a real planning risk, but the quoted >10 mm sag is not established for the active scene.** The current runtime performs vertical Cartesian lift, horizontal Cartesian transit, and vertical landing, with collision checks on samples and subdivisions. Some preposition/retreat and failed transit paths still use the existing reactive 65 mm joint-lift recovery; a fully preplanned corridor is outstanding.
4. **Historical `tool_bridge` — valid missing-envelope diagnosis, unsuitable dimensions.** The branch's full-width bridge caused neighbor-piece false positives near landing. The active proxy covers the axial length with narrower jaws and a palm. It must be checked against measured tool geometry before physical sign-off; no branch was merged.
5. **Yaw 90° seeds with yaw 0° scene — confirmed mismatch.** The dataset records yaw 90°, 150 mm tool, and 25 mm shift and is marked `STALE/UNVALIDATED`. Runtime now ignores it. Active endpoint IK is computed against yaw 0° geometry. Regenerating the dataset requires an updated generator and validated calibration, so it was not regenerated from stale assumptions.

## Corrections in this worktree

- Canonical tool loader validates length, axis, status, and orientation; simulation backend and world reject scene disagreements. Mock physical backend uses the same length for its dry-run flange cache.
- Runtime preserves the actual IK jaw orientation through pick hover and descent. Board placement uses an immutable nominal board surface so repeated adjustments do not compound Z offsets.
- Collision guard includes out-of-bounds piece bodies if physically near the robot. It also moves the attached piece to each candidate pose for board and neighbor checks, then restores the runtime pose. The intentional release target is 1 mm above the board.
- Tests that treated historical 90°/150 mm joints as current were changed to use active geometry. Master fixtures were isolated per test and adjusted to actual active board poses.

## Verification and limits

The final command and counts are recorded in `CURRENT_STATE.md`. Focused virtual tests cover malformed profiles, scene mismatches, 90 active grasp cells, sampled Cartesian lift/transit, payload-board and payload-neighbor rejections, and four complete corner-to-center pick/place/retreat routes. The guard applies 0.5 mm board clearance to gripper and attached payload during motion. No collision was reported on those four successful routes.

This is **simulation evidence for the sampled routes**, not proof that all 8010 ordered cell routes are safe or that the physical robot has 0 collisions. The 168.3 mm tool length, tool envelope, robot-to-board transform, controller motion, payload behavior, and emergency recovery need traceable physical verification before actuation. The historical reactive recovery planner and stale dataset remain open in `KNOWN_ISSUES.md`.
