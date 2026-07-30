# Agent Workflow Skill Orchestration Design

**Date:** 2026-07-29  
**Status:** Approved in conversation; awaiting written-spec review  
**Target release:** `0.8.0`

## 1. Outcome

A user starts JobsDB Assistant once from Claude Code or Codex, then primarily
works in the local Dashboard. The same Agent turn remains active and completes
every non-human workflow stage without requiring the user to return to chat and
say “continue.”

The finished workflow supports both entry points:

- an Agent request such as “搜索并评分 AI Lead”;
- Dashboard actions such as archiving the current batch, searching another
  batch, or requesting application materials.

Both entry points feed the same Python-owned durable queue. The Agent never
discovers workflow commands by reading source code and never constructs,
guesses, or correlates internal IDs.

## 2. Problems Being Solved

The current Skill documents each workflow stage but still makes the Agent:

- select and preserve a run ID;
- distinguish JobsDB job IDs, snapshot IDs, task IDs, batch IDs, evaluation
  IDs, proposal IDs, and material versions;
- scan task directories or inspect multiple commands to find pending work;
- decide which command comes next;
- return after an apparently idle stage even though Dashboard work can arrive.

This makes a fresh Agent session expensive and fragile. It also permits a
Dashboard-created evaluation or material task to remain queued until the user
returns to chat.

## 3. Product Boundaries

### 3.1 Included

- One canonical Python protocol for all Agent-owned work.
- One opaque `work_id` exposed to the Agent.
- Automatic recovery of the current workflow state on startup.
- Continuous handling of profile, evaluation, JD translation, and material
  generation work.
- Continued listening while the Dashboard is open.
- Dashboard-triggered discovery followed by automatic evaluation.
- Fresh-machine initialization using pinned integration revisions.
- Idempotent claim, submit, retry, resume, and shutdown behavior.
- Equivalent Claude Code and Codex Skill behavior.
- Concise Skill instructions that do not require reading application source.

### 3.2 Human gates

The Agent pauses the affected workflow only for:

- candidate interview answers;
- candidate-profile confirmation;
- material approval, rejection, regeneration, or factual-risk override;
- Quick Apply review and final submission confirmation;
- login, CAPTCHA, or another browser intervention;
- an unrecoverable error requiring a user decision.

While one item is at a human gate, independent automatic work may continue.
The Agent turn remains alive unless the user stops the assistant.

### 3.3 Excluded

- A cloud service or permanently hosted Agent.
- Direct model-provider APIs or model credentials.
- Editing the AI Job Search or Career Ops integration checkouts.
- Automatic approval of a profile, material, or job submission.
- Automatic submission to external employer sites.
- Replacing the existing deterministic JobsDB application state machine.

## 4. Architectural Decision

Use a concise Skill over a versioned Python Agent-work protocol.

The Skill is the AI worker loop. Python and SQLite remain the authority for
workflow order, identity, persistence, validation, recovery, and Dashboard
events. Integration capability files remain the authority for AI reasoning.

Two alternatives are rejected:

1. Expanding the current Skill into a larger command manual would retain ID
   handling, source inspection, and high context usage.
2. A standalone AI daemon would require a provider API and contradict the
   decision to run AI work through the active Claude Code or Codex session.

## 5. Unified Agent Protocol

### 5.1 Commands

The Python CLI exposes a small stable surface:

```text
jobsdb-assistant agent doctor
jobsdb-assistant agent start
jobsdb-assistant agent next --session SESSION_TOKEN --wait 30
jobsdb-assistant agent submit --session SESSION_TOKEN --work-id WORK_ID \
  --result RESULT_PATH
jobsdb-assistant agent fail --session SESSION_TOKEN --work-id WORK_ID \
  --error ERROR_PATH
jobsdb-assistant agent stop --session SESSION_TOKEN
```

`agent start` starts or resumes a local Agent session, starts the Dashboard
when needed, and returns a Python-generated session token. The Skill treats
both the session token and `work_id` as opaque strings.

`agent next` is the only task-discovery command. It waits for a bounded period,
claims at most one task, and returns one typed envelope. The Agent never scans
`workspace/ai-tasks`, queries SQLite, polls Dashboard endpoints, or calls
stage-specific “pending” commands.

`agent submit` validates identity and schema, commits the result, updates
Dashboard progress, and schedules the next valid workflow action.

### 5.2 Work envelope

Every `agent next` response follows a versioned schema:

```json
{
  "protocol_version": 1,
  "session": "opaque-session-token",
  "state": "claimed",
  "work_id": "opaque-work-id",
  "kind": "job_evaluation",
  "task_path": "workspace/ai-tasks/.../task.json",
  "result_path": "workspace/ai-tasks/.../agent-result.json",
  "capability_paths": ["integrations/..."],
  "attempt": 1,
  "lease_expires_at": "2026-07-29T10:00:00Z"
}
```

Allowed response states are:

- `claimed`: perform the typed AI task and submit it;
- `human_required`: report the requested human interaction and continue
  bounded waiting for other automatic work;
- `idle`: no work arrived during this wait interval; call `agent next` again;
- `failed`: the workflow cannot proceed without intervention;
- `stopped`: the user or Python has ended the session.

Allowed work kinds are initially:

- `candidate_questions`;
- `candidate_proposal`;
- `job_evaluation`;
- `application_material`.

The envelope contains paths, not large private payloads. The Agent reads the
single task and only the explicitly declared capability and context paths.
This preserves progressive disclosure and limits Token use.

### 5.3 Identifier ownership

All existing domain identifiers remain internal and retain their current
semantics. Python maps them to one public Agent-work record:

```text
work_id
  ├── internal task/proposal/evaluation/material identity
  ├── current batch and snapshot identity
  ├── candidate profile version and hashes
  ├── integration contract and pinned SHA
  └── claim, attempt, and completion state
```

The Skill must not parse a `work_id`, use a JobsDB job ID as a task ID, or
carry an ID from one envelope into another.

## 6. End-to-End Flow

### 6.1 First machine or first user

1. The user invokes the JobsDB Assistant Skill.
2. The Skill runs `agent doctor`.
3. Python checks the locked environment, browser, schema, privacy paths,
   Dashboard port, resume input, and integration manifest.
4. `agent start` installs only missing pinned integration revisions.
5. Python emits candidate-profile work.
6. The Agent performs the structured interview and proposal through typed
   work envelopes.
7. The user confirms the profile.
8. Python waits for a Dashboard keyword or uses the keyword supplied in chat.
9. Discovery creates the current batch and evaluation work.
10. The Agent drains evaluation work, including full Simplified Chinese JD
    translation, and the Dashboard displays the scored batch.

### 6.2 Returning user

Python reuses the active immutable profile, installed pinned integrations,
unchanged evaluation cache, current batch, and incomplete durable tasks. It
does not repeat onboarding or installation unless the user explicitly requests
a profile update or repair.

### 6.3 Dashboard-driven next batch

```text
User archives current batch and supplies a keyword
→ Python archives all current jobs as handled
→ discovery fetches up to 15 non-historical jobs
→ Python creates and queues evaluation work
→ waiting `agent next` receives the first item
→ Agent evaluates and submits every item
→ Python marks the batch scored
→ Dashboard manual refresh displays the results
```

The keyword may match a previous batch. Existing history exclusion remains
Python-owned. Fewer than 15 public results is a successful smaller batch.

### 6.4 Dashboard-driven materials

When the user selects jobs and requests cover-letter-only or full tailored
materials, Python creates one work item per job. The same Agent session drains
all items. Reviewer and ATS remain advisory; factual consistency remains the
existing controlled safety decision. Human review continues in the Dashboard.

### 6.5 Application execution

Application preparation and submission remain Python browser workflows.
The Agent loop may report durable progress or a human-intervention state, but
does not approve materials, prepare an application on the user's behalf, or
confirm an irreversible submission.

## 7. Session and Listening Semantics

“Start once” means one foreground Claude Code or Codex Agent turn for the
current local working session, not a permanent background cloud service.

The Skill loops over bounded `agent next --wait 30` calls. This provides:

- prompt Dashboard response without a busy loop;
- a commentary heartbeat at least once per minute;
- an opportunity to process new user input;
- clean interruption when the user says to stop;
- no final response while automatic work is queued, running, or the user has
  asked the assistant to stay active.

An `idle` response is not completion. The Skill continues listening. A final
response is permitted only after `stopped`, an unrecoverable `failed` state, or
an explicit user request to end the assistant.

If the CC/Codex window or process is closed, the local Agent cannot continue
AI reasoning. On the next invocation, `agent start` resumes leases and durable
work without duplication.

## 8. Reliability and Recovery

- Claims use expiring leases bound to the Agent session.
- Submission is idempotent by `work_id` and result hash.
- A completed work item cannot be overwritten by a later submission.
- An expired claimed item becomes reclaimable with an incremented attempt.
- Python validates the work kind, task identity, profile and JD hashes,
  integration SHA, result schema, and claim ownership.
- A validation failure records the exact error and may retry the same item
  within a bounded policy.
- One failed evaluation or material item does not block unrelated items.
- A process restart reconstructs state from SQLite, not filesystem scanning.
- Dashboard progress is derived from the same work records as Agent progress.
- Discovery completion and evaluation queue creation occur transactionally
  enough that a successful batch cannot remain silently unscored.
- Unknown submission outcomes retain the existing manual-intervention
  behavior and are never retried blindly.

## 9. Token-Efficiency Requirements

- Keep each platform Skill under 250 lines, with one canonical workflow and a
  thin platform-specific forwarding file where necessary.
- Do not include CLI catalogs, internal ID definitions, database schemas, or
  troubleshooting tables in the core Skill.
- Let `agent doctor`, `agent start`, and typed envelopes provide operational
  instructions.
- Read one task at a time.
- Read only envelope-declared capability and context paths.
- Never reread integrations for every item when their paths and SHA are
  unchanged within the same batch; retain the already loaded capability
  context for that Agent turn.
- Do not render full private task payloads or source documents into chat.
- Return concise progress counts from Python instead of reconstructing them
  from directories.

## 10. Skill Packaging

The repository contains the canonical Codex-compatible Skill at:

```text
.agents/skills/jobsdb-assistant/
├── SKILL.md
└── agents/openai.yaml
```

Claude Code keeps a concise compatible Skill at:

```text
.claude/skills/jobsdb-assistant/SKILL.md
```

Both invoke the same Python protocol and enforce the same completion gate.
The README documents installation and one user-facing invocation, but the
Skill does not depend on the Agent reading the README.

The Skill includes no credentials, resume, profile, task result, or runtime
artifact. All private state remains under ignored local paths.

## 11. Error Communication

Recoverable task errors are recorded and the loop continues. The Dashboard
shows the affected item and error state.

The Agent interrupts the user only when action is required. The message must
state:

- which human gate or subsystem is blocked;
- what Python has already completed;
- the exact user action needed;
- whether other work is still continuing.

The Agent must not report a queue as complete based only on having created or
claimed its tasks.

## 12. TDD and Acceptance Criteria

Implementation follows red-green-refactor. Tests cover:

### 12.1 Unit

- work-envelope schema and protocol-version rejection;
- opaque work-ID mapping;
- claim leases, expiry, and ownership;
- idempotent submission;
- invalid identity and result-hash rejection;
- state-to-work-kind dispatch;
- idle, human-required, failed, stopped, and resume behavior.

### 12.2 Integration

- first-run profile workflow and pinned integration installation;
- returning-user profile and integration reuse;
- Dashboard archive/search creating evaluation work;
- discovery automatically handing off to scoring;
- evaluation completion marking the batch scored;
- Dashboard material requests creating independent work items;
- isolated task failure and continued queue draining;
- restart recovery without directory scanning;
- same keyword excluding historical jobs.

### 12.3 End-to-end

- a clean environment reaches the first legitimate human profile gate without
  source inspection or guessed IDs;
- an existing profile plus Dashboard keyword produces and scores a batch;
- a Dashboard archive/search action is fully scored without another user chat
  message;
- multiple selected jobs produce all requested materials without another user
  chat message;
- closing and restarting the Agent resumes unfinished work exactly once;
- Claude Code and Codex Skills drive the same protocol;
- the Agent does not end its turn while automatic work is queued or running;
- privacy checks confirm no runtime or candidate data is committed.

Acceptance requires all non-E2E tests to pass, the relevant browser E2E tests
to pass in the supported local environment, lint to pass, and a manual
Dashboard validation of the uninterrupted next-batch and material flows.

## 13. Migration

The new protocol wraps existing profile, evaluation, material, batch, and
application services. Stage-specific CLI commands remain temporarily for
diagnostics and backward compatibility, but the JobsDB Assistant Skills stop
using them.

Existing local profiles, batches, evaluations, materials, and application
history remain valid. Migration creates Agent-work records only for unfinished
durable work; it does not regenerate completed results or change fork
revisions.
