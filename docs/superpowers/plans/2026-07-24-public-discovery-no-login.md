# Public JobsDB Discovery Without Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the accepted JobsDB discovery flow browser-based and completely independent of accounts and login.

**Architecture:** Remove credential resolution at the CLI boundary and remove `_ensure_login` from the discovery orchestration boundary. Preserve the existing `_discover_loaded` capture pipeline and all application login behavior.

**Tech Stack:** Python, Typer, Playwright abstraction, pytest, uv, ruff

## Global Constraints

- Discovery must never read or require credentials.
- Discovery must never invoke login.
- Quick Apply login behavior remains unchanged.
- Use TDD and preserve 80% or higher total coverage.

### Task 1: Reproduce both login couplings

**Files:**
- Modify: `tests/unit/test_discover_cli.py`
- Modify: `tests/unit/test_discovery_orchestrator.py`

- [ ] Add a CLI test that makes `AccountRegistry.resolve_active` raise if
  called and still expects discovery success.
- [ ] Add an orchestrator test that stubs `_ensure_login` to raise if called,
  then expects `_discover_loaded` and `_cleanup` to be awaited.
- [ ] Run:
  `uv run pytest tests/unit/test_discover_cli.py tests/unit/test_discovery_orchestrator.py -q`
  and verify RED is caused by credential resolution and login invocation.
- [ ] Commit with
  `test: reproduce login-coupled public discovery`.

### Task 2: Remove login from discovery

**Files:**
- Modify: `src/main.py`
- Modify: `src/orchestrator.py`

- [ ] Replace discovery account resolution with an empty
  `Account(alias="public-discovery", email="", password="")`.
- [ ] Remove discovery-only login-mode handling from the CLI.
- [ ] Make `Orchestrator.discover` call `_discover_loaded` immediately after
  `_init_browser`.
- [ ] Run the same focused tests and verify GREEN.
- [ ] Commit with `fix: keep public discovery independent of login`.

### Task 3: Regression and evidence

**Files:**
- Modify: `.agents/skills/jobsdb-assistant/SKILL.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/testing/2026-07-24-public-discovery-no-login.tdd.md`

- [ ] State explicitly that discovery is public and must not request
  credentials.
- [ ] Run ruff, the full non-E2E suite, coverage, privacy guard, and
  `git diff --check`.
- [ ] Record exact RED/GREEN commits and verification results without private
  runtime data.
- [ ] Commit with `docs: record public discovery login isolation`.
