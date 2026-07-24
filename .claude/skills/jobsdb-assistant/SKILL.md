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
```

Read each task from `workspace/ai-tasks/<task_id>/task.json`, then read only
the pinned integration files listed in `capability_paths`. Keep the current
Claude Code session active until the report or an explicit Python error.

Do not modify integration checkouts, update fork revisions, combine scoring
systems, create application materials, or run application execution.
