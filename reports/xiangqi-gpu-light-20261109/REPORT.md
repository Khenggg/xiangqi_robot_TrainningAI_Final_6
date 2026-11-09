# xiangqi.zip GPU-preferred lightweight — 2026-11-09

Branch: fix/fix-capsule, working tree includes scoped vsc-v3 HVR migration and packaging edits.
Final ZIP: dist/xiangqi.zip, 286,793,685 bytes.
SHA256: ca800881ffce38b7990075e68e0224cd9e5c66f0eeae065827ee8e7b758881a1

ML libraries are not bundled in runtime.zip. First start installs pinned PyTorch CUDA 12.4/torchvision and ONNX Runtime GPU 1.20.2 into app-local runtime when NVIDIA is detected; otherwise installs CPU variants. First setup needs Internet and several GB disk. Later start.bat runs normally. System Python/config/game mode are not overridden. Optional verified wheelhouse used for this acceptance (official Torch SHA256, local downloaded ORT wheel).

24 packaging + 3 installer tests pass; 93 HVR/other-mode regression tests passed in preceding migration verification; GPU device selection tests also pass. Final source hashes: 236 match extracted bundle. The final ZIP CRC and checksum pass; contains no expanded runtime directory, contains the new scoped HVR source.

Actual PS5/batch first installation in Unicode/space path passed and confirmed Torch2.5.1+cu124/CUDA12.4 and ORT1.20.2. Inference succeeded on NVIDIA GTX1650: both ONNX models CUDAExecutionProvider and YOLO CUDA. Own packaged runtime passed Moonfish legal move, actual 32-piece virtual world, loopback viewer HTML/JS/WASM, packaged Black subprocess state/GUI/request, actual main menu/exit. No physical camera/FR3 accessed.

Initial installation had nonfatal pip log encoding errors. Final installer adds -X utf8 to both setup and pip; unit tests and actual packaged pip command in Unicode path pass. Updated bootstrap/installer/docs/manifest were synchronized and ZIP rebuilt; final repeated start.bat -Setup and actual --help passed without reinstalling. No claim of a second fresh full ML install after the encoding-only correction.

No clean second-PC, full UI-game/browser visual or physical hardware acceptance. This ZIP supersedes the earlier CPU artifact. Source is committed alongside this report; no GitHub release uploaded.
