# Windows capsule implementation
Mode: --fast planning; Standard implementation, user authorized complete capsule without another approval round.
Risk: normal — isolated packaging/launcher; retain hardware policy and motion code.
Status: implemented; local acceptance passed; separate-PC/hardware acceptance unverified

## Decision
App-local official embeddable CPython 3.12 x64 plus vendored dependencies, CPU Torch/ORT. Build on developer PC; release has no pip/npm/setup step. Relative paths and isolated _pth prevent reuse of developer virtualenv/system Python. One START.bat opens existing game menu. Fixed taught hardware profile stays unmodified; no session copied.

## Phases
- [x] Build cached runtime/dependencies, source allowlist, complete models/viewer, licenses and integrity manifest; fail closed on missing assets.
- [x] Isolated launch/preflight, editable non-motion host settings, smoke checks and clear offline operator instructions.
- [x] Tests, actual build/ZIP, relocated isolated verification, code review, document evidence and remaining hardware/second-machine boundary.

## Verification
Use tools/test_fast.ps1 for packaging/startup tests; actual bundle --check and --smoke without host tool PATH. Check release SHA256 and absence of journals/tokens/venvs. No physical operations. Do not commit/push until requested.

## Sources
https://docs.python.org/3.12/using/windows.html#the-embeddable-package
https://docs.python.org/3.12/library/sys_path_init.html#pth-files
https://www.python.org/downloads/release/python-31210/

## Evidence
Final ZIP dated 20261105, 386706814 bytes, SHA256 c5d1a6570d41954ffbeb0dbc0fb7451b275fa943f2bc09fbd1f61606f1120f5e. 66 selected tests, packaged smoke, clean ZIP relocation into Vietnamese/spaces path, actual virtual-world/engine/viewer/main menu and native DLL provenance all PASS. See reports/windows-capsule-20261105/REPORT.md. No commit/push or physical operations.
