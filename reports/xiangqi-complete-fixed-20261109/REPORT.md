# Complete fixed xiangqi.zip — 2026-11-09

Release: xiangqi-gpu-light-20261109-fixed. Artifact dist/gpu-light-fixed/xiangqi.zip, 286,793,962 bytes.
SHA256: 906504f2514a34c0c92324bf6bec8e7eafb2cd0464f7099896b05d6b0d1ef41b

Integrated source at 3f7c78f includes c7d9269 R1-R4 fixed-profile constructor fix and DO1-open/DO0-close. No separate patch execution needed. Pulse timings unchanged. GPU-first lightweight installation, scoped vsc-v3 HVR and other-mode logic preserved.

Build reuses the checksum-verified base runtime.zip from the accepted GPU-light release, refreshes all 236 tracked source/asset files and packaging entries, and regenerates manifest/ZIP/SHA256. No expanded runtime, CUDA wheels or device sessions in ZIP.

71 focused tests pass. Whole ZIP CRC and all 236 source hashes verified. Actual packaged HVR constructor selects fixed profile, uses DO1/DO0, and loads real user0 profile with an SDK object that raises on any access; no physical IO. Reused installed runtime only after proving compressed base runtime hash identical. Packaged inference passes GTX1650/CUDA for YOLO and both ONNX models; real virtual world32 pieces, local viewer HTML/JS/WASM, Black subprocess handshake/state/request and main menu/exit pass. No new fresh ML install was required for this source-only integration.

Physical camera/FR3 operation and a second clean-PC acceptance remain unverified. New full ZIP supersedes old full ZIP + two patches; old release assets retained for existing installations.
