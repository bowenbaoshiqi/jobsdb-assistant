# Evaluation Backfill Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two Dashboard actions that append missed, unevaluated jobs to the existing Agent-consumed evaluation batch.

**Architecture:** Reuse `DashboardQueryService` to resolve current pending jobs and `EvaluationProgressStore` to append unique queued job IDs. Expose one scoped FastAPI endpoint and two Simplified Chinese buttons; no AI provider, worker, automatic refresh, or new persistence layer is introduced.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite, vanilla JavaScript, pytest, ruff.

## Global Constraints

- Backfill only active jobs with no persisted evaluation.
- Skip jobs already present in the current batch.
- `selected` scope additionally requires the current Dashboard selection.
- Buttons only register missed tasks; CC/Codex remains the scorer.
- Never rescore evaluated jobs or add automatic page refresh.

---

### Task 1: Append missing jobs to an evaluation batch

**Files:**
- Modify: `src/dashboard/evaluation_progress.py`
- Test: `tests/unit/test_evaluation_progress.py`

**Interfaces:**
- Consumes: `EvaluationProgressStore._read()` and `_write()`.
- Produces: `EvaluationProgressStore.append(task_ids: list[str], now: datetime) -> tuple[EvaluationBatch | None, int]`.

- [ ] **Step 1: Write failing tests**

Add tests proving that `append` creates a batch when idle, preserves existing statuses when active or completed, queues only unique missing IDs, and returns `(None, 0)` for empty input without writing a file.

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/test_evaluation_progress.py -q`

Expected: FAIL because `EvaluationProgressStore.append` does not exist.

- [ ] **Step 3: Implement the minimal append operation**

Normalize input with insertion-order deduplication. If no batch exists, delegate to `start`. Otherwise copy existing tasks and append missing IDs as `EvaluationTaskStatus.QUEUED`. Write only when at least one ID was appended.

- [ ] **Step 4: Run the focused test**

Run: `uv run pytest tests/unit/test_evaluation_progress.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/evaluation_progress.py tests/unit/test_evaluation_progress.py
git commit -m "feat: append missed evaluation tasks"
```

### Task 2: Add the scoped backfill API

**Files:**
- Modify: `src/dashboard/routes.py`
- Test: `tests/integration/test_dashboard_api.py`

**Interfaces:**
- Consumes: `DashboardQueryService.list_jobs(DashboardFilters)` and `EvaluationProgressStore.append(...)`.
- Produces: `POST /api/evaluation-backfill?scope=all|selected` returning `batch_id`, `appended`, and current progress.

- [ ] **Step 1: Write failing API tests**

Add tests proving `all` appends both pending fixtures, `selected` appends only a selected pending fixture, repeated calls append zero, and an invalid scope returns HTTP 422.

- [ ] **Step 2: Run the focused API tests**

Run: `uv run pytest tests/integration/test_dashboard_api.py -q`

Expected: FAIL with HTTP 404 for the new endpoint.

- [ ] **Step 3: Implement the endpoint**

Use `Literal["all", "selected"]` query validation, request the all-jobs Dashboard read model, filter `evaluation_status == "pending"` and optionally `selected`, then append job IDs with `datetime.now(UTC)`. Return a private-safe summary only.

- [ ] **Step 4: Run the focused API tests**

Run: `uv run pytest tests/integration/test_dashboard_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/routes.py tests/integration/test_dashboard_api.py
git commit -m "feat: expose evaluation backfill endpoint"
```

### Task 3: Add minimal Dashboard controls

**Files:**
- Modify: `src/dashboard/templates/index.html`
- Modify: `src/dashboard/static/dashboard.js`
- Modify: `tests/integration/test_dashboard_api.py`

**Interfaces:**
- Consumes: `POST /api/evaluation-backfill?scope=all|selected`.
- Produces: buttons `#backfill-all-evaluations` and `#backfill-selected-evaluations`.

- [ ] **Step 1: Write failing HTML and JavaScript contract tests**

Assert both Chinese button labels and IDs exist, the selected button is disabled when selected count is zero, clicks POST the correct scope, and neither code path schedules automatic refresh.

- [ ] **Step 2: Run the focused tests**

Run: `uv run pytest tests/integration/test_dashboard_api.py -q`

Expected: FAIL because the controls are absent.

- [ ] **Step 3: Implement the two controls**

Place both buttons beside evaluation progress. Disable the selected button when `summary.selected === 0`; disable both during a request. Report `已补充 N 个待评分职位` or `没有遗漏的未评分职位`, then reload evaluation progress only.

- [ ] **Step 4: Run verification**

Run:

```bash
uv run pytest tests/unit/test_evaluation_progress.py tests/integration/test_dashboard_api.py -q
uv run ruff check src/dashboard tests/unit/test_evaluation_progress.py tests/integration/test_dashboard_api.py
uv run pytest -m 'not e2e' -q
```

Expected: all commands pass; no automatic refresh is introduced.

- [ ] **Step 5: Commit**

```bash
git add src/dashboard/templates/index.html src/dashboard/static/dashboard.js tests/integration/test_dashboard_api.py
git commit -m "feat: add evaluation backfill controls"
```

### Task 4: Preserve TDD evidence

**Files:**
- Create: `docs/testing/evaluation-backfill-controls.tdd.md`

**Interfaces:**
- Consumes: RED/GREEN commands and commits from Tasks 1–3.
- Produces: reviewer-readable guarantees, real command outcomes, coverage gaps, and merge evidence.

- [ ] **Step 1: Write the evidence report**

Record each guarantee, its test target, RED cause, GREEN outcome, and the final non-E2E regression result. Note that real Career Ops scoring remains an Agent-session manual test.

- [ ] **Step 2: Verify the plan has no uncommitted production changes**

Run: `git status --short`

Expected: only the evidence report is uncommitted.

- [ ] **Step 3: Commit**

```bash
git add docs/testing/evaluation-backfill-controls.tdd.md
git commit -m "docs: record evaluation backfill TDD evidence"
```
