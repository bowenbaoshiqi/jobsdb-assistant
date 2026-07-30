---
name: jobsdb-assistant
description: Start and continuously run the complete local JobsDB Hong Kong workflow from Claude Code. Use for candidate onboarding, Dashboard job discovery, Career Ops scoring and full Simplified Chinese JD translation, tailored materials, or recovery. Keep the Agent session active until the user explicitly stops it.
---

# Run JobsDB Assistant

Python and SQLite own all state and IDs. Use only the unified Agent protocol.
Treat every returned `session` and `work_id` as opaque; copy it exactly and
never derive or search for an internal task, job, snapshot, batch, proposal,
or material ID.

## Start

From the repository root run:

```bash
uv run jobsdb-assistant agent doctor
uv run jobsdb-assistant agent start
```

Repeat `--source ABSOLUTE_PATH` for user-supplied resume/profile files. Use
`--update-profile` only on an explicit update request. Do not read source code,
scan `workspace/ai-tasks`, or query SQLite to decide what comes next.

The command returns the exact session and Dashboard URL. Report the URL and
enter the loop. Dashboard archive/search and material actions feed this same
session automatically.

## Persistent loop

```bash
uv run jobsdb-assistant agent listen --session SESSION
```

The command deliberately does not return while the queue is temporarily empty.
If the tool surface yields a running process handle, keep polling that same
process instead of starting another listener.

- `claimed`: read only the returned `task_path` and `capability_paths`. Write
  schema-valid JSON to the exact `result_path`, then run:

  ```bash
  uv run jobsdb-assistant agent submit \
    --session SESSION --work-id WORK_ID --result RESULT_PATH
  ```

- `human_required`: read `prompt_path`, request only the declared human input,
  write it to `response_path`, submit it with the exact same opaque `work_id`,
  and continue. Silence is never approval.
- recoverable error: write a sanitized error file, call
  `agent fail --session SESSION --work-id WORK_ID --error ERROR_PATH`, and
  continue other work.
- `failed`: report the blocker and exact required action.
- `stopped`: report durable results and end.

After every submit or fail, immediately run `agent listen` again. `agent next`
is a one-shot diagnostic command only: idle is not completion. Do not send a
final answer while the user expects the assistant to remain active. On an
explicit stop request run:

```bash
uv run jobsdb-assistant agent stop --session SESSION
```

Before reporting normal completion, run the read-only terminal guard:

```bash
uv run jobsdb-assistant agent status --session SESSION
```

`claimed > 0` or `queued > 0` means the workflow is not complete. A claimed
envelope must end with `agent submit`, `agent fail`, or an explicit
`agent stop`; never end the Agent turn while it is still claimed. Do not repair
state by editing the Dashboard progress file or by reading SQLite. If the
client turn disappears, the next `agent start`, `listen`, or `next` performs
lease recovery.

## Evaluation default: one Agent

When the current batch contains `job_evaluation` work, use the normal single
Agent listener. Claim one JD, complete its Career Ops evaluation, submit it,
and immediately listen again. This is the default because it avoids worker
startup, context duplication, and coordination overhead for the normal 15-job
batch:

```bash
uv run jobsdb-assistant agent listen --session SESSION
```

Do not start a pool for the normal workflow. The pool remains an explicit
experimental option for benchmark runs only:

### Optional experimental three-worker pool

Only use this section when the user explicitly requests a parallel benchmark:

```bash
uv run jobsdb-assistant agent pool start --session SESSION
uv run jobsdb-assistant agent pool ready --session SESSION --pool POOL \
  --slot SLOT --capability-context CAPABILITY_CONTEXT \
  --profile-context PROFILE_CONTEXT
uv run jobsdb-assistant agent pool claim --session SESSION --pool POOL --slot SLOT
uv run jobsdb-assistant agent pool heartbeat --session SESSION --pool POOL \
  --live-slot SLOT
uv run jobsdb-assistant agent pool status --session SESSION --pool POOL
```

The pool must report `requested_concurrency=3` and exactly three returned slot
tokens. Create exactly three top-level workers—one per returned slot—then load
only the declared pinned capability and profile context before calling
`agent pool ready` for all three. Do not claim any work until all slots are
ready. Each worker handles one JD at a time and is reused for at most five JDs;
after five, or after a context hash mismatch, replace that worker in the same
slot. The main Agent validates each result and performs `agent submit`; workers
never submit directly.

Heartbeat live slots every 30 seconds. If a worker fails, stop heartbeating its
slot and let Python requeue it after 90 seconds; replace the worker and retry once.
Keep the other slots running. Never create nested workers, guess IDs,
read SQLite, scan task directories, combine multiple JDs, or end while a pool
or claimed work is active. Use `agent pool status` before reporting terminal
completion, and call `agent pool stop` only on explicit user request.

## AI constraints

- Candidate profile: use only supplied evidence and explicit answers; never
  invent or infer skipped preferences.
- Evaluation: use native Career Ops ordered A-F evaluation and 1.0–5.0 score.
  Include a faithful full Simplified Chinese translation of every JD section;
  never replace it with a summary.
- Cover-only material: factual 100–300-word English cover letter, no tailored
  resume.
- Full material: change only `Professional Summary`, exactly four
  `Career Highlights`, and exactly three `Core Competencies`; add a factual
  100–300-word English cover letter. Never change Work Experience or later
  sections.
- Do not edit pinned integration checkouts or combine scoring engines.

## Required human gates

Candidate interview and profile confirmation, material review, Quick Apply
Review/final submission, JobsDB login or 验证码, uncertain submission results,
and external-site Apply all require the user. Keep listening for independent
work while a gate is open. Never approve, prepare, or submit an application
for the user.

Keep all private documents, tasks, JDs, materials, cookies, logs, and browser
profiles in ignored local paths. Never commit or echo complete private data.
