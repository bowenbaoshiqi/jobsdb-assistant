---
name: jobsdb-assistant
description: Start and continuously run the complete local JobsDB Hong Kong workflow from Codex or another compatible Agent. Use for candidate onboarding, Dashboard-driven job discovery, Career Ops scoring with full Simplified Chinese JD translation, tailored application materials, workflow recovery, or keeping the local assistant active until the user explicitly stops it.
---

# Run JobsDB Assistant

Use only the versioned Python Agent protocol. Python and SQLite own workflow
order, state, retries, and identity. Treat `session` and `work_id` as opaque:
copy them exactly and never construct, parse, or substitute them.

## Start once

From the repository root run:

```bash
uv run jobsdb-assistant agent doctor
uv run jobsdb-assistant agent start
```

When the user supplies one or more resume/profile files, repeat
`--source ABSOLUTE_PATH` on `agent start`. Add `--update-profile` only when the
user explicitly asks to replace the confirmed profile. Do not invent a
`run_id`, inspect source code to discover commands, scan task directories, or
query SQLite.

`agent start` reuses durable work when possible and returns the exact session
plus the local Dashboard URL. Tell the user the URL, then remain in the work
loop. The user may archive/search batches and request materials entirely from
the Dashboard.

## Work loop

Run the persistent listener:

```bash
uv run jobsdb-assistant agent listen --session SESSION
```

The command deliberately does not return while the queue is temporarily empty.
If the tool surface yields a running process handle, keep polling that same
process instead of starting another listener. Handle exactly the returned
state:

- `claimed`: read only `task_path` and the listed `capability_paths`. Reuse
  already loaded capability context when its path and pinned SHA are unchanged
  in this Agent turn. Produce schema-valid JSON at the exact `result_path`,
  then run:

  ```bash
  uv run jobsdb-assistant agent submit \
    --session SESSION --work-id WORK_ID --result RESULT_PATH
  ```

- `human_required`: read the exact `prompt_path`, ask only for the declared
  human decision or answers, write the response to the exact `response_path`,
  and submit it with the same `agent submit` command. Never infer approval
  from silence.
- recoverable task error: write a concise sanitized error file and run:

  ```bash
  uv run jobsdb-assistant agent fail \
    --session SESSION --work-id WORK_ID --error ERROR_PATH
  ```

  Continue the loop so one failed job does not block unrelated work.
- `failed`: report the exact sanitized blocker and required user action.
- `stopped`: report the final durable counts and end.

After every submit or fail, immediately run `agent listen` again. `agent next`
is a one-shot diagnostic command only: idle is not completion. Never send a final response
merely because a queue is temporarily empty. Continue until the user explicitly
says to stop, then run:

```bash
uv run jobsdb-assistant agent stop --session SESSION
```

## Claimed-work rules

The task schema and declared pinned capabilities define the AI work. Do not
substitute a second scoring system or edit either integration checkout.

- Candidate work: use only supplied documents and explicit interview answers.
  Never invent facts or turn a skipped answer into a preference. Present the
  proposal at the Python-created confirmation gate.
- Job evaluation: use Career Ops native ordered A-F reasoning and 1.0–5.0
  score. Return a faithful full Simplified Chinese translation of every
  captured JD section, including company information, responsibilities,
  requirements, salary, benefits, and employment terms. Do not summarize or
  omit sections.
- Cover-letter-only material: produce one factual 100–300-word English cover
  letter and no tailored resume sections.
- Full material: tailor only `Professional Summary`, exactly four
  `Career Highlights`, and exactly three `Core Competencies`, plus one factual
  100–300-word English cover letter. Never modify Work Experience or anything
  after it. Reviewer and ATS are advisory; factual consistency remains a
  controlled review gate.

## Human and application boundaries

The following always require the user:

- candidate interview answers and profile confirmation;
- material approval, rejection, regeneration, or factual-risk override;
- Quick Apply Review and final submission confirmation;
- JobsDB login, 验证码, or uncertain submission handling;
- every external-site Apply submission.

Keep listening while a Dashboard human gate is open because other independent
work may arrive. Never call a Quick Apply preparation/confirmation endpoint,
approve materials, or confirm submission for the user.

All candidate data, tasks, JD content, materials, cookies, logs, and browser
profiles remain in ignored local runtime paths. Never commit or print complete
private source documents.
