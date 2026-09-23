# Test Performance & Parallel Infrastructure Specification

## 1. Machine Hardware Profile
* **Host Operating System:** Windows 11
* **Processor:** Intel Core i5-10300H
* **Physical Cores:** 4
* **Logical Threads:** 8
* **System Memory:** 24 GB RAM
* **Python Environment:** Python 3.11.15, Pytest 9.1.1, Pytest-xdist 3.8.0

---

## 2. Baseline Methodology

Testing on this repository previously suffered from slow developer feedback cycles due to serial execution where CPU utilization remained around 10–15%. 

To maximize test throughput while maintaining deterministic, crash-free test execution:
1. **Thread Caps Enforced:** Numerical libraries (OpenMP, MKL, OpenBLAS, NumExpr) are clamped to 1 compute thread per process (`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`). This prevents $N$ worker processes from each spawning 8 threads and thrashing the CPU with 32–64 competing threads.
2. **Pytest-xdist Worksteal / Loadfile:** Worksteal scheduling distributes tests dynamically across worker processes.
3. **Representative Benchmark Subset:** A 44-test representative suite spanning configuration schemas, motion execution, mock hardware backends, vision filters, PyBullet rigid body dynamics, full 90-cell reachability, and architectural safety contracts was benchmarked across 1, 2, 4, 6, and 8 worker configurations.

---

## 3. Benchmark Results (Representative 44-Test Suite)

| Workers | Status | Wall-Clock Duration | Relative Speedup | Resource Utilization Notes |
| :---: | :---: | :---: | :---: | :--- |
| **1 (Serial)** | PASS | 53.78 s | 1.00x | Baseline unparallelized execution |
| **2** | PASS | 31.54 s | 1.71x | Conservative mode for concurrent agent pairing |
| **4 (Balanced)** | PASS | **20.95 s** | **2.57x** | **Optimal throughput per physical core (4 cores)** |
| **6** | PASS | 22.28 s | 2.41x | Hyperthread contention slightly exceeds gains |
| **8 (Full)** | PASS | 27.05 s | 1.99x | Full 8 logical thread utilization |

*Note: On a 4-core / 8-thread CPU, 4 worker processes (`-Mode Balanced`) achieve the lowest wall-clock latency for small test runs due to physical core mapping without hyperthread context-switching. For large runs with uneven test lengths, 8 workers (`-Mode Full`) keep all logical execution pipelines occupied.*

---

## 4. Full Suite Performance & Slowest Tests

The full unit test regression comprises **441 tests** across **40 test files**.
* **Full Parallel Suite (8 Workers):** **225.56 s (3 min 45 s)**
* In comparison, a single heavy serial test file (`test_phase3_dynamic_board_placement.py`) takes **356.88 s (~6 minutes)** when run alone serially.

### Top 10 Slowest Tests (Profiling Pass: `--durations=30`)
1. `test_recommended_placement_90_cells_pass` (`test_phase3_dynamic_board_placement.py`): **148.96 s** (Solves exhaustive 90-cell trajectory feasibility)
2. `test_validation_state_invariance` (`test_phase3_dynamic_board_placement.py`): **138.69 s**
3. `test_nominal_placement_fails_row0_with_link_pair_and_sample` (`test_phase3_dynamic_board_placement.py`): **133.03 s**
4. `test_g90f_11_sampled_mode_reports_non_exhaustive` (`test_phase3_final_g90_corrective.py`): **26.72 s**
5. `test_representative_trajectories_at_recommended_placement` (`test_phase3_dynamic_board_placement.py`): **25.60 s**
6. `test_90_intersections_reachable_at_board_surface` (`test_fr3_board_reachability.py`): **24.24 s** (Full 90-cell Cartesian IK validation)
7. `test_full_board_routes_validation` (`test_phase3_dynamic_board_placement.py`): **23.96 s**
8. `test_cartesian_3stage_trajectory_fidelity_and_drift` (`test_phase3_final_closure.py`): **21.44 s**
9. `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place` (`test_phase3_final_master.py`): **20.06 s**
10. `test_allowed_grasp_piece_id_guaranteed_cleanup` (`test_phase3_dynamic_board_placement.py`): **19.38 s**

---

## 5. Parallel-Safety Findings & Resolutions

During parallelization audit and benchmarking, two file-access race conditions were identified and surgically corrected:
1. **Temporary Matrix Isolation (`test_occupancy_filter.py`):**
   * *Problem:* Test generated a hardcoded `test_perspective.npy` directly in the source directory `tests/unit/`.
   * *Resolution:* Switched to isolated `tempfile.TemporaryDirectory()`, preventing cross-worker file collisions.
2. **Concurrent URDF Generation (`src/simulation/physics/urdf_resolver.py`):**
   * *Problem:* `get_simulation_ready_fr3_urdf()` blindly rewrote `fairino3_v6_pybullet.urdf` on every call. Multiple worker processes initializing PyBullet collided trying to write and read the locked file simultaneously.
   * *Resolution:* Added an idempotency check (`st_mtime` verification) to return the existing file without disk rewriting, and added atomic temp-file replacement if regeneration is required.
3. **Class-Level Simulator Piece State (`test_phase3_final_master.py`):**
   * *Problem:* `test_c9_retreat_collision` assumed default piece positions without explicitly resetting piece positions after previous tests in the worker.
   * *Resolution:* Added `self.sim.reset_pieces()` at test initialization.

### Base Branch Test Status
The following 3 assertions fail identically in both serial and parallel runs and represent pre-existing logical conditions on `integration/unified-fr3-system`:
* `test_phase3_dynamic_board_placement.py::test_nominal_placement_fails_row0_with_link_pair_and_sample`
* `test_phase3_dynamic_board_placement.py::test_row0_collision_resolution_and_recommended_placement`
* `test_phase3_final_g90_corrective.py::test_g90f_14_critical_routes_explicit`

---

## 6. Authoritative Testing Guidance for AI Agents

### Single Agent Mode (Full Utilization)
```powershell
# Routine full regression (default: 8 workers, worksteal)
.\tools\test_fast.ps1

# Balanced mode (4 workers: optimal latency on 4 physical cores)
.\tools\test_fast.ps1 -Mode Balanced
```

### Targeted Development Mode
```powershell
# Run only affected test files with 2-4 workers
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_phase3b_wiring.py
.\tools\test_fast.ps1 -Workers 4 -Tests tests/unit/test_motion_executor.py,tests/unit/test_motion_resolver.py
```

### Two Concurrent Agents Mode
```powershell
# Essential when two AI agents are working in parallel worktrees
.\tools\test_fast.ps1 -Mode Concurrent
# OR:
.\tools\test_fast.ps1 -Workers 2
```

### Serial Debugging Mode
```powershell
# Single-process run for isolating race conditions
.\tools\test_serial.ps1 -Tests tests/unit/test_piece_drop.py
```
