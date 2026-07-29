# Parallel Evaluation Pool TDD Evidence

## Source

Derived from [Parallel Evaluation Worker Pool Design](../superpowers/specs/2026-07-29-parallel-evaluation-worker-pool-design.md).

## RED/GREEN checkpoints

| Area | RED evidence | GREEN evidence |
|---|---|---|
| v0.9 pool schema | Missing migration 10 and pool tables | `tests/integration/test_v10_migration.py` passes; migration is idempotent |
| Pool repository | Missing `AgentPoolRepository` | `tests/unit/test_agent_pool_repository.py` passes: ready gate, atomic claim, five-assignment cap, stop release, heartbeat and stale recovery |
| Coordinator protocol | Missing `pool_start`/`pool_ready`/`pool_claim` | `tests/integration/test_agent_workflow_protocol.py::test_three_slot_pool_requires_ready_workers_before_claiming` passes |
| Skill orchestration | Both Skills lacked pool commands | `tests/unit/test_v03_skill_contract.py` and `tests/unit/test_jobsdb_assistant_skill.py` pass |
| SQLite Dashboard authority | Legacy JSON returned `running` while SQLite was queued | `tests/integration/test_dashboard_api.py::test_evaluation_progress_prefers_sqlite_pool_state_over_legacy_json` passes |
| 15-job drain | Pool stayed `active` after all tasks completed | `tests/integration/test_parallel_evaluation_pool.py` passes with three lanes of five |

## Full validation

```text
uv run ruff check src tests
All checks passed!

uv run pytest -m 'not e2e' --cov=src --cov-branch --cov-report=term-missing
806 passed, 1 skipped, 25 deselected
Total coverage: 85.16%
```

## Deliberate manual handoff

The simulated pool is complete. Real acceptance now requires the user's
Claude Code and Codex runtime because Python cannot create those AI workers.
The manual test must verify three visible processing slots, out-of-order
results, complete Simplified Chinese JD translation, ordered Career Ops A-F
output, one-worker interruption recovery, and unchanged pinned fork files.
