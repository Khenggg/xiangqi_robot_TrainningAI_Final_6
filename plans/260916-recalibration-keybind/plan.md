# Re-run camera auto-calibration with a keybind

Mode: fast
Risk: normal — this is a multi-file, user-facing camera lifecycle change that temporarily pauses a live capture pipeline and overwrites the persisted perspective matrix.

## Confirmed current behavior

- On a non-`DRY_RUN` startup, `HardwareManager._init_camera()` opens the camera and calls `run_calibration_flow(...)` before it creates `CameraMonitor`.
- `run_calibration_flow(...)` first uses `models/board_pose.pt`; it accepts the result only when every keypoint meets the `0.65` threshold and the four-corner geometry sanity check passes. Otherwise it opens the existing four-click manual calibration fallback.
- A successful auto or manual calibration writes `perspective.npy`. `CameraMonitor` loads this matrix once at construction; `SnapshotDetector` reads it from disk for each occupancy operation.
- During gameplay, `CameraMonitor` is the single owner of `cv2.VideoCapture`. Its `stop()` method currently releases the camera, so it cannot be reused as-is for an in-session calibration.

## Proposed user-facing behavior

- Add `V` as the recalibration key. It is handled only while the game accepts human-turn keyboard commands (not in `DRY_RUN`, after game over, or during the AI turn), matching the existing safety gate for `Z` and `SPACE`.
- Pressing `V` displays a status message and reruns the same `run_calibration_flow(...)` used at startup: YOLO-Pose is tried first, and low confidence, invalid geometry, a missing pose model, or inference failure goes to the unchanged four-click fallback.
- The camera monitor pauses before calibration so no background thread accesses the same `VideoCapture`. It resumes afterward whether the flow succeeds, is cancelled, or raises, then reloads the in-memory perspective matrix and clears the YOLO move baseline. A fresh baseline is captured only after a successfully saved/reloaded calibration matrix.
- If the user exits manual calibration (`Q`) or calibration cannot produce a matrix, retain the previously active calibration/baseline rather than treating the existing on-disk file as proof of a new successful calibration. Report the cancellation/failure without crashing or leaving the monitor paused.

## Implementation phases

### Phase 1 — make the live camera monitor pausable

**File:** `src/vision/camera_monitor.py`

1. Refactor the monitor lifecycle into a reusable temporary-pause path and final shutdown path. The temporary path must signal and join the capture/detection threads but must not release `cap`; final application cleanup retains the current release-and-window-destruction behavior.
2. Ensure resume creates fresh worker threads, clears the stop event, and continues using the same already-open `cv2.VideoCapture`.
3. Keep camera reads serialized by the existing `_cam_lock`; calibration will only begin after workers have joined. Preserve `reload_perspective()` for refreshing `_M` and `_inv_M` after a new matrix is written.

### Phase 2 — provide one hardware-level recalibration transaction

**File:** `src/hardware/hardware_manager.py`

1. Add a public `recalibrate_camera()` method that is a no-op with a useful result/status for unavailable camera/model/monitor dependencies.
2. Build the pose model path exactly as startup does and call the same `run_calibration_flow(self.cap, self.perspective_path, pose_model_path=...)` while the monitor is paused.
3. Use `try`/`finally` so the monitor always resumes. On a returned new matrix, reload its perspective, clear any stale YOLO baseline, and capture a new baseline after the monitor has resumed and has produced a fresh frame.
4. Define success from `run_calibration_flow` returning a newly accepted matrix, not merely from `perspective.npy` existing (the manual dialog can load an old matrix and be cancelled). Do not modify the game board, FEN, robot calibration, or AI state.

### Phase 3 — connect the Pygame command and document it

**Files:** `src/ui/input_handler.py`, `src/ui/board_renderer.py`, `README.md`

1. Handle `pygame.K_v` before the existing move-detection action; set an in-app “calibrating” status, call the hardware transaction synchronously (the manual four-corner dialog is intentionally modal), and show a success, cancellation, or failure status based on its result.
2. Add `V` to the visible keyboard hint without hiding the existing `SPACE` instruction.
3. Update the documented keyboard controls and replace the outdated statement that no mid-game `V` calibration key exists.

### Phase 4 — add regression coverage and verify

**Files:** `tests/test_recalibration_keybind.py`, `src/vision/camera_monitor.py`, `src/hardware/hardware_manager.py`, `src/ui/input_handler.py`

1. Unit-test the hardware transaction with mocked monitor/calibration flow: it pauses before calling the flow, resumes even when it raises/fails, reloads/clears/recaptures only on success, and leaves the old baseline intact on cancellation/failure.
2. Unit-test the input handler dispatches `V` to hardware and that existing `SPACE`/`Z` behavior and the existing turn/game-over guard remain unchanged.
3. If small lifecycle seams are needed to make these tests hardware-free, add only dependency injection or narrowly scoped helpers; do not require a camera, YOLO weights, robot, or OpenCV windows in tests.

## Safety and compatibility notes

- `perspective.npy` is a physical calibration artifact. The implementation must only replace it through the established auto/manual flow, and must not delete it on an unsuccessful attempt.
- The manual fallback owns the UI until the operator saves (`S`) or cancels (`Q`). This is intentional; Pygame rendering pauses during that interaction just as it does for other blocking hardware actions.
- The `V` command is deliberately unavailable in `DRY_RUN`, during AI movement/thinking, and after the game ends, avoiding a camera/robot-state transition in unsafe gameplay phases.
- Camera cleanup must still release the device exactly once at application exit; a temporary recalibration pause must not do so.

## Verification commands

```powershell
py -3.10 -m py_compile src/vision/camera_monitor.py src/hardware/hardware_manager.py src/ui/input_handler.py src/ui/board_renderer.py
py -3.10 -m unittest tests/test_recalibration_keybind.py
py -3.10 tests/test_occupancy_filter.py
py -3.10 -m unittest tests/test_visual_pick_estimator.py
```

## Manual acceptance check

1. Start the non-`DRY_RUN` app and confirm startup still attempts pose calibration and opens the four-click dialog when confidence/geometry fails.
2. On the human turn, press `V`; confirm the camera monitor pauses, the same auto-calibration flow appears, and a successful calibration refreshes the overlay/grid and baseline.
3. Repeat with a forced low-confidence/missing pose model and confirm the four-click fallback appears.
4. In the manual dialog press `Q`; confirm the camera monitor resumes, the app stays playable, and the prior grid/baseline remains usable.
5. Confirm `V` does nothing while it is the AI turn or the game is over, and that `SPACE` and `Z` still work as before.

## Session Notes
<!-- Updated by cook automatically — do not edit manually -->

**Last active:** 2026-09-16
**Phase in progress:** complete
**Status:** Implemented and verified; focused code review approved the final change.

### Decisions made this session
- Reuse the existing opened camera by pausing worker threads; do not reinitialize or release the capture device during recalibration.
- Wait for both workers to exit before calibration starts, preventing concurrent `VideoCapture` reads.
- Restore the previous perspective file, monitor matrix, and visual-pick estimator if any calibration handoff step fails.

### Next immediate action
Manual acceptance check with the physical camera and board.
