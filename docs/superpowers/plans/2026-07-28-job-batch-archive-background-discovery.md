# Job Batch Archive and Background Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show one 15-job Dashboard batch, archive it immediately, and discover a historically unique next batch in the local Dashboard background.

**Architecture:** Add v7 batch tables and a focused repository, reuse the existing public Orchestrator with historical exclusion and a 15-job limit, and run one durable discovery worker from the FastAPI lifespan. Existing Dashboard job cards, Career Ops evaluation, material, and application code remain unchanged.

**Tech Stack:** Python 3.11+, SQLite, FastAPI, Playwright, vanilla JavaScript, pytest, ruff.

## Global Constraints

- One non-archived batch at a time.
- Archive is immediate and irreversible from the Dashboard.
- New discovery excludes every job present in any retained batch.
- Capture at most 15 eligible jobs; a smaller non-zero result is valid.
- Purge archived batches and every related datum after 30 days.
- Dashboard remains local-only and uses manual refresh.

---

### Task 1: Persist and purge job batches

**Files:**
- Create: `src/storage/v07_migration.py`
- Create: `src/storage/job_batch_repository.py`
- Modify: `src/storage/database.py`
- Create: `tests/integration/test_job_batch_repository.py`

- [ ] Write RED tests for create, ordered membership, immediate archive, one-active-batch enforcement, historical IDs, and complete 30-day purge.
- [ ] Run `uv run pytest tests/integration/test_job_batch_repository.py -q` and confirm RED.
- [ ] Implement v7 schema and minimal repository.
- [ ] Rerun focused tests and commit RED/GREEN checkpoints.

### Task 2: Discover 15 historically new jobs

**Files:**
- Modify: `src/jobsdb/homepage.py`
- Modify: `src/orchestrator.py`
- Modify: `tests/unit/test_homepage_scraper.py`
- Modify: `tests/unit/test_discover_cli.py`

- [ ] Write RED tests proving excluded IDs are skipped across pages while collecting 15 eligible jobs.
- [ ] Implement `excluded_job_ids` through scraper and Orchestrator without changing public login behavior.
- [ ] Run focused tests and commit.

### Task 3: Run durable background discovery

**Files:**
- Create: `src/application/job_batch_discovery.py`
- Create: `src/application/job_batch_worker.py`
- Modify: `src/dashboard/app.py`
- Modify: `src/dashboard/cli.py`
- Create: `tests/unit/test_job_batch_worker.py`

- [ ] Write RED tests for queue, single-worker execution, success/partial/zero/failure status, and restart recovery.
- [ ] Implement the service and lifespan worker using an injected async discovery runner.
- [ ] Run focused tests and commit.

### Task 4: Expose Dashboard archive/start/status controls

**Files:**
- Modify: `src/dashboard/routes.py`
- Modify: `src/dashboard/query_service.py`
- Modify: `src/dashboard/templates/index.html`
- Modify: `src/dashboard/static/dashboard.js`
- Modify: `tests/integration/test_dashboard_api.py`

- [ ] Write RED API/UI tests for required keyword, HTTP 202, HTTP 409, immediate disappearance, Chinese controls, and manual status refresh.
- [ ] Filter the read model to current-batch membership and add the minimal endpoint/UI.
- [ ] Run focused tests and commit.

### Task 5: Skill handoff, bootstrap, and verification

**Files:**
- Modify: `.agents/skills/jobsdb-assistant/SKILL.md`
- Modify: `.claude/skills/jobsdb-assistant/SKILL.md`
- Create: `docs/testing/job-batch-background-discovery.tdd.md`

- [ ] Add skill contract tests requiring exact current-batch scoring after `waiting_for_scoring`.
- [ ] Bootstrap the current local database with the latest 15 `AI Lead` captures.
- [ ] Run `uv run pytest -m 'not e2e' -q` and `uv run ruff check src tests`.
- [ ] Restart port 8877 and manually verify the initial 15-job batch.
- [ ] Record evidence and commit.
