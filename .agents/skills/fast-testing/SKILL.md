---
name: fast-testing
description: Authoritative workflow and rules for running fast, parallelized pytest regression and targeted unit tests on Xiangqi Robot.
---

# Fast Testing Skill — Parallel Pytest & Subsystem Testing

This skill defines the authoritative testing procedures for AI agents developing on the Xiangqi Robot repository.

## Machine Hardware Baseline
* **CPU:** Intel Core i5-10300H (4 Physical Cores, 8 Logical Threads)
* **RAM:** 24 GB
* **OS:** Windows 11

---

## 1. Core Testing Rules

1. **NEVER run bare full serial pytest** (`pytest tests/unit -m "not slow" -q`) for routine development verification. It underutilizes the CPU and wastes turnaround time.
2. **NEVER execute physical hardware tests in parallel or without authorization.** All scripts in `tools/hardware_tests/` are excluded from unit discovery.
3. **NEVER modify production robot code to force tests to pass.**
4. **Follow the Targeted Workflow:**
   ```text
   CODE CHANGE
       ↓
   Targeted tests (affected files only, 2-4 workers)
       ↓
   Subsystem regression
       ↓
   ONE final full regression (.\tools\test_fast.ps1)
   ```

---

## 2. Test Runner Commands

### 2.1 Targeted Development Testing (During Feature / Fix Iteration)
When editing a specific module or component, run ONLY the affected test files:
```powershell
# Single test file (2 workers)
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_phase3b_wiring.py

# Multiple affected files (4 workers)
.\tools\test_fast.ps1 -Workers 4 -Tests tests/unit/test_motion_executor.py,tests/unit/test_motion_resolver.py
```

### 2.2 Full Regression (Final Pre-PR Gate)
When completing a milestone or before pushing:
```powershell
# Default FULL mode (8 workers, worksteal distribution, thread caps active)
.\tools\test_fast.ps1

# BALANCED mode (4 workers - optimal for 4 physical cores)
.\tools\test_fast.ps1 -Mode Balanced

# Explicit worker override
.\tools\test_fast.ps1 -Workers 4
```

### 2.3 Concurrent Agent Execution (Multi-Agent Protocol)
When another agent is concurrently working in a parallel worktree:
```powershell
# Limit each agent to 2 workers to avoid CPU saturation and thermal throttling
.\tools\test_fast.ps1 -Mode Concurrent
# OR:
.\tools\test_fast.ps1 -Workers 2
```

### 2.4 Serial Debugging / Equivalence Verification
To isolate flaky tests or debug potential race conditions against a single-process baseline:
```powershell
.\tools\test_serial.ps1 -Tests tests/unit/test_piece_drop.py
```

---

## 3. Worker Preset Modes

| Mode | Workers | Recommended Context |
| :--- | :--- | :--- |
| **`Full`** | 8 workers | Default mode when one agent owns the machine/test workload. |
| **`Balanced`** | 4 workers | Matches physical core count (4 cores); minimizes context-switch overhead. |
| **`Concurrent`** | 2 workers | Essential when two AI agents are running test suites simultaneously. |

---

## 4. Numerical Thread Limits
To prevent thread oversubscription (e.g. 8 processes × 8 OpenMP threads = 64 threads on 8 logical cores), `tools/test_fast.ps1` automatically enforces:
* `OMP_NUM_THREADS = 1`
* `MKL_NUM_THREADS = 1`
* `OPENBLAS_NUM_THREADS = 1`
* `NUMEXPR_NUM_THREADS = 1`

Do NOT remove these environment variable clamps.

---

## 5. Test Classification & Markers
* **Parallel-safe tests:** Executed in Part A with `pytest-xdist` (`--dist=worksteal`).
* **`@pytest.mark.serial`:** Executed strictly in Part B (single process).
* **`@pytest.mark.slow`:** Excluded from everyday regression; reserved for extensive sweeps.
* **`@pytest.mark.hardware`:** Physical hardware only; excluded from CI and automated runners.
