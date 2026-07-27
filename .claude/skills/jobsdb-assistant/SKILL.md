---
name: jobsdb-assistant
description: Run the local JobsDB Hong Kong candidate-profile and native career-ops evaluation workflow from Claude Code. Use for first-time candidate onboarding, explicit profile updates, single-keyword JobsDB discovery, incremental A-F scoring, and the local evaluation report.
---

# JobsDB Assistant

Follow the canonical workflow in
`.agents/skills/jobsdb-assistant/SKILL.md` exactly.

Python and SQLite are the state authority. Use these commands in order as
directed by Python:

```text
workflow profile-prepare
workflow profile-submit
workflow profile-answers
workflow profile-confirm
discover --keyword
workflow evaluation-prepare
workflow evaluation-submit
workflow report
dashboard doctor
dashboard start
```

Read each task from `workspace/ai-tasks/<task_id>/task.json`, then read only
the pinned integration files listed in `capability_paths`. Keep the current
Claude Code session active until the report or an explicit Python error.

For candidate onboarding, follow the canonical typed interview gate. A task
with `interview_complete: false` must return all required question dimensions
and cannot return a proposal. Collect dimension-keyed structured answers,
including explicit skip statuses when chosen by the user, then service the
follow-up task. A completed proposal includes evidence-backed `canonical_cv`
and one answer-hash-bound synthesis per dimension; Python injects and
preserves the raw answers.

For evaluation, read exactly the task's `profile_context_paths` and use the
native loading order
`config/profile.yml → modes/_shared.md → modes/_profile.md → modes/oferta.md → cv.md`.
Never recreate or edit the immutable private profile bundle.

JobsDB discovery is public browser navigation and never uses credentials or
login. Do not request password configuration during discovery.

Do not modify integration checkouts, update fork revisions, combine scoring
systems, or create application materials. Keep `dashboard start` in the
foreground. Application execution is allowed only after the user's Dashboard confirmation:
Quick Apply uses the JobsDB default CV with no cover letter, while Apply
remains manual. The Agent must not call the application endpoint or confirm it
on the user's behalf.
