# Parallel Evaluation Worker Pool Design

**Date:** 2026-07-29  
**Status:** Draft for user review  
**Proposed target release:** `0.9.0`  
**Required prerequisite:** Agent Lease Recovery and State Reconciliation  

## 1. Outcome

Score one JobsDB batch with three AI workers in parallel while keeping the
Python workflow deterministic, durable, and recoverable.

The user still starts JobsDB Assistant once from Claude Code or Codex. Python
continues to own task order, identifiers, validation, retries, and Dashboard
state. The main Agent becomes an orchestrator and delegates evaluation only to
three persistent top-level workers.

For the normal 15-job batch:

- three worker slots are active concurrently;
- each worker evaluates one JD at a time;
- each worker reuses the same pinned Career Ops and candidate-profile context;
- each worker handles at most five JDs before it is recycled;
- completed results appear independently without waiting for all three workers;
- the workflow continues until every evaluation is completed or terminally
  failed.

## 2. Dependency on the First Development

This feature starts only after the lease-recovery specification is implemented
and accepted.

The prerequisite guarantees:

- expired and explicitly released claims return to `queued`;
- SQLite and the current Dashboard projection are reconciled;
- a claimed task cannot be treated as normal completion;
- status and stop commands expose a safe lifecycle boundary.

Parallel execution must not be added directly to the current unreconciled
dual-state implementation.

## 3. Product Boundaries

### 3.1 Included

- Parallel execution for `job_evaluation` work only.
- One main orchestrator Agent plus three top-level evaluation workers.
- Durable worker-pool, slot, lease, heartbeat, retry, and recovery state.
- Rolling progress: a free slot receives its next assigned JD immediately.
- Context reuse with explicit version and hash identities.
- Full Simplified Chinese JD translation and Career Ops native ordered A-F
  scoring for every job.
- A stable Python command protocol documented directly in both Skills.
- Dashboard visibility into useful pool progress without private task IDs.
- Automatic recovery when a worker or the main Agent disappears.
- Automated and real-client acceptance tests.

### 3.2 Excluded

- Parallel candidate interviewing, profile generation, material generation, or
  job application.
- A fourth evaluation worker.
- Workers spawning nested agents.
- Workers submitting applications or bypassing human approval gates.
- Editing either pinned AI Job Search or Career Ops integration checkout.
- Direct model-provider APIs, `codex exec`, `claude -p`, or a standalone AI
  daemon.
- Changing Career Ops scoring criteria.
- Combining several JDs into one AI evaluation request.

## 4. Architectural Decision

Use one main Agent and three persistent top-level evaluation workers.

```text
Claude Code or Codex session
│
├── Main Agent
│   ├── starts/resumes Python session
│   ├── creates pool with concurrency = 3
│   ├── claims and assigns work atomically
│   ├── renews live leases
│   ├── validates and submits results
│   ├── retries failures once
│   └── drains and closes the pool
│
├── Evaluation Worker Slot 1 ── one JD at a time, maximum 5 assignments
├── Evaluation Worker Slot 2 ── one JD at a time, maximum 5 assignments
└── Evaluation Worker Slot 3 ── one JD at a time, maximum 5 assignments
```

Python does not create AI workers. The Skill uses the current client's native
top-level agent primitive. Python creates the durable pool and authorizes each
slot; the main Agent connects client workers to those slots.

The main Agent does not perform scoring while a pool is active. This keeps all
three evaluation slots available and makes orchestration failures distinguishable
from scoring failures.

## 5. Why Persistent Workers

Starting a new worker for every JD repeatedly loads the same Career Ops
contract, candidate profile, and result schema. Three persistent workers reduce
Token use and startup time while keeping each JD evaluation independent.

Persistence does not permit cross-job evidence:

- a worker reads only the current envelope's task and declared context paths;
- facts from a previous JD cannot be used in a later evaluation;
- each result must cite only the current JD snapshot and current profile;
- after submission, the worker clears its current task before accepting the
  next assignment;
- a worker is recycled after five assignments or whenever its context identity
  changes.

## 6. Durable Pool Model

### 6.1 Pool

A pool record contains:

- opaque `pool_id`;
- owning Agent session;
- work kind, fixed to `job_evaluation`;
- requested and actual concurrency;
- pool status: `starting`, `active`, `draining`, `completed`, `stale`, or
  `stopped`;
- creation, last-heartbeat, and completion timestamps;
- current batch identity stored internally;
- capability and profile context identities.

### 6.2 Worker slots

Each pool has exactly three active slot records:

- opaque `slot_token`;
- ordinal `1`, `2`, or `3` for display only;
- status: `starting`, `idle`, `assigned`, `replacing`, or `stopped`;
- current work identity, stored internally;
- assignments completed in the current worker lifetime;
- last observed client status and heartbeat timestamp;
- worker generation, incremented when a crashed or recycled worker is replaced.

Only three slots may be active. Replacement reuses the failed slot and does not
increase concurrency.

### 6.3 Evaluation task mapping

Add a durable mapping from the current evaluation batch to Agent work items.
The mapping preserves batch order and worker-slot assignment without exposing
internal IDs to the Skill.

For a normal batch of 15 jobs, Python distributes five ordered task positions
to each slot. A fast slot immediately receives the next queued task from its
own assignment lane; it does not wait for the slowest slot. This gives rolling
progress while keeping each persistent worker at no more than five JDs.

A smaller batch is distributed as evenly as possible. A retry stays in the
same slot unless that worker is being replaced.

## 7. Single Runtime State Source

Before parallel execution is enabled, evaluation runtime status moves to
SQLite:

- `agent_work_items` is authoritative for queued, claimed, completed, and
  failed work;
- durable pool, slot, and batch-task mapping tables are authoritative for
  concurrency and ownership;
- Dashboard counts and rows are read from these tables;
- `evaluation-progress.json` is no longer written as an authoritative runtime
  status source.

The JSON file may be read once for migration of an incomplete legacy batch.
After migration, it is compatibility data only and cannot override SQLite.

This removes the prior class of bugs where SQLite says `queued` while the
Dashboard says `running`.

## 8. Stable Python Protocol

The parallel command surface is:

```text
jobsdb-assistant agent pool start \
  --session SESSION_TOKEN \
  --kind job_evaluation \
  --concurrency 3

jobsdb-assistant agent pool ready \
  --session SESSION_TOKEN \
  --pool POOL_ID \
  --slot SLOT_TOKEN \
  --capability-context CAPABILITY_CONTEXT_ID \
  --profile-context PROFILE_CONTEXT_ID

jobsdb-assistant agent pool claim \
  --session SESSION_TOKEN \
  --pool POOL_ID \
  --slot SLOT_TOKEN \
  --wait 30

jobsdb-assistant agent pool heartbeat \
  --session SESSION_TOKEN \
  --pool POOL_ID \
  --live-slots SLOT_TOKEN [SLOT_TOKEN ...]

jobsdb-assistant agent submit \
  --session SESSION_TOKEN \
  --work-id WORK_ID \
  --result RESULT_PATH

jobsdb-assistant agent fail \
  --session SESSION_TOKEN \
  --work-id WORK_ID \
  --error ERROR_PATH

jobsdb-assistant agent pool status \
  --session SESSION_TOKEN \
  --pool POOL_ID

jobsdb-assistant agent pool stop \
  --session SESSION_TOKEN \
  --pool POOL_ID
```

All returned identifiers are opaque. The Skill copies values from command
output and never constructs them.

### 8.1 Pool start

`pool start`:

1. verifies that the current evaluation batch and candidate profile are valid;
2. creates or resumes one idempotent pool for that session and batch;
3. returns exactly three slot tokens, context paths, and declared context
   identities.

The main Agent, rather than Python, observes the client's available worker
capacity. If three worker slots are unavailable, the Skill does not start a
pool; it reports `requested_concurrency=3` and `actual_concurrency` clearly.
If worker creation fails after pool creation, the main Agent stops that
unactivated pool. No work can be claimed before all three slots are ready.

### 8.2 Worker ready

After creating a client worker and loading its pinned context, the main Agent
calls `pool ready` with that slot's acknowledgment.

Python verifies the expected context identities and marks the slot `idle`.
`pool claim` remains disabled until all three slots are ready. This prevents a
partially created pool from silently running as one-way or two-way evaluation.

### 8.3 Pool claim

`pool claim` atomically claims at most one item assigned to that slot. It
returns the existing versioned work envelope plus:

- `pool_id`;
- `slot_token`;
- capability context identity;
- profile context identity;
- worker assignment count.

A slot cannot own two work items. A work item cannot belong to two slots.

### 8.4 Submit and fail

Workers write only the declared result or error path. The main Agent invokes
the existing submit or fail command.

Python validates:

- claim ownership and lease generation;
- current JD snapshot identity;
- profile and capability context identities;
- result schema and ordered A-F grading;
- complete Simplified Chinese translation of the JD field;
- no combined or cross-job result.

Successful submission marks the slot idle and makes its next lane item
claimable immediately.

A failed task is requeued once. Its second failure is terminal for that task
and does not stop the other slots.

## 9. Context Identity and Reuse

Two identities govern worker reuse:

```text
capability_context_id =
  integration_commit + contract_version + prompt_version

profile_context_id =
  profile_id + profile_version + profile_hash + profile_bundle_hash
```

On its first assignment, each worker loads the declared Career Ops capability,
result contract, candidate profile, and profile bundle. It acknowledges both
context identities to the main Agent.

On later assignments:

- matching identities permit reuse without re-reading unchanged context;
- any identity or file-hash mismatch invalidates the worker;
- the main Agent replaces that worker in the same slot before claiming more
  work;
- a worker that has completed five assignments is also replaced before reuse
  in another batch.

Pinned integration checkouts remain read-only and their commits are verified
before the pool starts.

## 10. Heartbeat and Recovery

### 10.1 Timing

- Main Agent heartbeat interval: 30 seconds.
- Pool or slot stale threshold: 90 seconds.
- Work-item lease: five minutes as a final safety boundary.
- Maximum evaluation attempts: two.

The main Agent reports only slots that the client still shows as active. A
heartbeat renews claims for those slots and updates pool liveness.

### 10.2 Worker failure

If one worker fails or disappears:

1. the main Agent stops declaring that slot live;
2. after at most 90 seconds, Python returns its claimed work to `queued`;
3. the other two slots continue;
4. the main Agent creates a replacement worker for the same slot;
5. the replacement reloads pinned context and retries that JD.

At no point are more than three evaluation workers active.

### 10.3 Main Agent failure

If the main Agent disappears, the pool heartbeat stops. Within 90 seconds
Python marks the pool stale and makes all of its claimed work recoverable.

On the next `agent start`, Python resumes the pool or safely returns its work to
the evaluation queue. No result is accepted from an obsolete lease generation.

Automatic 90-second recovery requires a lightweight Python watchdog owned by
the active Dashboard/server process. When no server is running, the first
development's lifecycle recovery remains the fallback.

### 10.4 Explicit stop

`pool stop` releases every pool-owned claim, stops all slots, and reconciles
their state before the Agent exits. It never marks unfinished scoring as
completed.

## 11. Fixed Skill Orchestration

Both Skill copies contain the same numbered state machine:

1. Run `agent doctor`.
2. Run `agent start` or resume its returned session.
3. Let discovery finish and confirm evaluation work exists.
4. Confirm the client can create exactly three top-level workers.
5. Run `agent pool start --concurrency 3`.
6. Create exactly one worker for each returned slot.
7. Give every worker only its pinned context paths; after it loads them, call
   `agent pool ready` with the returned identity acknowledgment.
8. After all three slots are ready, claim and assign one envelope per slot.
9. Heartbeat live slots every 30 seconds while collecting worker updates.
10. Validate and submit each finished result through Python.
11. Immediately claim the slot's next lane item and reuse the same worker.
12. On one task failure, call `agent fail` and allow one Python-owned retry.
13. Replace failed or context-invalid workers in their existing slots and run
    `pool ready` again before that slot receives work.
14. Continue until `agent pool status` reports terminal.
15. Report batch results; stop only on explicit user request or unrecoverable
    human intervention.

### 11.1 Client-specific worker operations

The Skills include a short platform adapter section:

- **Codex:** create three top-level sub-agents, use follow-up tasks to reuse the
  same worker, inspect worker status while maintaining heartbeat, and interrupt
  only for replacement or explicit stop.
- **Claude Code:** create three top-level Agent workers, resume the same worker
  for its next assignment, collect its result, and terminate only for
  replacement or explicit stop.

The exact platform operations live in the Skill. The Python protocol and
result contract remain identical across clients.

### 11.2 Explicit prohibitions

The Skills prohibit:

- reading application source to discover how to execute the workflow;
- scanning task directories, querying SQLite, or inventing IDs;
- starting nested workers;
- allowing a worker to claim its own unrelated task;
- ending while a pool or claimed work is active;
- merging multiple JDs into one evaluation;
- letting a worker apply for a job or cross a human gate;
- editing pinned integration checkouts;
- invoking external provider APIs or background AI CLIs.

Contract tests compare the Claude Code and Codex Skill semantics.

## 12. Dashboard Behavior

The Dashboard remains manually refreshed, as previously decided.

The scoring area displays:

- requested concurrency: `3`;
- actual active workers;
- queued, processing, completed, and failed counts;
- worker slot number for each processing job;
- elapsed time and attempt number;
- pool state and last heartbeat;
- completed Simplified Chinese evaluation results as they arrive.

It does not display session tokens, pool IDs, slot tokens, work IDs, task paths,
or private profile hashes.

No application or material-generation button behavior changes in this release.

## 13. Failure Handling

- **Worker result schema invalid:** reject the result, keep evidence, and use
  the task's one retry.
- **Chinese JD translation missing or substantially incomplete:** treat as
  validation failure and retry once.
- **Career Ops A-F order or required section missing:** treat as validation
  failure and retry once.
- **Profile/capability identity mismatch:** do not submit; replace the worker
  and retry with fresh context.
- **One terminal task failure:** display it clearly and continue the batch.
- **All workers unavailable:** leave unclaimed work queued and report the
  client-capacity blocker.
- **Database restart:** reconstruct pool and slot state from SQLite; do not use
  the JSON progress file as authority.
- **Late obsolete result:** reject it by lease generation and retain the current
  assignment.

## 14. Test Strategy

### 14.1 Unit tests

- Pool creation is idempotent and enforces concurrency three.
- Atomic claim prevents duplicate ownership.
- Each slot owns at most one task and at most five assignments per worker
  generation.
- Batch lanes distribute 15 tasks as five per slot.
- Heartbeat renews only declared live slots.
- Stale slot and pool recovery respect 90 seconds.
- Context identity changes force replacement.
- A task retries once and fails terminally after attempt two.
- SQLite-derived Dashboard counts match work state.

### 14.2 Integration tests

- Fifteen queued tasks start with at most three `claimed` tasks.
- Three slots make progress independently.
- A fast slot receives its next lane item without waiting for a slow slot.
- Killing one simulated worker recovers only its task; the other two continue.
- Killing the main orchestrator recovers all claims within the watchdog bound.
- Restart reconstructs the same durable pool without duplicate evaluation.
- Full Chinese JD translation and ordered A-F validation remain enforced.
- Legacy JSON progress is migrated once and cannot override SQLite.
- Pinned Career Ops worktree remains unchanged.

### 14.3 Skill contract tests

- Both Skills specify the same 15-step orchestration.
- Both request exactly three top-level workers.
- Both use follow-up/resume behavior for worker reuse.
- Both include heartbeat, status, retry, stop, and prohibition rules.
- Neither requires source inspection or private ID discovery.

### 14.4 Manual real-client test

Run one real 15-job batch in Claude Code and one in Codex:

1. verify the Dashboard shows three processing slots;
2. verify results arrive out of order as workers finish;
3. verify every result includes full Simplified Chinese JD translation and
   Career Ops A-F scoring;
4. interrupt one worker and confirm recovery without stopping the other two;
5. confirm all 15 jobs reach completed or explicit terminal failed state;
6. confirm no pinned fork files changed.

## 15. Acceptance Criteria

The release is accepted when:

1. A 15-job batch uses exactly three concurrent top-level worker slots.
2. No more than three evaluation tasks are `claimed` simultaneously.
3. Each persistent worker evaluates one JD at a time and no more than five JDs
   per worker generation.
4. A free slot starts its next assigned JD without waiting for other slots.
5. Matching capability and profile contexts are loaded once per worker.
6. Context changes or hash mismatches force worker replacement.
7. One worker failure recovers its task within 90 seconds while the other two
   continue.
8. Main Agent failure makes all owned work recoverable within 90 seconds while
   the Dashboard/server is active.
9. Every task has at most two attempts.
10. Every successful result contains full Simplified Chinese JD translation and
    Career Ops native ordered A-F scoring.
11. Dashboard runtime status comes from SQLite and cannot diverge from a JSON
    projection.
12. Both Skills execute the documented flow without source-code discovery,
    guessed IDs, nested workers, or external AI providers.
13. Candidate, material-review, and application human gates are unchanged.
14. The full non-E2E test suite remains green.

## 16. Delivery Sequence

Implementation is divided into five internal checkpoints within this second
development:

1. SQLite single-state migration and pool schema.
2. Pool commands, atomic claims, lanes, and retries.
3. Heartbeat, watchdog, stale recovery, and restart behavior.
4. Claude Code/Codex Skill orchestration and contract tests.
5. Dashboard progress plus simulated and real 3-worker acceptance tests.

Each checkpoint must leave the sequential fallback usable until the complete
parallel path passes acceptance.
