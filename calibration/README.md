# Workstation camera profile

`camera_intrinsics.json` is the accepted camera-0 optical profile, 640x480,
checkerboard square 27.3333333 mm, 20 views, RMS 0.818720151 px.
`intrinsic_samples_camera0.npz` stores the checkerboard observations used for
calibration. These files contain camera geometry, not robot teaching points.

Reuse only with the same physical camera, image mode, focus and zoom.
Camera indices can change on another PC; verify the intended camera before
running. A different camera needs its own checkerboard calibration.

RUN recalibrates the board on startup and creates local `perspective.npy`.
Robot teaching points are loaded from the connected controller.

`feat/player-vs-robot` defaults to PvP foot-point picking
(`VISUAL_PVP_PICK_ENABLED = True`), which uses the board homography rather than
this optical profile. SETUP prepares dependencies and verifies active assets;
it never opens a camera, guesses a new calibration, changes robot offsets, or
overwrites a profile. A new PC with a different camera needs its own measured
optical profile when selecting a mode that uses intrinsics.

After SETUP, close RUN and double-click `CALIBRATE_CAMERA_INTRINSICS.bat` to
measure another camera. It asks for the measured printed checkerboard square
side in mm when `--square-mm` is omitted. All calibration/measurement launchers
use the same project `.venv312` as RUN. The intrinsics tool backs up an existing
profile before saving a replacement; cancellation preserves the old profile.
