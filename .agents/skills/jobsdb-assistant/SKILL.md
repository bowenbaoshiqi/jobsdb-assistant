---
name: jobsdb-assistant
description: Run the local JobsDB Hong Kong candidate-profile and job-evaluation workflow. Use when the user asks to initialize or update their candidate profile, discover JobsDB roles for one keyword, score current roles with native career-ops A-F evaluation, or generate the local evaluation report. Keep the current Codex or compatible agent session active until Python reports completion.
---

# JobsDB Candidate and Evaluation Workflow

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

Do not apply to jobs in this skill.

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
