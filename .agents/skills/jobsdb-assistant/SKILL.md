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
4. Return either `questions` or a `proposal` matching the task schema.
5. Save it to `workspace/ai-tasks/<task_id>/agent-result.json`.
6. Submit it:

```bash
uv run python -m src.main workflow profile-submit \
  --run-id RUN_ID \
  --task-id TASK_ID \
  --result workspace/ai-tasks/TASK_ID/agent-result.json
```

When Python returns questions, ask the user, save a JSON object mapping each
question to its answer, and run:

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

Never invent candidate facts. Every verified fact requires source evidence.

## 2. Discover JobsDB roles

Ask for one keyword if none was supplied. Location remains Hong Kong.

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
3. Run career-ops evaluation-only reasoning against the embedded confirmed
   profile and single JD.
4. Preserve native ordered A-F blocks and the native 1.0–5.0 overall score.
5. Save schema-valid JSON to
   `workspace/ai-tasks/<task_id>/agent-result.json`.
6. Submit it:

```bash
uv run python -m src.main workflow evaluation-submit \
  --task-id TASK_ID \
  --result workspace/ai-tasks/TASK_ID/agent-result.json
```

Do not combine scores with ai-job-search, add weights, convert to percentages,
generate application materials, or control browser application execution.
Continue other tasks if one result is rejected; report the rejected task ID
and Python validation error.

## 4. Generate the report

After all pending tasks have been submitted:

```bash
uv run python -m src.main workflow report
```

Return the complete report and identify any failed task IDs. Do not expose
full private source documents or raw task payloads.
