# Split Material Generation Modes TDD Evidence

## Source

- Design:
  `docs/superpowers/specs/2026-07-28-split-material-generation-modes-design.md`
- Plan:
  `docs/superpowers/plans/2026-07-28-split-material-generation-modes.md`

## User Journeys

1. A user can select jobs and generate only tailored cover letters.
2. A user can retain the existing tailored-resume-and-cover-letter flow.
3. Both modes use the same preview, review, approval, rejection, regeneration,
   and version lifecycle.
4. An approved cover-letter-only Quick Apply keeps the JobsDB default resume
   and never runs remote resume management.
5. An approved cover-letter-only Apply handoff copies the cover letter and
   opens the job without downloading a resume.

## RED/GREEN Evidence

| Behavior | RED evidence | GREEN evidence |
|---|---|---|
| Domain contracts carry a backward-compatible material mode | Contract suite failed during collection because `MaterialMode` did not exist | `32 passed` for adapter, material-domain, and execution-domain tests |
| Cover-only generation skips PDF rendering and preserves mode | Generation tests failed because `plan_batch()` and Dashboard batch creation did not accept `material_mode` | `46 passed` across generation, artifacts, contracts, and material API regression |
| Dashboard exposes two actions and a mode-aware preview | Dashboard tests failed because the two button IDs and default-resume notice did not exist | `22 passed`; both Dashboard JavaScript files passed `node --check` |
| Cover-only execution keeps the default resume | Execution tests failed because package execution dereferenced a missing resume and the resume step attempted exact-file selection | `35 passed` across execution workflow, material-aware apply steps, and Dashboard API |
| Cover-only manual handoff omits resume download | API test received a tailored-resume URL for a cover-only handoff | API now returns `resume_url: null`; execution handoff returns `resume_path: None` |
| Cover-only Agent tasks avoid unused resume rewriting | Adapter test failed because `tailored_sections` was mandatory | Cover-only tasks expose no tailored section names and accept only the cover letter plus checks |

Checkpoint commits:

- `18351a2` — contract RED
- `4ede3e6` — contract GREEN
- `f96a57b` — generation RED
- `c7f4564` — generation GREEN
- `e5c0861` — Dashboard RED
- `5c1cabe` — Dashboard GREEN
- `58f2cf1` — automatic execution RED
- `acb4b14` — manual handoff RED
- `2dec03e` — application execution GREEN
- `cde0aba` — Agent protocol RED
- `84b2719` — focused cover-only task RED
- `8a4182b` — focused Agent task and Skill GREEN

## Test Specification

| # | Guarantee | Test target | Type | Result |
|---|---|---|---|---|
| 1 | Legacy packages default to full-material mode | `tests/unit/test_material_domain.py` | Unit | PASS |
| 2 | Cover-only packages contain no resume artifact | `tests/unit/test_material_domain.py` | Unit | PASS |
| 3 | Agent result mode must match its task | `tests/unit/test_application_material_adapter.py` | Unit | PASS |
| 4 | Cover-only submission never invokes the PDF renderer | `tests/integration/test_material_generation_workflow.py` | Integration | PASS |
| 5 | Regeneration preserves cover-only mode | `tests/integration/test_material_generation_workflow.py` | Integration | PASS |
| 6 | Material batch API accepts both exact mode values | `tests/integration/test_dashboard_material_api.py` | Integration | PASS |
| 7 | Cover-only material detail exposes no resume | `tests/integration/test_dashboard_material_api.py` | Integration | PASS |
| 8 | Dashboard contains both Chinese material actions | `tests/integration/test_dashboard_api.py` | Integration | PASS |
| 9 | Cover-only automatic preparation never calls resume replacement | `tests/integration/test_application_execution_workflow.py` | Integration | PASS |
| 10 | Cover-only resume step retains the existing default selection | `tests/unit/test_material_aware_apply_steps.py` | Unit | PASS |
| 11 | Cover-only review verifies job and cover letter without a tailored filename | `tests/unit/test_material_aware_apply_steps.py` | Unit | PASS |
| 12 | Cover-only manual handoff has no resume URL | `tests/integration/test_dashboard_api.py` | Integration | PASS |
| 13 | Cover-only Agent result omits unused tailored sections | `tests/unit/test_application_material_adapter.py` | Unit | PASS |
| 14 | Canonical CC/Codex Skill preserves material mode | `tests/unit/test_dashboard_documentation.py` | Unit | PASS |

## Regression and Coverage

Commands:

```bash
uv run pytest -m 'not e2e' -q
uv run ruff check src tests
node --check src/dashboard/static/dashboard.js
node --check src/dashboard/static/material.js
uv run pytest -m 'not e2e' --cov=src --cov-branch --cov-report=term-missing
```

Results:

- Non-E2E regression: `733 passed, 1 skipped, 25 deselected`
- Ruff: pass
- JavaScript syntax: pass
- Coverage: `86.03%`, exceeding the configured 80% threshold
- The first coverage run found one stale README assertion. The documentation
  contract was updated to the two new button labels and the final non-E2E
  regression passed.

## Browser Validation

The local Dashboard was restarted on port 8877 with the new source. Chrome
read-only validation confirmed:

- both actions are visible and enabled for the two selected jobs;
- labels are `仅定制求职信` and `定制简历 + 求职信`;
- existing full-material previews remain available;
- no generation, approval, application, or submission action was triggered.

Cover-only preview and application state transitions are covered by isolated
integration tests so validation does not create or mutate the user's current
material batch.
