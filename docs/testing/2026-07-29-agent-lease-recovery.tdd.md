# Agent Lease Recovery TDD Evidence

## Source

Derived from [Agent Lease Recovery and State Reconciliation Design](../superpowers/specs/2026-07-29-agent-lease-recovery-design.md).

## User journeys

- As a returning Agent session, I want expired claims requeued in SQLite and
  the Dashboard projection so stale `running` work can resume.
- As a user, I want an explicit Agent stop to release unfinished work without
  marking it failed or completed.
- As an Agent, I want a read-only terminal status guard without private task
  identifiers.

## RED evidence

The new repository tests initially failed because `recover_expired()` returned
an integer and `release_session()` did not exist:

```text
2 failed: TypeError: 'int' object is not iterable;
AttributeError: 'AgentWorkRepository' object has no attribute 'release_session'
```

Checkpoint: `c77cb57 test: add lease recovery identity reproducers`.

## GREEN evidence

| Guarantee | Test | Result |
|---|---|---|
| Expired claims return opaque work identities and become queued | `tests/unit/test_agent_work_repository.py::test_recover_expired_returns_recovered_work_identity` | PASS |
| Explicit session release returns identities and queues work | `tests/unit/test_agent_work_repository.py::test_release_session_returns_owned_work_identities` | PASS |
| Expired evaluation claims reconcile to Dashboard `queued` on next start | `tests/integration/test_agent_workflow_protocol.py::test_expired_evaluation_claim_is_requeued_in_dashboard_on_start` | PASS |
| Terminal progress is never moved backwards by recovery | `tests/unit/test_evaluation_progress.py::test_requeue_if_running_does_not_move_terminal_task_backwards` | PASS |
| `agent status` exposes counts without private IDs | `tests/unit/test_agent_cli.py::test_agent_status_prints_terminal_counts_without_private_ids` | PASS |
| Both Skills require a terminal guard and forbid ending with claimed work | `tests/unit/test_v03_skill_contract.py`, `tests/unit/test_jobsdb_assistant_skill.py` | PASS |

Full validation:

```text
uv run pytest -m 'not e2e' --cov=src --cov-branch --cov-report=term-missing
794 passed, 1 skipped, 25 deselected
Total coverage: 85.37%
```

## Scope and known gaps

This release does not add heartbeat, background recovery, or parallel workers.
Recovery runs at Agent `start`, `next`, `listen`, `status`, and explicit
`stop` lifecycle boundaries. Automatic watchdog recovery is part of the second
parallel-worker development.
