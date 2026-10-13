# Camera GPU correction evidence — 2026-10-13

- Exact scoped primary baseline: baseline-hashes.json and baseline/.
- Four new lifecycle tests fail against baseline (red2.log), then pass with fix.
- 89 scoped subsystem passes (regression.log), exit0.
- Actual GTX1650Ti CUDA tensor/ONNX pose+layout/YOLO inference verified.
- Same-image warm GPU47-78ms, 32detections/32names (gpu-inference.json).
- Live camera2/DSHOW1280x720:15s,227/227 samples after5s ready with32names;
  147capture timestamps,39inference timestamps; clean shutdown (live-camera.json).
- SETUP_GPU.bat executed against installed environment, exit0; CUDA pose run.
- Python compilation and git diff --check passed for scoped changes.
- Full regression and guarded delivery results will be appended after completion.
- First two test runner attempts lacked basetemp parent; no test acceptance claimed.
- No physical robot connection/commands or calibration artifact updates in probes.

## Final gates and limits

123scoped passes (final-scoped.log), exit0. Full857passed/12failed, no serial phase because runner stopped at failure. All12failed with baseline sources too (baseline-failures.log). Additional one-line UI accent correction resolves3startup findings;9baseline findings remain (after-ui-failures.log). Do not claim whole-repo/full acceptance.

Scoped files delivered to primary with exact SHA256 parity (delivery-manifest.json). Existing calibration/camera-source files unchanged. No reset/commit/push or physical robot actuation.
