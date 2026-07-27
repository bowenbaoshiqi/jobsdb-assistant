# Dashboard Manual Refresh and Chinese Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop automatic Dashboard refreshes, add an explicit refresh action, and display all scoring guidance in Chinese without changing Career Ops source data or scores.

**Architecture:** Keep the existing REST endpoints and initial page load. Remove the timer from `dashboard.js`, expose one manual refresh function, and preserve already rendered content when refresh requests fail. Add a jobsdb-assistant-owned presentation translator between persisted Career Ops evaluations and Dashboard response schemas so the database and fork remain unchanged.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, vanilla JavaScript, pytest, Playwright, Ruff.

## Global Constraints

- Dashboard must not automatically poll the progress or jobs endpoints.
- Manual refresh reloads progress and jobs while preserving current URL filters.
- Career Ops persisted records, fork code, A–F scores, and scoring algorithm remain unchanged.
- All Dashboard scoring guidance must be Chinese, including A–F titles, findings, evidence, recommendation, strengths, gaps, and risks.
- Existing user-owned untracked probe scripts must not be edited or committed.

---

## File Structure

- `src/dashboard/static/dashboard.js`: owns initial loading, filter loading, manual refresh UI state, and card rendering.
- `src/dashboard/templates/index.html`: contains the visible refresh control.
- `src/dashboard/evaluation_translation.py`: owns deterministic Chinese presentation projection for persisted evaluation text.
- `src/dashboard/query_service.py`: applies the projection while building Dashboard schemas.
- `tests/unit/test_dashboard_evaluation_translation.py`: verifies translation behavior without API or browser dependencies.
- `tests/integration/test_dashboard_api.py`: verifies the HTML contract and translated API response.
- `tests/e2e/test_dashboard_browser.py`: verifies no background refresh and validates explicit refresh behavior.
- `docs/testing/2026-07-27-v0.4.0-review-dashboard.tdd.md`: records RED/GREEN evidence.

### Task 1: Manual Refresh Instead of Automatic Polling

**Files:**
- Modify: `src/dashboard/templates/index.html`
- Modify: `src/dashboard/static/dashboard.js`
- Modify: `tests/integration/test_dashboard_api.py`
- Modify: `tests/e2e/test_dashboard_browser.py`

**Interfaces:**
- Consumes: existing `loadJobs()`, `loadEvaluationProgress()`, `/api/jobs`, and `/api/evaluation-progress`.
- Produces: `refreshDashboard()` JavaScript function and `#refresh-results` button.

- [ ] **Step 1: Write failing integration and browser tests**

Add assertions that the HTML contains a button named `刷新评分结果`, that JavaScript contains no `setInterval`, that waiting longer than 3 seconds does not replace a previously captured job-card DOM node, and that clicking the button issues new jobs/progress requests.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py -q
```

Expected: failure because `#refresh-results` is absent and automatic polling still replaces cards.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py
git commit -m "test: require manual dashboard refresh"
```

- [ ] **Step 4: Implement the minimal manual-refresh behavior**

Add this control to the template:

```html
<button id="refresh-results" type="button">刷新评分结果</button>
```

Add the element binding and explicit refresh function:

```javascript
async function refreshDashboard() {
  elements.refreshResults.disabled = true;
  elements.refreshResults.textContent = "刷新中…";
  try {
    await Promise.all([loadJobs({ preserveContentOnError: true }), loadEvaluationProgress()]);
    setStatus("评分结果已刷新。");
  } finally {
    elements.refreshResults.disabled = false;
    elements.refreshResults.textContent = "刷新评分结果";
  }
}
```

Remove the `window.setInterval(...)` block. Keep the one initial call to `loadJobs()` and `loadEvaluationProgress()`. Make `loadJobs()` accept `{ preserveContentOnError = false }` and avoid replacing existing cards with the loading placeholder or an empty list when preservation is requested.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```bash
uv run pytest tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/dashboard/templates/index.html src/dashboard/static/dashboard.js
git commit -m "fix: replace dashboard polling with manual refresh"
```

### Task 2: Chinese Evaluation Presentation Projection

**Files:**
- Create: `src/dashboard/evaluation_translation.py`
- Create: `tests/unit/test_dashboard_evaluation_translation.py`
- Modify: `src/dashboard/query_service.py`
- Modify: `tests/unit/test_dashboard_query_service.py`
- Modify: `tests/integration/test_dashboard_api.py`

**Interfaces:**
- Consumes: persisted `JobEvaluation` and `NativeDimension` text.
- Produces: `translate_evaluation(evaluation: JobEvaluation) -> JobEvaluation`, returning a copy with presentation text translated and all identity, provenance, and numeric fields unchanged.

- [ ] **Step 1: Write failing unit and integration tests**

Cover:

```python
translated = translate_evaluation(english_evaluation)
assert translated.overall_score == english_evaluation.overall_score
assert [item.code for item in translated.dimensions] == list("ABCDEF")
assert translated.dimensions[0].title == "职位与求职目标匹配度"
assert translated.recommendation == "建议谨慎申请，并先确认关键条件"
assert translated.strengths == ["企业级 AI 领导经验"]
assert translated.gaps == ["职位未说明团队规模"]
assert translated.risks == ["薪酬范围未披露"]
assert english_evaluation.strengths == ["Enterprise AI leadership"]
```

The API test must assert that representative English recommendation, strength, gap, risk, finding, and evidence strings are absent from the Dashboard response and their Chinese equivalents are present.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/unit/test_dashboard_evaluation_translation.py tests/unit/test_dashboard_query_service.py tests/integration/test_dashboard_api.py -q
```

Expected: import or assertion failure because the translator does not exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_dashboard_evaluation_translation.py tests/unit/test_dashboard_query_service.py tests/integration/test_dashboard_api.py
git commit -m "test: require Chinese dashboard evaluation results"
```

- [ ] **Step 4: Implement the presentation translator**

Create deterministic maps for:

```python
DIMENSION_TITLES = {
    "A": "职位与求职目标匹配度",
    "B": "简历匹配度",
    "C": "职级与申请策略",
    "D": "薪酬与市场需求",
    "E": "公司文化与组织条件",
    "F": "风险与阻碍",
}
```

Implement explicit phrase mappings for the Career Ops recommendation enums and common persisted findings/evidence used by the current profile. Preserve unknown text with a visible `原文：` prefix rather than silently changing meaning. Return a Pydantic copy; never mutate the repository object.

Apply `translate_evaluation()` in `DashboardQueryService` immediately after loading the valid current evaluation and before constructing `DashboardJob`.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```bash
uv run pytest tests/unit/test_dashboard_evaluation_translation.py tests/unit/test_dashboard_query_service.py tests/integration/test_dashboard_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/dashboard/evaluation_translation.py src/dashboard/query_service.py
git commit -m "feat: present Career Ops evaluations in Chinese"
```

### Task 3: Regression, Coverage, and Manual Browser Verification

**Files:**
- Modify: `docs/testing/2026-07-27-v0.4.0-review-dashboard.tdd.md`

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: verified Dashboard on port 8877 and durable TDD evidence.

- [ ] **Step 1: Run focused coverage**

```bash
uv run pytest tests/unit/test_dashboard_evaluation_translation.py tests/unit/test_dashboard_query_service.py tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py --cov=src.dashboard --cov-report=term-missing -q
```

Expected: all tests pass and changed Dashboard code remains above 80% coverage.

- [ ] **Step 2: Run lint and full non-live suite**

```bash
uv run ruff check src/ tests/
uv run pytest -m "not e2e" -q
```

Expected: Ruff passes and all non-live tests pass.

- [ ] **Step 3: Restart the existing local Dashboard**

Stop only the existing process bound to `127.0.0.1:8877`, then start the documented Dashboard CLI on the same address and port. Do not alter runtime credentials or trigger applications.

- [ ] **Step 4: Verify the live browser behavior**

Confirm in Chromium:

- no page or card refresh occurs while idle for at least 10 seconds;
- the refresh button updates progress and results only after a click;
- current evaluated jobs show Chinese advice, strengths, gaps, risks, A–F titles, findings, and evidence;
- filters, selection checkboxes, and application controls remain usable.

- [ ] **Step 5: Record evidence and commit**

Append the actual RED/GREEN commands, results, coverage, and known limitations to the TDD evidence document.

```bash
git add docs/testing/2026-07-27-v0.4.0-review-dashboard.tdd.md
git commit -m "docs: record manual refresh and Chinese results evidence"
```
