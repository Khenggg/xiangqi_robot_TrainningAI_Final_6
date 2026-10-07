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
