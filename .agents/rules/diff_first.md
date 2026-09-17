# RULE: DIFF-FIRST INCREMENTAL REPOSITORY WORKFLOW

This rule applies to all tasks, reviews, debugging, and feature additions in this repository.

## 1. DEFAULT BEHAVIOR: DIFF FIRST
* When assigned any task, bug fix, or PR review, **NEVER** begin by reading or scanning the entire repository.
* Consult `CURRENT_STATE.md` to identify `LAST_REVIEWED_HEAD`.
* Compare `LAST_REVIEWED_HEAD..HEAD` using `git log` and `git diff --stat` (or execute `python tools/agent_context.py`).

## 2. STRICT SUBSYSTEM BOUNDARY SCOPING
* Match modified files against the **Task → Files Routing Table** in `REPO_MAP.md`.
* Inspect ONLY directly affected files and their immediate dependencies.
* Do not expand inspection to other subsystems unless stack traces, shared invariants, or explicit import dependencies require it.

## 3. EVIDENCE-FIRST VERIFICATION
* Run focused unit tests first on the modified subsystem.
* Run the broader Phase 3 regression suite only after focused tests pass.
* Never declare an issue fixed or tests passed without terminal execution evidence.
* Update `CURRENT_STATE.md` and `KNOWN_ISSUES.md` upon completion.
