# Public JobsDB Discovery Without Login TDD Evidence

**Date:** 2026-07-24  
**Status:** GREEN  
**Design:** `docs/superpowers/specs/2026-07-24-public-discovery-no-login-design.md`  
**Plan:** `docs/superpowers/plans/2026-07-24-public-discovery-no-login.md`

## Guarantee

JobsDB discovery uses public browser pages and is independent of account
resolution, email, password, and login. Authentication remains available to
application execution and was not changed.

## RED

- Commit: `335bce1`
- Command:
  `uv run pytest tests/unit/test_discover_cli.py tests/unit/test_discovery_orchestrator.py -q`
- Result: `2 failed, 6 passed`.
- Evidence:
  - CLI failed because it called `AccountRegistry.resolve_active`.
  - Orchestrator failed because it awaited `_ensure_login`.

## GREEN

- Commit: `362ae12`
- Command:
  `uv run pytest tests/unit/test_discover_cli.py tests/unit/test_discovery_orchestrator.py -q`
- Result: `8 passed`.
- Guarantees:
  - CLI creates only the empty `public-discovery` identity.
  - CLI does not resolve configured accounts or credentials.
  - Orchestrator initializes the browser and enters public discovery directly.
  - Orchestrator never invokes login during discovery.
  - Public-page failure still cleans up the browser.
  - Existing capture and non-submission behavior remains covered.

## Full Verification

```text
uv run ruff check src tests
uv run pytest -m "not e2e" -q
uv run pytest -m "not e2e" --cov=src --cov-branch --cov-report=term -q
uv run python scripts/privacy_guard.py
git diff --check
```

Results:

- Ruff: PASS
- Non-E2E suite: `503 passed, 1 skipped, 20 deselected`
- Coverage suite: `503 passed, 1 skipped, 20 deselected`
- Combined coverage: `84.35%`
- Required coverage: `80.0%`
- Privacy guard: PASS
- Git diff check: PASS

Existing Pydantic v1 deprecation and legacy SQLite connection resource warnings
remain documented and do not affect this change.

No account data, credentials, candidate documents, browser profiles, cookies,
or private runtime artifacts are included in this report.
