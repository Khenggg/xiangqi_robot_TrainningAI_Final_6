# xiangqi.zip — 2026-11-09

Branch: fix/fix-capsule. Runtime source baseline: 1faf176. Packaging edits are in the current working tree.

Artifact: dist/xiangqi.zip (385,778,543 bytes).
SHA256: 5faab516e8466632b5d9fae6171b2e743b56da5d5a318d1745f34da13365e05a

start.bat invokes start.run for offline first-run installation of runtime.zip; INSTALL.bat provides setup-only entry. Later launches use app-local Python. No settings.json or config/environment overrides; exact project CLI including --help forwarded. app/config.py remains editable during normal launch; full audit compares it to original hash. Bundled dependencies are CPU-only, not CUDA.

Verification: 24 packaging tests pass; combined earlier package/startup run 52 pass before adding three CLI tests. Actual PS5 bootstrap traversal rejection, repeat-install and Unicode-path setup verified. Final ZIP CRC checked, extracted into Unicode/space path without expanded runtime; real start.bat -Setup installs and repeat setup passes. Own packaged interpreter passes models, engine, real 32-piece virtual world, local viewer HTML/JS/WASM, actual Black subprocess room/GUI/request, main menu/exit acceptance. All 188 runtime source/asset hashes match the manifest. Actual start.bat --help forwards to project CLI. Review: no blocker after CLI forwarding correction.

No physical camera/controller or motion acceptance; no clean second Windows machine test. No changes to project runtime source/main/config made by packaging. ZIP has not been published as a GitHub release.

Superseded by the GPU-preferred lightweight artifact documented in reports/xiangqi-gpu-light-20261109/REPORT.md.
