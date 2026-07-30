# Agent Lease Recovery and State Reconciliation Design

**Date:** 2026-07-29  
**Status:** Draft for user review  
**Target release:** `0.8.1`  
**Depends on:** Agent Workflow Skill Orchestration  

## 1. Outcome

Fix the current failure mode in which an Agent claims a scoring task and exits
without submitting it, leaving SQLite and the Dashboard showing different
states.

After this change, the next Agent start, listen cycle, or explicit stop
reconciles expired or released work back to `queued` in both state stores. The
Skill also treats `claimed` as a non-terminal state and must not end a normal
run while it owns claimed work.

This is a deliberately small reliability release. It preserves the existing
single-worker, sequential evaluation flow.

## 2. Confirmed Root Cause

The problem is caused by three behaviors acting together:

1. `agent_work_items` in SQLite owns Agent claim and lease state.
2. `evaluation-progress.json` separately owns the state displayed by the
   Dashboard.
3. Expired claims are recovered lazily inside the next claim operation, but
   that recovery updates only SQLite.

The current five-minute lease also has no heartbeat. If an Agent receives a
`claimed` envelope and its turn ends before `submit` or `fail`, the work remains
claimed until a later lifecycle action recovers it. Even then, the Dashboard
can continue displaying `running` because its projection was not updated.

The resulting symptoms are:

- queued jobs never appear to start;
- one job remains `running` long after the Agent has stopped;
- SQLite says `queued` while the Dashboard says `running`;
- users must ask the Agent to inspect and repair the queue manually.

## 3. Scope

### 3.1 Included

- Return the identities of recovered work items from the repository.
- Reconcile recovered evaluation work to `queued` in the Dashboard projection.
- Run reconciliation at Agent start, before each claim/listen cycle, and during
  explicit stop.
- Add a read-only Agent status command for the Skill's terminal-state guard.
- Strengthen both Claude Code and Codex Skills so claimed work must end in
  `submit`, `fail`, or an explicit release during `stop`.
- Preserve idempotency and the current single-worker workflow.
- Add automated tests for state reconciliation and Skill parity.

### 3.2 Excluded

- Parallel scoring or a worker pool.
- Worker heartbeat or automatic 90-second failure detection.
- A background daemon that recovers work without an Agent lifecycle call.
- Removing `evaluation-progress.json`.
- Migrating the Dashboard to SQLite as its only state source.
- Changing Career Ops scoring, candidate profiles, job discovery, materials,
  or application behavior.
- Changing the five-minute work-item lease.

## 4. State Ownership for This Release

SQLite remains authoritative for Agent claims. The JSON progress file remains
the Dashboard projection.

This release does not remove the dual-state design. Instead, every operation
that moves an evaluation claim back to `queued` must update both stores through
one application-service operation.

```text
Agent lifecycle action
        │
        ▼
AgentWorkCoordinator.recover_stale_work()
        │
        ├── SQLite: claimed → queued
        │
        └── EvaluationProgressStore: running → queued
```

Callers must not independently edit either state store for lease recovery.

## 5. Repository Contract

The repository's expired-lease recovery operation currently returns only a
count. It must instead return immutable recovery records containing enough
information for the coordinator to update the correct projection.

Conceptual contract:

```python
@dataclass(frozen=True)
class RecoveredAgentWork:
    work_id: str
    kind: AgentWorkKind
    internal_task_id: str
    previous_session_id: str | None
    recovery_reason: Literal["lease_expired", "session_stopped"]


def recover_expired(now: datetime) -> list[RecoveredAgentWork]: ...

def release_session(
    session_id: str,
    now: datetime,
) -> list[RecoveredAgentWork]: ...
```

The returned records are application-internal. They are not exposed in the
Dashboard and do not require the Skill to understand evaluation IDs.

Each database transition must:

- match only `claimed` work whose lease is expired, or work owned by the
  explicitly stopped session;
- set status to `queued`;
- clear the owning session and lease expiration;
- retain attempt history;
- leave `completed`, terminal `failed`, and non-expired claims unchanged;
- return each transitioned work item exactly once.

## 6. Coordinator Reconciliation

`AgentWorkCoordinator` owns the cross-store operation:

1. Ask the repository to recover expired claims or release a stopped session.
2. For every recovered `job_evaluation` item, map its internal task identity to
   the corresponding evaluation progress record.
3. Change only a matching `running` projection to `queued`.
4. Persist the projection update.
5. Return a summary with recovered counts by work kind.

Non-evaluation work is recovered in SQLite but does not require an evaluation
progress update.

Projection reconciliation is idempotent:

- an already `queued` projection stays `queued`;
- a `completed` or terminal `failed` projection is never moved backwards;
- a missing legacy projection is logged and does not abort recovery of other
  work;
- repeating the operation returns no newly recovered work.

## 7. Lifecycle Integration

### 7.1 `agent start`

Before creating or resuming a session, Python recovers all expired claims and
reconciles their projections. The command then resumes the durable workflow
normally.

This guarantees that a returning user does not inherit a stale `running` item
from a previous Agent turn.

### 7.2 `agent next` and `agent listen`

At the beginning of every claim cycle:

1. reconcile expired claims;
2. atomically claim at most one queued item;
3. return its typed envelope.

Recovery must happen before claiming so a just-recovered item is eligible in
the same cycle.

### 7.3 `agent stop`

An explicit stop releases all claims owned by that session and reconciles their
Dashboard projections to `queued`. It then marks the session stopped.

Stopping is recoverable cancellation, not task failure. The next session may
claim the released work.

### 7.4 Dashboard reads

Opening or refreshing the Dashboard does not recover leases in this release.
Read traffic must not requeue a task that a live Agent may still be evaluating.

## 8. Read-Only Agent Status

Add a stable command:

```text
jobsdb-assistant agent status --session SESSION_TOKEN
```

It returns protocol-level counts only:

```json
{
  "protocol_version": 1,
  "session_state": "active",
  "work": {
    "queued": 11,
    "claimed": 0,
    "completed": 3,
    "failed": 0
  },
  "terminal": false
}
```

The output must not expose JobsDB job IDs, evaluation IDs, private profile
data, or filesystem scans. `terminal` is true only when the current automatic
work is drained or the session is explicitly stopped.

## 9. Skill Contract

The Claude Code and Codex Skill copies must express the same rules:

- `claimed` is never a successful stopping point.
- After receiving a claimed envelope, the Agent must produce one of:
  `agent submit`, `agent fail`, or an explicit `agent stop`.
- An `idle` wait is not workflow completion.
- Before reporting normal completion, run `agent status`.
- Do not return a final completion message while `claimed > 0`.
- If the user explicitly stops the workflow, call `agent stop` before ending.
- Do not repair state by reading SQLite, scanning task directories, guessing
  internal IDs, or editing the progress JSON.

The Skill cannot prevent a user from closing the client process. Python lease
recovery remains the safety mechanism for that case.

## 10. Failure Handling

- **Projection write fails:** keep the recovered SQLite state, report a
  reconciliation error, and retry projection reconciliation on the next
  lifecycle action. Do not reclaim the same item in that command because the
  Dashboard would still present contradictory state.
- **Legacy task mapping is absent:** log a structured warning, leave the
  projection untouched, and continue recovering other work.
- **Malformed projection file:** surface a repair-required error; do not
  overwrite unrelated progress data.
- **Concurrent recovery calls:** SQLite conditional updates ensure only one
  caller receives each recovered record.
- **Late result after work was reclaimed:** existing claim ownership and
  idempotency validation rejects the stale submit.

## 11. Test Strategy

### 11.1 Unit tests

- Repository returns recovered item identities, not only a row count.
- Expired claims are recovered; non-expired claims are not.
- Session stop releases only work owned by that session.
- Completed and terminal failed items never move backwards.
- Coordinator maps recovered evaluation work to its projection.
- Reconciliation is idempotent.
- Agent status reports protocol counts without private domain IDs.

### 11.2 Integration tests

- A claimed evaluation with an expired lease becomes `queued` in SQLite and
  the Dashboard projection during the next `agent start`.
- The same recovery occurs before `next` and `listen` claim.
- A recovered item can be claimed in that same claim cycle.
- `agent stop` releases claimed work to `queued` in both stores.
- A stale submission after recovery and reassignment is rejected.
- Existing sequential evaluation completes unchanged.

### 11.3 Skill contract tests

- Claude Code and Codex copies contain equivalent lifecycle rules.
- Both require status inspection before normal completion.
- Both prohibit ending with claimed work and prohibit private-state discovery.

## 12. Acceptance Criteria

The release is accepted when:

1. An expired claimed evaluation is `queued` in both SQLite and the Dashboard
   after the next Agent start or claim cycle.
2. Explicit stop releases all work owned by the session in both stores.
3. Non-expired claims and terminal work are unchanged.
4. Repeated recovery creates no duplicate transition or duplicate result.
5. A recovered task remains eligible for normal sequential processing.
6. The Dashboard no longer remains at `running` solely because SQLite
   recovered the task.
7. Both Skills refuse to treat `claimed` or `idle` as successful completion.
8. The full non-E2E suite remains green.

## 13. Known Limitation

If the Agent disappears and no later `start`, `next`, `listen`, or `stop`
occurs, recovery does not run automatically. The Dashboard may therefore show
the last state until the next Agent lifecycle action.

Automatic heartbeat, bounded failure detection, and durable parallel workers
are intentionally deferred to the second specification.
