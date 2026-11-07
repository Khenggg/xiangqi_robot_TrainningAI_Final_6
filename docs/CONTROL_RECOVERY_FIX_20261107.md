# Control recovery patch — 2026-11-07

Base: `final` at `9b4c515241834241e85974799ddcf0189af54af6`. Candidate branch: `fix/control-recovery-20261107`.

## User-visible changes

| Trigger | Previous behavior | Candidate behavior |
|---|---|---|
| Pre-pick retry pending → F2 → V / Y / Continue | Home transition could be trapped by the retry route. | Home uses the same closing-session guard as reset/surrender. V and Continue reconcile pending state after stop proof; Y cannot replay the move while closing. |
| Pending manual test → home/reset/surrender → V | Manual-test pending was not selected for closing reconciliation. | Dispatches to existing manual-test reconciliation; stop/camera checks remain required. |
| Self-play FAULTED → F12 / visible clear-error button | Main whitelist omitted F12; retained visual retry could also swallow its mouse action. | Keyboard and visible button reach the existing guarded recovery handler. |
| Self-play recovery → visible Continue / scan button | Main hit testing used an obsolete fixed rectangle. | Uses the renderer's actual action and Continue rectangles; hidden game-over actions are excluded. |
| Self-play → F8 → F6 | Handbook suggested F6 could restart directly. | Code semantics preserved and documented: resolve pending → NEW GAME → prepare/verify board and physical permission if applicable → F6. |

No trajectory, calibration, controller stop proof, camera acceptance or physical-enable policy is relaxed. Device endpoints in the new tests are inert mocks. No physical controller/camera was operated.

## Verification

| Check | Result | Exit |
|---|---|---|
| Same 43 new control/dispatch cases on base | 29 PASS, 14 FAIL | 1 |
| Same 43 cases on candidate | 43 PASS | 0 |
| 30-file related subsystem selection | 325 PASS | 0 |
| F8 end/new-game/F6 contract, added after subsystem run | 1 PASS | 0 |
| Explicit serial exit/robot-PvP UI selection | 11 PASS, 1 deselected | 0 |
| Old selective-integration fixtures, without actual-PyBullet case | 18 PASS; included in subsystem count | 0 |

The subsystem, added F8 case and serial selection contain **337 unique passing cases**. Targeted/fixture reruns are not added again. The 43-case selection combines real GameState/InputHandler recovery tests with event-loop AST dispatch tests using real pygame keys and renderer layouts; they are not Windows end-to-end acceptance. Separate existing startup tests exercise the mocked entrypoint.

Independent review found the retained-retry mouse F12 guard and hidden game-over regions; both were corrected and covered. Final scoped review found no blocking finding and independently ran the 43 cases successfully.

Environment: Linux, Python 3.12.14, pytest 8.4.2, pytest-xdist 3.8.0, pygame 2.6.1, numpy 1.26.4, OpenCV-headless 4.10.0.84, ONNX Runtime 1.20.1. SDL video/audio dummy; VIRTUAL/DRY_RUN; numerical thread caps all 1. PowerShell/pwsh was unavailable, so Python pytest commands used the same parallel/serial split, worksteal scheduler, markers and thread caps as the repository runners. No new project dependency was added.

## Reproduce scoped checks

Run from repository root in the development environment. Windows users can use `tools/test_fast.ps1 -Workers 2 -Tests ...` for parallel selections and `tools/test_fast.ps1 -SerialOnly -Tests ...` for explicitly serial selections.

```sh
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ROBOT_BACKEND=VIRTUAL DRY_RUN=1 PYTHONPATH=.
python -m pytest tests/unit/test_recovery_control_sequences.py tests/unit/test_selfplay_recovery_dispatch.py -n 2 --dist=worksteal -q --tb=short
python -m pytest tests/unit/test_self_play_merge_contract.py::test_f8_ends_selfplay_and_requires_new_game_before_f6_restart -n 2 --dist=worksteal -q --tb=short
python -m pytest tests/unit/test_exit_confirmation.py tests/unit/test_robot_pvp_main_ui.py -m 'not slow and serial and not hardware' -q --tb=short
```

The exact 30-file subsystem selection and normalized executed case results are retained in [test evidence](../reports/control-recovery-20261107/test-results.json). The subsystem excludes `actual_pybullet` and `unknown_board_does_not_prevent_readonly_arm_telemetry` because this environment lacks PyBullet. It uses `-m 'not slow and not serial and not hardware' -n 2 --dist=worksteal`.

Static documentation checks: 60 local file/explicit-anchor links and balanced code fences PASS; `git diff --check` PASS.

## Remaining acceptance boundary

The full parallel gate was also attempted with `python -m pytest tests/unit -m 'not slow and not serial and not hardware' -n 2 --dist=worksteal -q --tb=short`. It is **FAIL**, not a green whole-suite result. Candidate: **807 PASS, 27 FAIL, 38 ERROR**, exit 1. Base: **753 PASS, 37 FAIL, 38 ERROR**, exit 1. All 65 candidate failure/error IDs also occur on base; no candidate-only failure/error ID was observed in these runs. The two additional baseline viewer failures come from its missing node_modules; eight other baseline failures are the outdated selective-integration fixtures corrected here. These are not full-suite-green results.

Remaining failures include missing PyBullet (including collection/setup errors), unavailable viewer OCCT assets, camera fixture/contracts, telemetry contracts and an existing game/twin synchronization assertion. The last one warrants a separate investigation before claiming reliable full-system operation. No runtime fix for those other subsystems is included. Full serial phase was not advanced after the full parallel phase failed; the scoped 11 serial cases above ran separately.

Real camera, clean second Windows PC, physical FR3/controller/gripper and complete game acceptance: **NOT RUN**. GPU/recognition-staleness investigation is separate and is not repaired by this control patch. The existing Windows release ZIP has **not** been rebuilt. Merge/release and physical acceptance remain separate follow-up work; historical `LAST_REVIEWED_HEAD` is unchanged.
