# Evaluation backfill controls — TDD evidence

## Source

- Design: `docs/superpowers/specs/2026-07-28-evaluation-backfill-controls-design.md`
- Plan: `docs/superpowers/plans/2026-07-28-evaluation-backfill-controls.md`

## Guarantees

| Guarantee | Test target | RED | GREEN |
|---|---|---|---|
| Missing unique job IDs append as queued without changing existing task statuses | `tests/unit/test_evaluation_progress.py` | `a4964db`: `append` absent, 3 failed | `cb6ed75`: 6 passed |
| `all` and `selected` scopes append only pending jobs and reject invalid scopes | `tests/integration/test_dashboard_api.py` | `e29fca1`: endpoint returned 404, 3 failed | `a8498f5`: 18 passed |
| Dashboard exposes two Simplified Chinese backfill controls without automatic refresh | Dashboard HTML/JavaScript contract tests | `e3a5f5f`: controls absent, 2 failed | `68d34c5`: 18 passed |

## Final verification

- `uv run pytest -m 'not e2e' -q`
  - 707 passed, 1 skipped, 25 deselected.
- `uv run ruff check src tests`
  - All checks passed.

## Known boundary

The controls register missed jobs in the durable local evaluation batch. They
do not call Career Ops or an AI provider; the active CC/Codex Agent session
continues to consume and score queued jobs through the established workflow.
