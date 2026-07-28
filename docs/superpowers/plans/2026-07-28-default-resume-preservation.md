# Default Resume Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the sole JobsDB default resume, delete all non-default resumes, upload one approved job-specific PDF, and verify the final two-resume state.

**Architecture:** Keep `RemoteResumeManager` as the only owner of remote resume replacement. Change its private DOM projection from filenames to structured records and alter its deletion and verification rules; do not modify the Dashboard, application service, or Quick Apply state machine.

**Tech Stack:** Python 3.11+, Playwright page-controller port, Pydantic-compatible immutable dataclass, pytest, ruff.

## Global Constraints

- Never delete or replace the JobsDB resume marked `Default`.
- Do not interact with the `Make this my default resumé` checkbox.
- Delete every non-default resume before upload.
- The final state must contain exactly the original default resume and the current tailored PDF.
- The tailored PDF must not be default and must be selected by exact filename in Quick Apply.
- Stop before Quick Apply if remote-state verification fails.

---

### Task 1: Preserve Default Resume During Remote Replacement

**Files:**
- Modify: `src/jobsdb/resumes.py`
- Modify: `src/jobsdb/selectors.py`
- Test: `tests/unit/test_jobsdb_resume_manager.py`

**Interfaces:**
- Consumes: `RemoteResumeManager.replace_all_with(pdf_path: Path, remote_name: str)`.
- Produces: `RemoteResumeRecord(filename: str, item_automation: str, is_default: bool)` and the unchanged `RemoteResumeReceipt`.

- [ ] **Step 1: Write failing default-preservation tests**

Add a fake page that exposes one default and multiple non-default records.
Assert that replacement leaves the original default plus the uploaded PDF,
never clicks the default item, and rejects zero or multiple defaults before
upload.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
uv run pytest tests/unit/test_jobsdb_resume_manager.py -q
```

Expected: failure because the current manager deletes all names and expects a
single final file.

- [ ] **Step 3: Implement the minimal structured projection**

Add a frozen `RemoteResumeRecord`. Make the bounded page query return exact
filename, item `data-automation`, and default-marker presence. Require exactly
one default before any deletion.

- [ ] **Step 4: Delete only non-default records**

For each non-default record, click the options button scoped by its stable
item identifier and then its matching delete action. Re-read state after each
mutation. Do not click the default checkbox during upload.

- [ ] **Step 5: Verify the final remote state**

Require two records: the original default with the same filename and marker,
and `remote_name` with `is_default == false`. Raise
`ResumeUploadMismatchError` for any difference.

- [ ] **Step 6: Run focused and regression tests**

Run:

```bash
uv run pytest tests/unit/test_jobsdb_resume_manager.py \
  tests/unit/test_material_aware_apply_steps.py \
  tests/integration/test_application_execution_workflow.py -q
uv run ruff check src/jobsdb/resumes.py src/jobsdb/selectors.py \
  tests/unit/test_jobsdb_resume_manager.py
```

Expected: all tests and lint pass.

- [ ] **Step 7: Commit**

```bash
git add src/jobsdb/resumes.py src/jobsdb/selectors.py \
  tests/unit/test_jobsdb_resume_manager.py
git commit -m "fix: preserve JobsDB default resume"
```

- [ ] **Step 8: Run the real JobsDB preparation**

Restart the local Dashboard with the fixed v5 template, requeue job
`93533309`, and verify the remote drawer contains the preserved default plus
`JBA_93533309_v1_16a96a14.pdf`. Continue only until Review; do not confirm
submission.
