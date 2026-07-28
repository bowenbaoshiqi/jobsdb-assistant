# Split Material Generation Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add separate “cover letter only” and “tailored resume + cover letter” actions while preserving the existing review and application lifecycle.

**Architecture:** Extend the existing task/package contracts with one backward-compatible `MaterialMode` value. Reuse the current generation, storage, review, and execution services; branch only where resume rendering, preview, remote resume handling, and manual handoff differ.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, SQLite, vanilla JavaScript, pytest, Playwright/Fake browser ports

## Global Constraints

- `cover_letter_only` uses the current JobsDB default resume and never renders, uploads, deletes, or selects a resume.
- `tailored_resume_and_cover_letter` preserves current behavior.
- Both modes retain Reviewer, ATS, fact checking, version history, approval, rejection, and regeneration.
- Regeneration preserves the source package mode.
- Existing persisted packages and callers default to `tailored_resume_and_cover_letter`.
- Work-experience content remains immutable in full-material generation.

---

### Task 1: Backward-Compatible Material Mode Contracts

**Files:**
- Modify: `src/domain/material.py`
- Modify: `src/adapters/application_material.py`
- Modify: `src/domain/application_execution.py`
- Modify: `src/jobsdb/apply/context.py`
- Test: `tests/unit/test_application_material_adapter.py`
- Test: `tests/unit/test_material_domain.py`
- Test: `tests/unit/test_application_execution_domain.py`

**Interfaces:**
- Produces: `MaterialMode.COVER_LETTER_ONLY`
- Produces: `MaterialMode.TAILORED_RESUME_AND_COVER_LETTER`
- Produces: `ApplicationPackage.material_mode: MaterialMode`
- Produces: `ApplicationPackage.resume: MaterialArtifact | None`
- Produces: matching mode fields on `ApplicationMaterialTask`, `ApplicationMaterialResult`, `ApplicationIdentity`, and `ApplicationMaterialContext`

- [ ] **Step 1: Write failing contract tests**

```python
def test_legacy_package_defaults_to_full_material(package_payload):
    package = ApplicationPackage.model_validate(package_payload)
    assert package.material_mode is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER


def test_cover_only_package_accepts_no_resume(package_payload):
    package_payload.update(
        material_mode="cover_letter_only",
        resume=None,
    )
    assert ApplicationPackage.model_validate(package_payload).resume is None


def test_full_package_rejects_missing_resume(package_payload):
    package_payload["resume"] = None
    with pytest.raises(ValueError, match="resume is required"):
        ApplicationPackage.model_validate(package_payload)
```

Add adapter assertions that the requested mode appears in the task and that a
result with a different mode is rejected. Add identity/context round-trip
assertions for both modes.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
uv run pytest tests/unit/test_application_material_adapter.py tests/unit/test_material_domain.py tests/unit/test_application_execution_domain.py -q
```

Expected: FAIL because `MaterialMode` and mode-aware validation do not exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/unit/test_application_material_adapter.py tests/unit/test_material_domain.py tests/unit/test_application_execution_domain.py
git commit -m "test: define split material mode contracts"
```

- [ ] **Step 4: Implement the minimal contracts**

Add:

```python
class MaterialMode(str, Enum):
    COVER_LETTER_ONLY = "cover_letter_only"
    TAILORED_RESUME_AND_COVER_LETTER = "tailored_resume_and_cover_letter"
```

Use `TAILORED_RESUME_AND_COVER_LETTER` as the default on all new fields. Make
`ApplicationPackage.resume` optional and add an after-validator:

```python
if (
    self.material_mode is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    and self.resume is None
):
    raise ValueError("resume is required for tailored material mode")
if (
    self.material_mode is MaterialMode.COVER_LETTER_ONLY
    and self.resume is not None
):
    raise ValueError("cover-letter-only package must not contain a resume")
```

Pass `material_mode` into `ApplicationMaterialAdapter.build_task()` and include
it in result identity validation. Make resume filename/hash optional in
execution identity/context only when the mode is cover-letter-only.

- [ ] **Step 5: Run tests to verify GREEN**

Run the Task 1 command. Expected: PASS.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/domain/material.py src/adapters/application_material.py src/domain/application_execution.py src/jobsdb/apply/context.py tests/unit
git commit -m "feat: add material generation modes"
```

---

### Task 2: Mode-Aware Generation, Persistence, and Review

**Files:**
- Modify: `src/application/generate_materials.py`
- Modify: `src/materials/artifacts.py`
- Modify: `src/storage/material_repository.py`
- Modify: `src/dashboard/material_service.py`
- Modify: `src/dashboard/material_routes.py`
- Test: `tests/integration/test_material_generation.py`
- Test: `tests/unit/test_dashboard_material_service.py`
- Test: `tests/integration/test_dashboard_material_api.py`

**Interfaces:**
- Consumes: `MaterialMode`
- Produces: `DashboardMaterialService.create_batch(material_mode: MaterialMode)`
- Produces: cover-only packages containing only a verified cover-letter artifact

- [ ] **Step 1: Write failing service tests**

Add tests proving:

```python
plan = service.create_batch(MaterialMode.COVER_LETTER_ONLY)
assert plan.pending[0].task.material_mode is MaterialMode.COVER_LETTER_ONLY
```

For submission, monkeypatch `render_tailored_resume` to fail if called, submit a
valid cover-only result, and assert:

```python
assert package.resume is None
assert package.material_mode is MaterialMode.COVER_LETTER_ONLY
assert Path(package.cover_letter.path).is_file()
```

Add an API test:

```python
response = client.post(
    "/api/material-batches",
    json={"material_mode": "cover_letter_only"},
)
assert response.status_code == 202
assert response.json()["material_mode"] == "cover_letter_only"
```

Verify regeneration retains `cover_letter_only`.

- [ ] **Step 2: Run tests to verify RED**

```bash
uv run pytest tests/integration/test_material_generation.py tests/unit/test_dashboard_material_service.py tests/integration/test_dashboard_material_api.py -q
```

Expected: FAIL because batch creation and installation always require a resume.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/integration/test_material_generation.py tests/unit/test_dashboard_material_service.py tests/integration/test_dashboard_material_api.py
git commit -m "test: define cover-letter-only generation"
```

- [ ] **Step 4: Implement minimal mode branches**

Add a request schema:

```python
class MaterialBatchRequest(BaseModel):
    material_mode: MaterialMode = (
        MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    )
```

Thread the mode through `create_batch()` and `plan_batch()`. Include it in task
identity so requests for different modes cannot collide.

In `_install_and_package()`, always verify and install the cover letter. Only
resolve the source CV, render PDF, validate layout, and install a resume when
the mode is full. Extend `install_package_files()` with an optional
`resume_path` and return optional resume path/hash fields.

Persist `material_mode` in the existing package JSON payload. Existing records
remain readable through the domain default. `plan_regeneration()` uses
`previous.material_mode` unchanged.

- [ ] **Step 5: Run tests to verify GREEN**

Run the Task 2 command. Expected: PASS.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/application/generate_materials.py src/materials/artifacts.py src/storage/material_repository.py src/dashboard/material_service.py src/dashboard/material_routes.py tests
git commit -m "feat: generate cover-letter-only packages"
```

---

### Task 3: Two Dashboard Actions and Mode-Aware Preview

**Files:**
- Modify: `src/dashboard/templates/index.html`
- Modify: `src/dashboard/static/dashboard.js`
- Modify: `src/dashboard/templates/material.html`
- Modify: `src/dashboard/static/material.js`
- Modify: `src/dashboard/static/material.css`
- Test: `tests/integration/test_dashboard_api.py`
- Test: `tests/e2e/test_dashboard_browser.py`

**Interfaces:**
- Consumes: `POST /api/material-batches` with `material_mode`
- Consumes: material detail `material_mode` and optional `resume`
- Produces: two selected-job generation buttons

- [ ] **Step 1: Write failing UI tests**

Assert the Dashboard HTML includes:

```python
assert 'id="generate-cover-letters"' in html
assert 'id="generate-full-materials"' in html
assert "仅定制求职信" in html
assert "定制简历 + 求职信" in html
```

In the browser test, click each unique button in separate scenarios and capture
the request body, asserting the two exact mode values.

Add a material preview test with `material_mode="cover_letter_only"` asserting
the page displays `将使用 JobsDB 默认简历`, hides `#resume-preview` and
`#resume-download`, and retains the cover letter and review buttons.

- [ ] **Step 2: Run tests to verify RED**

```bash
uv run pytest tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py -q
```

Expected: FAIL because only one generation button and one preview shape exist.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py
git commit -m "test: define split material Dashboard actions"
```

- [ ] **Step 4: Implement the two actions**

Replace the single button with:

```html
<button id="generate-cover-letters" type="button" disabled>
  仅定制求职信
</button>
<button id="generate-full-materials" type="button" class="primary" disabled>
  定制简历 + 求职信
</button>
```

Use one JavaScript function:

```javascript
async function generateSelectedMaterials(mode, button) {
  return fetch("/api/material-batches", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({material_mode: mode}),
  });
}
```

On preview render:

```javascript
const coverOnly = payload.material_mode === "cover_letter_only";
elements.resumePanel.hidden = coverOnly;
elements.defaultResumeNotice.hidden = !coverOnly;
```

Keep both buttons disabled when no jobs are selected and restore their labels
after completion. Version the modified static-script URLs to prevent stale
browser caches.

- [ ] **Step 5: Run tests to verify GREEN**

Run the Task 3 command. Expected: PASS, with authenticated JobsDB E2E cases
remaining skipped unless their explicit marker/environment is enabled.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/dashboard/templates src/dashboard/static tests/integration/test_dashboard_api.py tests/e2e/test_dashboard_browser.py
git commit -m "feat: split Dashboard material actions"
```

---

### Task 4: Default-Resume Application Branch

**Files:**
- Modify: `src/application/execute_application.py`
- Modify: `src/domain/application_execution.py`
- Modify: `src/jobsdb/apply/context.py`
- Modify: `src/jobsdb/apply/steps/resume_step.py`
- Modify: `src/jobsdb/apply/steps/cover_letter_step.py`
- Modify: `src/dashboard/routes.py`
- Modify: `src/dashboard/static/dashboard.js`
- Test: `tests/integration/test_application_execution_workflow.py`
- Test: `tests/unit/test_material_aware_apply_steps.py`
- Test: `tests/integration/test_dashboard_api.py`

**Interfaces:**
- Consumes: approved `ApplicationPackage.material_mode`
- Produces: cover-only execution that skips `ResumeReplacer.replace_all_with`
- Produces: manual handoff with optional `resume_path`/`resume_url`

- [ ] **Step 1: Write failing execution tests**

Create a cover-only approved package and assert:

```python
queued = service.queue("job-1", account_alias="personal")
await service.run_next()
await service.run_next()
assert resumes.calls == []
assert wizard.prepared[0].material_mode is MaterialMode.COVER_LETTER_ONLY
assert wizard.prepared[0].resume_filename is None
```

Add a wizard-step test proving cover-only mode leaves the existing resume
selection unchanged but still inserts the approved cover letter. Add an Apply
manual-handoff test asserting `resume_path is None` and API `resume_url is
None`.

Retain the existing full-material assertions that one resume replacement occurs.

- [ ] **Step 2: Run tests to verify RED**

```bash
uv run pytest tests/integration/test_application_execution_workflow.py tests/unit/test_material_aware_apply_steps.py tests/integration/test_dashboard_api.py -q
```

Expected: FAIL because every approved execution requires and replaces a resume.

- [ ] **Step 3: Commit the RED checkpoint**

```bash
git add tests/integration/test_application_execution_workflow.py tests/unit/test_material_aware_apply_steps.py tests/integration/test_dashboard_api.py
git commit -m "test: define default-resume approved application"
```

- [ ] **Step 4: Implement mode-aware execution**

In `_prepare()`:

```python
context, resume = self._context(execution)
if resume is not None:
    await self.resume_manager.replace_all_with(
        resume,
        context.resume_filename,
    )
result = await self.wizard.prepare(context)
```

Verify only the cover artifact in cover-only mode. Keep full-mode resume hash
and layout validation unchanged. Include the mode in `ApplicationIdentity` so
idempotency distinguishes modes.

In the apply material step, skip resume selection when
`context.material_mode` is cover-only; continue through the existing cover
letter path. For manual Apply roles, return no resume download URL for
cover-only mode and label the Dashboard action as using the JobsDB default
resume plus the approved cover letter.

- [ ] **Step 5: Run tests to verify GREEN**

Run the Task 4 command. Expected: PASS.

- [ ] **Step 6: Commit the GREEN checkpoint**

```bash
git add src/application/execute_application.py src/domain/application_execution.py src/jobsdb/apply/context.py src/jobsdb/apply/steps/resume_step.py src/jobsdb/apply/steps/cover_letter_step.py src/dashboard/routes.py src/dashboard/static/dashboard.js tests
git commit -m "feat: apply cover letters with default resume"
```

---

### Task 5: Regression, Coverage, and Evidence

**Files:**
- Create: `docs/testing/2026-07-28-split-material-generation-modes.tdd.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks
- Produces: user-facing setup/behavior documentation and preserved TDD evidence

- [ ] **Step 1: Update README behavior**

Document the two Dashboard choices, their review requirement, and the exact
resume behavior. State that cover-only mode does not alter the JobsDB default
resume.

- [ ] **Step 2: Run focused and non-E2E regression**

```bash
uv run pytest -m "not e2e" -q
uv run ruff check src tests
node --check src/dashboard/static/dashboard.js
node --check src/dashboard/static/material.js
```

Expected: all selected tests and checks pass.

- [ ] **Step 3: Run coverage**

```bash
uv run pytest -m "not e2e" --cov=src --cov-branch --cov-report=term-missing
```

Expected: project threshold passes and changed application/material modules
retain at least 80% statement coverage.

- [ ] **Step 4: Perform local browser validation**

On port 8877, select test jobs and verify:

1. both generation buttons enable;
2. cover-only task preview contains no PDF viewer;
3. full task preview contains the inline PDF viewer;
4. approve/reject/regenerate controls work in both modes;
5. no application is submitted during validation.

- [ ] **Step 5: Write TDD evidence**

Record each Task 1–4 RED command/failure, GREEN command/result, regression
command, coverage output, browser result, and checkpoint commit in
`docs/testing/2026-07-28-split-material-generation-modes.tdd.md`.

- [ ] **Step 6: Commit documentation and evidence**

```bash
git add README.md docs/testing/2026-07-28-split-material-generation-modes.tdd.md
git commit -m "docs: explain split material generation modes"
```
