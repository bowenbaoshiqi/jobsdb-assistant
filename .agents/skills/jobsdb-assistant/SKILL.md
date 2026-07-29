---
name: jobsdb-assistant
description: Run the local JobsDB Hong Kong candidate-profile, job-evaluation, and review Dashboard workflow. Use when the user asks to initialize or update their candidate profile, discover JobsDB roles for one keyword, score current roles with native career-ops A-F evaluation, generate the local evaluation report, or open the local review Dashboard. Keep the current Codex or compatible agent session active until Python reports completion.
---

# JobsDB Candidate, Evaluation, Material, and Application Workflow

Python and SQLite are the state authority. Do not choose or skip workflow
stages. Do not modify either integration checkout.

## 1. Prepare the candidate profile

Choose one run ID and reuse it for the whole session.

```bash
uv run python -m src.main workflow profile-prepare \
  --run-id RUN_ID \
  --source PATH
```

Omit `--source` for an interview-only first run. Add `--update` only when the
user explicitly requests a new profile version.

If status is `ready`, continue to discovery. If status is
`waiting_for_agent`:

1. Read `workspace/ai-tasks/<task_id>/task.json`.
2. Read only its `capability_paths` below
   `integrations/candidate-profile/`.
3. Read only the listed local source documents.
4. Inspect `interview_complete` in the task. When it is `false`, return
   `questions`; a proposal is forbidden. Questions must cover every required
   dimension exactly once using the typed objects described below.
5. When `interview_complete` is `true`, return a `proposal` matching the task
   schema. It must include a complete evidence-backed `canonical_cv` and
   exactly one `intent_syntheses` item for every typed answer. Bind each item
   to the exact task answer with its SHA-256 `answer_hash`; use the same
   dimension for `dimension` and `target_field`.
6. Save it to `workspace/ai-tasks/<task_id>/agent-result.json`.
7. Submit it:

```bash
uv run python -m src.main workflow profile-submit \
  --run-id RUN_ID \
  --task-id TASK_ID \
  --result workspace/ai-tasks/TASK_ID/agent-result.json
```

The first task's `questions` result must contain exactly these dimensions:

```text
behavioral_style
career_goals
next_role_motivators
must_haves
deal_breakers
salary_expectations
references
```

Use one object per dimension with `dimension`, a concise candidate-aware
`prompt`, and `optional`. Only `salary_expectations` and `references` have
`optional: true`.

When Python returns questions, ask the user conversationally. Save a JSON
object keyed by dimension. Each value uses `status: answered` plus a non-empty
`value`, or the explicit skip status `not_provided` / `no_preference`:

```json
{
  "career_goals": {
    "status": "answered",
    "value": "Enterprise AI architecture leadership"
  },
  "salary_expectations": {
    "status": "not_provided"
  }
}
```

Include every required dimension, then run:

```bash
uv run python -m src.main workflow profile-answers \
  --run-id RUN_ID \
  --answers workspace/ai-tasks/profile-answers.json \
  --source PATH
```

Service the returned task in the same way. When Python returns a proposal,
show it to the user. Only after explicit approval run:

```bash
uv run python -m src.main workflow profile-confirm \
  --proposal-id PROPOSAL_ID
```

Never invent candidate facts or interview answers. Every factual leaf in
`canonical_cv` requires source evidence. Never convert silence into a
preference. Python injects its saved raw answers into the proposal after
validation; Agent output cannot replace or omit them.

## 2. Discover JobsDB roles

Ask for one keyword if none was supplied. Location remains Hong Kong.
Discovery uses the public JobsDB pages. It never requires an account, login,
email, password, or `JOBSDB_EMAIL` / `JOBSDB_PASSWORD`. Do not ask the user to
configure credentials for this stage.

```bash
uv run python -m src.main discover --keyword "KEYWORD"
```

Discovery itself never applies to jobs.

## 3. Prepare and service evaluations

```bash
uv run python -m src.main workflow evaluation-prepare --run-id RUN_ID
```

For every pending task:

1. Read `workspace/ai-tasks/<task_id>/task.json`.
2. Read only its `capability_paths` below
   `integrations/job-evaluation/`.
3. Read exactly the three private files listed by
   `profile_context_paths`. Load the career-ops context in this order:
   `config/profile.yml → modes/_shared.md → modes/_profile.md → modes/oferta.md → cv.md`.
   The `_shared.md` and `oferta.md` files come from the pinned integration;
   the other three come from the immutable private bundle.
4. Run career-ops evaluation-only reasoning against that native candidate
   context and the single JD.
5. Preserve native ordered A-F blocks and the native 1.0–5.0 overall score.
   Include `jd_translation_zh_cn`, a faithful full 简体中文 JD 翻译. Translate
   every section of the captured JD, including company information,
   responsibilities, requirements, salary, benefits, and employment terms.
   Do not summarize, omit sections, or invent missing information.
6. Save schema-valid JSON to
   `workspace/ai-tasks/<task_id>/agent-result.json`.
7. Submit it:

```bash
uv run python -m src.main workflow evaluation-submit \
  --task-id TASK_ID \
  --result workspace/ai-tasks/TASK_ID/agent-result.json
```

Never recreate, edit, or copy the profile bundle. Do not combine scores with
ai-job-search, add weights, convert to percentages, generate application
materials, or control browser application execution.
Continue other tasks if one result is rejected; report the rejected task ID
and Python validation error.

## 4. Generate the report

After all pending tasks have been submitted:

```bash
uv run python -m src.main workflow report
```

Return the complete report and identify any failed task IDs. Do not expose
full private source documents or raw task payloads.

## 5. Start the local review Dashboard

After discovery/evaluation, or whenever the user explicitly asks to review
the current local results, run:

```bash
uv run python -m src.main dashboard doctor
uv run python -m src.main dashboard start
```

Keep the foreground Agent session active until the user stops the service or
the command exits. Report the local `127.0.0.1` address. Do not replace the
foreground service with a detached schedule or a public/LAN binding.

The Dashboard is the human approval surface. The Agent must not click or call the Quick Apply endpoint on the user's behalf and must not confirm submission for the user.
A direct Quick Apply requires the user to use the Dashboard confirmation;
that path uses the JobsDB default CV and no cover letter. It does not tailor
a CV, generate a cover letter, or create a material task.

An Apply job only opens its JobsDB details page for manual continuation.
Never send an Apply job to browser automation. Keep the service running while
the user reviews scoring evidence, changes filters, or selects
`waiting_for_materials` jobs.

When the user archives the current batch and starts another search from the
Dashboard, do not end the Agent turn after starting the server. Python owns
discovery and automatically creates evaluation tasks scoped to the new
15-job-or-smaller batch. The Agent must complete this loop:

1. Read `/api/job-batch` until the current status is `scoring`, `scored`, or
   `failed`. Do not rerun discovery and do not call the global
   `workflow evaluation-prepare` command.
2. When status is `scoring`, read
   the next current task through Python:
   `uv run python -m src.main workflow evaluation-next`.
   When it returns `claimed`, immediately service its `task_path`; this
   durable claim changes the Dashboard state from queued to running. Never
   scan every historical `workspace/ai-tasks` directory. Python owns the
   current task map in `workspace/dashboard/evaluation-progress.json` and
   claims only tasks whose status is `queued`.
3. For each current task, follow Section 3's Career Ops loading order,
   produce one schema-valid A-F result, and submit it through
   `workflow evaluation-submit`.
4. Continue after an individual validation failure and report its task ID.
   Python updates Dashboard progress after every successful submission.
5. Call `workflow evaluation-next` again after every submission. Stop the
   scoring loop only when it returns `drained`,
   `/api/evaluation-progress` reports no
   queued or running tasks and `/api/job-batch` reports `scored`, or when the
   batch reports `failed`.

This is a hard completion gate: while any current task is queued or running,
the Agent MUST NOT send a final response, describe a claimed task as
completed work, or wait for another user message. Continue the claim,
evaluate, submit loop in the same Agent turn. A concise commentary progress
update is allowed, but it does not end the turn.

Dashboard HTTP requests are state observation only. They do not authorize
job selection, material approval, Quick Apply preparation, or submission.

## 6. Service tailored-material tasks

When the user creates a material batch in the Dashboard, remain in the
current Agent session until every task reaches `generated` or `failed`.
v0.6 application execution is available only through explicit user actions in
the Dashboard; the Agent never invokes prepare or confirm endpoints.

List work owned by Python:

```bash
uv run python -m src.main workflow material-pending
```

For every `waiting_for_agent` task:

1. Read `workspace/ai-tasks/<task_id>/task.json`.
2. Read only its `capability_paths` below
   `integrations/candidate-profile/`. These are pinned files; never edit them.
3. Read the task's three `profile_context_paths`, single JD, and native A-F
   evaluation. Treat the confirmed profile and source CV as the only factual
   sources.
4. Branch only on the task's `material_mode`:
   - `cover_letter_only`: produce only a 100–300-word English cover letter.
     Do not generate `tailored_sections` or a PDF.
   - `tailored_resume_and_cover_letter`: produce `Professional Summary`,
     exactly four `Career Highlights`, exactly three `Core Competencies`,
     and a 100–300-word English cover letter. Python alone renders the PDF
     from the fixed v5 template.
   Never rewrite Work Experience or any later section and never return an
   Agent-created PDF.
5. Run Reviewer, ATS, and factual checks in that exact order. Reviewer and
   ATS are advisory. Report check and change summaries in Simplified Chinese.
6. Write a schema-valid result matching the task identity to
   `workspace/ai-tasks/<task_id>/agent-result.json`. Always copy the task's
   `material_mode` into the result unchanged.
7. Submit only through Python:

```bash
uv run python -m src.main workflow material-submit \
  --task-id TASK_ID \
  --result workspace/ai-tasks/TASK_ID/agent-result.json
```

If one result fails validation, report its task ID and error, then continue other material tasks.
Never invent experience, dates, titles, employers,
skills, metrics, team sizes, education, or outcomes. Do not approve, reject,
regenerate, or submit materials on the user's behalf.

After each task, and once at the end, report durable progress:

```bash
uv run python -m src.main workflow material-progress --batch-id BATCH_ID
```

The first profile workflow installs missing pinned integrations only on a
genuine first run. On later runs, reuse the existing locked checkouts and
immutable confirmed profile unless the user explicitly requests an update.

## 7. Approved application execution

Keep `dashboard start` in the foreground. After the user approves materials,
Python owns the v0.6 application execution state, remote resume replacement,
exact filename verification, cover-letter entry, and browser flow.

- For Quick Apply, the user clicks prepare. `cover_letter_only` keeps the
  JobsDB default resume and skips all remote resume management.
  `tailored_resume_and_cover_letter` preserves the default resume, removes
  other non-default resumes, uploads the approved job-specific PDF, and
  selects it. Both modes fill the approved cover letter and stop at Review.
- The user must inspect Review and click confirm submission. The Agent must
  not confirm submission, call the endpoint, or simulate that approval.
- For Apply, the Dashboard copies the approved cover letter and opens the
  JobsDB detail URL. Full mode also downloads the approved PDF; cover-only
  mode keeps the JobsDB default resume. External employer-site submission
  remains manual.
- Keep the Agent and Dashboard process alive until work finishes or the user
  stops it. Report durable states and intervention errors without retrying an
  uncertain submission.
