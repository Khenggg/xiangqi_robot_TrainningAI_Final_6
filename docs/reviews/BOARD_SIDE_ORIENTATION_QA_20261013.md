# Board-side orientation QA — 2026-10-13

Nominal board rotated180 degrees about its existing center (-23.8,377)mm and unchanged10.5mm surface height. Black logical row0 now lies toward negative robotX; red row9 toward positiveX. Column direction rotates too; semantic color/IDs/FEN are not swapped. Shared scene owns yaw, origin, axis metadata, T_robot_from_board and nominal R1-R4. These points are provisional simulation coordinates, not controller measurements.

Default BoardPlacementState.compute, canonical_cell_to_robot_xyz_m, find_nearest_cell and FixedBoardPoseProvider.from_forward_shift now read scene yaw when no explicit angle is supplied. Explicit0/other yaw and measured physical calibration keep their meaning. Existing default-provider test checks scene instead of fixed0.

Evidence reports/board-side-qa-20261013/: red.log four failures before change, focused2.log30 passes, final.log90 passes (exit0), four Node suite logs (coordinate contract, mesh transform, camera reconciliation, placement integrity), browser.json, baseline files and delta.patch. New tests round-trip every90-cell target for scene180 and37; actual PyBullet32 piece IDs remain at their semantic cells and runtime90 targets follow the transform. Settled XY drift cap0.5mm is a simulation fixture check, not a physical tolerance.

Actual isolated ViewerServer8089 connects to the running main-process WebSocket8765: 16black+16red, yaw180, black mean worldZ0.1563m greater than red -0.1087m (worldZ=-robotX). Overhead QA screenshot shows red above/dark below and robot on right, matching operator image. Arm still uses measured physical joints. Only QA-tab camera was adjusted for inspection.

Broader103-case selection containing expensive90-cell/full-route sweeps was interrupted and is not a passed gate. Final90-case gate excludes that sweep file. Whole-repository regression, full trajectories and physical moves are NOT RUN. Node mesh test first needed Python PATH correction, then passed. Initial browser startup took longer than10s; subsequent live inspection succeeded.

Hard reload the physical raw-arm viewer to see new nominal sides. Restart a virtual backend before using its new scene; a running virtual backend can send its old placement. R4 frame mismatch, missing board contact calibration, unknown taught-pose/contact relation, visual-estimator error and previous model/controller flange discrepancy remain unresolved. No controller teaching points, motion coordinates, enable or IO changed.
