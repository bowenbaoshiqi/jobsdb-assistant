# Parallel Evaluation Worker Pool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable three-slot evaluation pool so one main Agent can keep three top-level scoring workers active, recover failures, and drain a 15-job batch without changing Career Ops scoring.

**Architecture:** SQLite becomes the authoritative runtime source for evaluation and pool state. A Python coordinator exposes pool start/ready/claim/heartbeat/status/stop operations; the active Claude Code or Codex session owns creation and reuse of exactly three top-level workers. Each slot receives an independent JD envelope, validates the result through the existing sequential submit path, and is capped at five assignments per worker generation.

**Tech Stack:** Python 3.11+, Typer, SQLite migrations, Pydantic, pytest, existing Agent-work protocol, existing Dashboard and Career Ops adapters.

## Global Constraints

- Parallelize `job_evaluation` only; candidate/profile/material/application work remains sequential.
- Use exactly three active top-level worker slots for the feature; never silently fall back to one or two after claiming work.
- Keep AI Job Search and Career Ops pinned checkouts read-only.
- Keep session tokens, pool IDs, slot tokens, work IDs, task paths, and profile hashes opaque to the Skills and Dashboard.
- Preserve full Simplified Chinese JD translation and Career Ops native ordered A-F evaluation for every result.
- Maximum two attempts per task; a terminal task failure must not stop independent slots.
- Main Agent heartbeat every 30 seconds; stale pool/slot recovery after 90 seconds; existing five-minute claim lease remains the final safety boundary.
- Use TDD: each task adds a failing test, proves RED, implements the smallest fix, proves GREEN, then commits.

---

### Task 1: Add durable pool, slot, and batch-task schema

**Files:**
- Create: `src/storage/v10_migration.py`
- Modify: `src/storage/database.py`
- Test: `tests/integration/test_v10_migration.py`
- Test: `tests/unit/test_migrations.py`

**Interfaces:**
- Produces tables `agent_pools`, `agent_pool_slots`, and `agent_evaluation_batch_tasks`.
- Adds no public identifiers to Dashboard payloads.

- [ ] **Step 1: Write the failing migration tests**

Assert a fresh database applies migration 10 and creates the three tables with
foreign keys and uniqueness constraints. Assert an existing v0.9 database can
apply migration 10 twice without changing schema or data.

- [ ] **Step 2: Run RED**

Run:

```bash
uv run pytest tests/integration/test_v10_migration.py tests/unit/test_migrations.py -q
```

Expected: failure because migration 10 and its tables do not exist.

- [ ] **Step 3: Implement the migration**

Create these columns:

```sql
CREATE TABLE agent_pools (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES agent_sessions(id),
  kind TEXT NOT NULL,
  batch_key TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_concurrency INTEGER NOT NULL CHECK (requested_concurrency = 3),
  actual_concurrency INTEGER NOT NULL CHECK (actual_concurrency BETWEEN 0 AND 3),
  capability_context_id TEXT NOT NULL,
  profile_context_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE TABLE agent_pool_slots (
  pool_id TEXT NOT NULL REFERENCES agent_pools(id),
  slot_token TEXT NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 3),
  status TEXT NOT NULL,
  generation INTEGER NOT NULL DEFAULT 1,
  current_work_id TEXT REFERENCES agent_work_items(id),
  assignment_count INTEGER NOT NULL DEFAULT 0,
  heartbeat_at TEXT,
  PRIMARY KEY (pool_id, slot_token),
  UNIQUE (pool_id, ordinal)
);
CREATE TABLE agent_evaluation_batch_tasks (
  pool_id TEXT NOT NULL REFERENCES agent_pools(id),
  work_id TEXT NOT NULL REFERENCES agent_work_items(id),
  ordinal INTEGER NOT NULL,
  slot_ordinal INTEGER NOT NULL CHECK (slot_ordinal BETWEEN 1 AND 3),
  PRIMARY KEY (pool_id, work_id),
  UNIQUE (pool_id, ordinal)
);
```

Register `Migration(10, "v0.9 parallel evaluation pool", add_v10_schema)` in
the existing migration list.

- [ ] **Step 4: Run GREEN**

Run the same migration command and expect all tests to pass.

- [ ] **Step 5: Commit**

```bash
git add src/storage/v10_migration.py src/storage/database.py tests/integration/test_v10_migration.py tests/unit/test_migrations.py
git commit -m "feat: add evaluation worker pool schema"
```

### Task 2: Implement pool domain records and repository transactions

**Files:**
- Create: `src/domain/agent_pool.py`
- Create: `src/storage/agent_pool_repository.py`
- Test: `tests/unit/test_agent_pool_repository.py`

**Interfaces:**
- `start_pool(session_id, batch_key, context_ids, now) -> AgentPoolRecord`.
- `ready_slot(pool_id, slot_token, capability_context_id, profile_context_id, now) -> AgentPoolSlotRecord`.
- `claim_for_slot(pool_id, slot_token, now, lease_duration) -> AgentWorkRecord | None`.
- `heartbeat(pool_id, live_slot_tokens, now) -> int`.
- `release_stale(pool_id, now) -> tuple[RecoveredAgentWork, ...]`.
- `pool_status(pool_id) -> AgentPoolStatusSnapshot`.
- `stop_pool(pool_id, now) -> tuple[RecoveredAgentWork, ...]`.

- [ ] **Step 1: Write failing repository tests**

Cover idempotent pool start, exactly three slots, ready gating, one claim per
slot, duplicate-claim exclusion, five-assignment cap, heartbeat renewal,
context mismatch rejection, and explicit stop release.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/test_agent_pool_repository.py -q
```

Expected: import/API failures because pool records and repository do not exist.

- [ ] **Step 3: Implement minimal transactional repository**

Use a single SQLite transaction for every state transition. Generate opaque
`pool-...` and `slot-...` values with `uuid.uuid4().hex`; never derive them
from JobsDB IDs. Reject claims until all three slots are `idle`. A slot claim
increments `assignment_count`, sets `current_work_id`, and copies the current
work lease generation. A successful submit/fail callback will clear the slot
through a repository method.

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/unit/test_agent_pool_repository.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/domain/agent_pool.py src/storage/agent_pool_repository.py tests/unit/test_agent_pool_repository.py
git commit -m "feat: add durable evaluation pool repository"
```

### Task 3: Add coordinator pool protocol and result handoff

**Files:**
- Modify: `src/application/agent_work_coordinator.py`
- Modify: `src/application/agent_runtime.py`
- Modify: `src/main.py`
- Test: `tests/unit/test_agent_work_coordinator.py`
- Test: `tests/unit/test_agent_cli.py`
- Test: `tests/integration/test_agent_workflow_protocol.py`

**Interfaces:**
- CLI commands: `agent pool start`, `agent pool ready`, `agent pool claim`, `agent pool heartbeat`, `agent pool status`, `agent pool stop`.
- Existing `agent submit` and `agent fail` remain the only result commit commands.

- [ ] **Step 1: Write failing coordinator/CLI tests**

Test that a 15-task batch cannot claim before all three slots are ready, then
claims at most one task per slot. Test submit clears the slot and allows its
next task. Test status returns requested/actual concurrency and counts without
private IDs. Test stale pool recovery requeues only claimed work.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/test_agent_work_coordinator.py tests/unit/test_agent_cli.py tests/integration/test_agent_workflow_protocol.py -q
```

Expected: missing `agent pool` command/API failures.

- [ ] **Step 3: Implement coordinator handoff**

The coordinator creates a pool from the current evaluation task snapshot,
assigns ordered lane positions 1/2/3..., and delegates result validation to
the existing `submit` method. On successful submit or fail it clears the slot;
on retry it preserves the same lane and increments the attempt. Status output
must use this shape:

```json
{
  "requested_concurrency": 3,
  "actual_concurrency": 3,
  "pool_state": "active",
  "work": {"queued": 12, "claimed": 3, "completed": 0, "failed": 0},
  "terminal": false
}
```

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/unit/test_agent_work_coordinator.py tests/unit/test_agent_cli.py tests/integration/test_agent_workflow_protocol.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/application/agent_work_coordinator.py src/application/agent_runtime.py src/main.py tests/unit/test_agent_work_coordinator.py tests/unit/test_agent_cli.py tests/integration/test_agent_workflow_protocol.py
git commit -m "feat: expose three-slot agent evaluation protocol"
```

### Task 4: Add heartbeat, watchdog, and restart recovery

**Files:**
- Modify: `src/storage/agent_pool_repository.py`
- Modify: `src/application/agent_work_coordinator.py`
- Modify: `src/dashboard/cli.py`
- Test: `tests/unit/test_agent_pool_repository.py`
- Test: `tests/integration/test_foreground_worker_recovery.py`

**Interfaces:**
- Main Agent invokes `agent pool heartbeat` every 30 seconds.
- Dashboard/server watchdog invokes coordinator stale recovery after 90 seconds.

- [ ] **Step 1: Write failing timing/restart tests**

Use injected timestamps to prove a live pool is renewed, an unrenewed slot is
requeued after 90 seconds, a main-process stale pool requeues all claims, and a
database restart reconstructs the pool without duplicate work.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/test_agent_pool_repository.py tests/integration/test_foreground_worker_recovery.py -q
```

- [ ] **Step 3: Implement minimal recovery**

Renew only live slot tokens supplied by the main Agent. Mark stale pools and
release their claims with lease-generation checks. Keep the existing
five-minute item lease as a secondary safety boundary. Do not recover from a
Dashboard read request.

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/unit/test_agent_pool_repository.py tests/integration/test_foreground_worker_recovery.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/storage/agent_pool_repository.py src/application/agent_work_coordinator.py src/dashboard/cli.py tests/unit/test_agent_pool_repository.py tests/integration/test_foreground_worker_recovery.py
git commit -m "feat: recover stale evaluation pools"
```

### Task 5: Fix both Skills to run the exact three-worker loop

**Files:**
- Modify: `.agents/skills/jobsdb-assistant/SKILL.md`
- Modify: `.claude/skills/jobsdb-assistant/SKILL.md`
- Test: `tests/unit/test_v03_skill_contract.py`
- Test: `tests/unit/test_jobsdb_assistant_skill.py`

**Interfaces:**
- Codex uses three top-level workers and follow-up messages for slot reuse.
- Claude Code uses three top-level Agent workers and resumes the same worker.

- [ ] **Step 1: Write failing Skill contract tests**

Assert both copies contain pool start/ready/claim/heartbeat/status/stop,
requested concurrency `3`, no nested workers, no guessed IDs, full Chinese JD
translation, A-F scoring, retry-once, and terminal completion guard.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/test_v03_skill_contract.py tests/unit/test_jobsdb_assistant_skill.py -q
```

- [ ] **Step 3: Update both Skill copies identically**

Document this exact order:

```text
doctor → start/resume → pool start(3) → create 3 workers
→ load pinned contexts → pool ready(3) → claim one per slot
→ heartbeat(30s) → validate/submit → refill slot
→ retry once or terminal fail → status terminal → report
```

Workers must never submit directly; the main Agent performs the Python submit
after validating the exact result path. A client with fewer than three worker
slots must stop before claiming work and report actual capacity.

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/unit/test_v03_skill_contract.py tests/unit/test_jobsdb_assistant_skill.py -q
```

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/jobsdb-assistant/SKILL.md .claude/skills/jobsdb-assistant/SKILL.md tests/unit/test_v03_skill_contract.py tests/unit/test_jobsdb_assistant_skill.py
git commit -m "feat: codify three-worker evaluation skill loop"
```

### Task 6: Make Dashboard counts SQLite-authoritative

**Files:**
- Modify: `src/dashboard/app.py`
- Modify: `src/dashboard/routes.py`
- Modify: `src/dashboard/static/dashboard.js`
- Test: `tests/integration/test_dashboard_api.py`

**Interfaces:**
- `/api/evaluation-progress` returns counts derived from SQLite pool/work state.
- Existing result rendering and manual refresh behavior remain unchanged.

- [ ] **Step 1: Write failing API tests**

Create a batch where SQLite is queued but legacy JSON says running. Assert the
API returns queued. Assert completed and failed counts remain terminal and no
private IDs are serialized.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/integration/test_dashboard_api.py -q
```

- [ ] **Step 3: Implement the read model**

Build a Dashboard evaluation progress query service from SQLite. Read legacy
JSON only for one-time migration metadata; never use it to override runtime
status. Keep the current Simplified Chinese labels and manual refresh button.

- [ ] **Step 4: Run GREEN**

```bash
uv run pytest tests/integration/test_dashboard_api.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/app.py src/dashboard/routes.py src/dashboard/static/dashboard.js tests/integration/test_dashboard_api.py
git commit -m "fix: make dashboard evaluation status authoritative"
```

### Task 7: End-to-end simulated and real-client validation

**Files:**
- Create: `tests/integration/test_parallel_evaluation_pool.py`
- Create: `docs/testing/2026-07-29-parallel-evaluation-pool.tdd.md`
- Modify: `tests/e2e/test_dashboard_browser.py` only if a selector contract changes.

- [ ] **Step 1: Write failing simulated-pool tests**

Simulate 15 independent JDs with three workers. Assert at most three claims,
out-of-order completion, five assignments per worker generation, one-worker
failure recovery, main-agent stale recovery, retry limit two, and unchanged
pinned integration files.

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/integration/test_parallel_evaluation_pool.py -q
```

- [ ] **Step 3: Implement only missing test harness adapters**

Use fake workers and injected clocks; do not call external model providers or
JobsDB. Keep all result validation on the Python coordinator path.

- [ ] **Step 4: Run GREEN and full regression**

```bash
uv run pytest tests/integration/test_parallel_evaluation_pool.py -q
uv run pytest -m 'not e2e' --cov=src --cov-branch --cov-report=term-missing
```

- [ ] **Step 5: Commit evidence**

```bash
git add tests/integration/test_parallel_evaluation_pool.py docs/testing/2026-07-29-parallel-evaluation-pool.tdd.md
git commit -m "test: verify parallel evaluation pool recovery"
```

After the simulated suite is green, stop implementation and ask the user to
run one real 15-job batch in Claude Code and one in Codex. Manual acceptance
must confirm three processing slots, out-of-order results, complete Chinese JD
translation, ordered A-F output, one-worker interruption recovery, and no
changes in either pinned fork.

## Self-review

- Spec coverage: schema, pool transactions, result handoff, context reuse,
  heartbeat/watchdog, Skill parity, SQLite Dashboard authority, and manual
  acceptance each have a dedicated task.
- No implementation starts before the failing test in each task.
- The only deferred behavior is real-client acceptance, which requires the
  user's Claude Code/Codex runtime and is intentionally the handoff point.
