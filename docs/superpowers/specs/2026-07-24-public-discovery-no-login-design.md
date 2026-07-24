# Public JobsDB Discovery Without Login

**Status:** Approved  
**Date:** 2026-07-24  
**Target:** v0.3.0 corrective change for the accepted v0.2 discovery flow

## Outcome

`discover --keyword KEYWORD` always opens the public JobsDB Hong Kong search
experience and captures jobs without authentication. It must not resolve a
configured account, inspect credentials, call the login handler, or ask for
`JOBSDB_EMAIL` / `JOBSDB_PASSWORD`.

Authentication remains exclusive to application execution, including Quick
Apply. This change does not alter scoring or application behavior.

## Root Cause

The v0.2 implementation reused two application prerequisites:

1. the CLI called `AccountRegistry.resolve_active`, whose default auto mode
   requires credentials; and
2. `Orchestrator.discover` called `_ensure_login` before public search.

Existing tests bypassed both boundaries with a mocked account and direct calls
to `_discover_loaded`.

## Design

- The discovery CLI constructs an empty, non-secret `public-discovery`
  account identity used only for local database/session isolation.
- The discovery command has no login-mode behavior.
- `Orchestrator.discover` initializes the browser and calls
  `_discover_loaded` directly.
- Browser initialization may construct reusable components, but discovery
  never invokes `LoginHandler`.
- Public-page failures remain safe discovery failures and never fall back to
  authentication.

## Tests

- CLI discovery succeeds without credentials and never calls
  `AccountRegistry.resolve_active`.
- Orchestrator discovery initializes the browser, skips `_ensure_login`, calls
  `_discover_loaded`, and cleans up.
- Existing discovery persistence, apply-type classification, and
  non-submission tests remain green.
- Full lint, non-E2E, coverage, and privacy gates remain green.

## Non-Goals

- Removing login from Quick Apply.
- Changing browser profile persistence.
- Adding anonymous HTTP scraping outside Playwright.
- Modifying either pinned fork.
