# Headless Background Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Dashboard job discovery headlessly while keeping application execution visible.

**Architecture:** Add one focused configuration-cloning helper at the Dashboard production assembly boundary. Discovery receives a deep-copied configuration with `browser.headless=True`; all application services retain the original visible configuration.

**Tech Stack:** Python 3.11+, Pydantic settings, pytest

## Global Constraints

- Change no discovery, pagination, scoring, persistence, or application logic.
- Never mutate the shared production configuration.
- Keep Quick Apply browser execution visible.

---

### Task 1: Isolate Discovery Browser Configuration

**Files:**
- Modify: `src/dashboard/cli.py`
- Test: `tests/unit/test_dashboard_cli.py`

**Interfaces:**
- Produces: `_headless_discovery_config(config)` returning an independent configuration copy
- Guarantees: returned copy has `browser.headless is True`; input retains its original value

- [ ] **Step 1: Write the failing test**

```python
def test_discovery_config_is_headless_without_mutating_application_config():
    config = Settings()
    config.browser.headless = False

    discovery = cli._headless_discovery_config(config)

    assert discovery is not config
    assert discovery.browser.headless is True
    assert config.browser.headless is False
```

- [ ] **Step 2: Run RED**

```bash
uv run pytest tests/unit/test_dashboard_cli.py -q
```

Expected: fail because `_headless_discovery_config` does not exist.

- [ ] **Step 3: Commit RED**

```bash
git add tests/unit/test_dashboard_cli.py
git commit -m "test: require headless Dashboard discovery"
```

- [ ] **Step 4: Implement minimal isolation**

```python
def _headless_discovery_config(config):
    discovery = config.model_copy(deep=True)
    discovery.browser.headless = True
    return discovery
```

Create this copy once in `build_production_app()` and use it only inside
`discover_batch()` when constructing the discovery `Orchestrator`.

- [ ] **Step 5: Run GREEN and focused regression**

```bash
uv run pytest tests/unit/test_dashboard_cli.py tests/unit/test_job_batch_worker.py tests/unit/test_discovery_orchestrator.py -q
uv run ruff check src/dashboard/cli.py tests/unit/test_dashboard_cli.py
```

Expected: all pass.

- [ ] **Step 6: Commit GREEN**

```bash
git add src/dashboard/cli.py
git commit -m "fix: run Dashboard discovery headlessly"
```

