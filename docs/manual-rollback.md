# Manual rollback

After a normal player move and a verified AI reply, press **Z** or click
**ROLLBACK**. Red circles mark the player's moved piece and return square;
blue circles mark the AI piece and return square. Return captured pieces to
their highlighted squares too. Overlapping circles use different radii.

Move all pieces by hand. The arm and gripper receive no rollback commands.
The client keeps the camera live and automatically resumes the player's turn
only after three fresh complete identity matches spanning at least one second,
with confidence above 0.7 in every cell. The measured YOLO baseline is saved from that same verified frame. YOLO may
miss pieces; its occupancy need not equal the full-board recognizer because
normal fallback compares measured YOLO snapshots against each other. Wrong/missing pieces, uncertainty,
camera failure or baseline failure leave play paused for further correction.

This undoes the latest completed pair only. It restores FEN, move log, captures
and counters, and sends the restored FEN to the current spectator room once.
There is no redo, cancellation, restart recovery or journal. Rollback is disabled
during thinking/motion, physical faults, test/emergency mode, and after game over.
Finish restoring the highlighted position to resume. New games and deliberate
operator corrections discard old eligibility. A new accepted player move
replaces the previous saved pair. The recognizer and calibrated camera are
required; mouse-only dry runs cannot bypass camera verification.

Offline tests use fake camera, baseline and provider interfaces. Physical camera
recognition and circle alignment still need validation on the actual board.
