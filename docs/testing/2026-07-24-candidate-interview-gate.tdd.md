# Candidate Interview Gate TDD Evidence

**Date:** 2026-07-24  
**Status:** GREEN  
**Design:** `docs/superpowers/specs/2026-07-24-candidate-interview-gate-design.md`  
**Plan:** `docs/superpowers/plans/2026-07-24-candidate-interview-gate.md`

## User Journeys

1. As a first-time user importing one CV, I must be asked about every
   candidate-profile gap before an AI proposal can be created.
2. As a privacy-conscious user, I can explicitly decline salary or reference
   details and still complete onboarding.
3. As a returning user, I can reuse a confirmed profile without repeating the
   interview unless I explicitly request an update.
4. As the workflow owner, I need Python rather than agent judgment to decide
   whether the interview is complete.

## Task Evidence

### Typed interview contract

- RED commit: `64e97e2`
- RED command:
  `uv run pytest tests/unit/test_candidate_profile_adapter.py -q`
- RED result: test collection failed with
  `ModuleNotFoundError: No module named 'src.domain.candidate_interview'`.
- GREEN commit: `040cd28`
- GREEN command:
  `uv run pytest tests/unit/test_candidate_profile_adapter.py -q`
- GREEN result: `10 passed`.

The adapter now defines stable dimension IDs, typed questions, structured
answers, explicit skip statuses, complete coverage validation, and a proposal
gate derived from the persisted task.

### Onboarding state transitions

- RED commit: `e4dedd9`
- RED command:
  `uv run pytest tests/unit/test_candidate_onboarding.py tests/unit/test_candidate_evaluation_workflow.py -q`
- RED result: `4 failed, 4 passed`; onboarding did not supply the persisted
  task to task-aware result validation.
- GREEN commit: `c54ced3`
- GREEN command: same focused command.
- GREEN result: `8 passed`.

Invalid proposal output is now rejected before `result.json` or a database
proposal is written. A complete validated answer set produces a follow-up task
whose `interview_complete` value is derived by Python.

### CLI and skill protocol

- RED commit: `5f7b1d2`
- RED command:
  `uv run pytest tests/unit/test_workflow_cli.py tests/unit/test_integration_manifest.py -q`
- RED result: `2 failed, 9 passed`; typed questions were not JSON serializable
  and the manifest still declared `candidate-profile.v1`.
- GREEN commit: `9442f9d`
- GREEN command: same focused command.
- GREEN result: `11 passed`.

The CLI now emits dimension, prompt, and optional fields. Both repository
skills require the interview gate. The adapter contract is
`candidate-profile.v2`; the fork URL and locked commit SHA are unchanged.

### Style-only refactor

- Commit: `a3bb3b7`
- Command:
  `uv run ruff check src tests`
- Result: `All checks passed!`
- Focused regression:
  `uv run pytest tests/unit/test_candidate_profile_adapter.py tests/unit/test_candidate_onboarding.py -q`
- Result: `15 passed`.

## Test Specification

| # | Guarantee | Test target | Type | Result |
|---|---|---|---|---|
| 1 | A first CV task rejects an immediate proposal | `test_first_task_rejects_immediate_proposal` | Unit | PASS |
| 2 | Questions cover every required dimension exactly once | `test_first_task_rejects_invalid_question_coverage` | Unit | PASS |
| 3 | Answers cover every required dimension | `test_answers_require_every_dimension` | Unit | PASS |
| 4 | An answered status cannot contain an empty value | `test_answered_status_requires_non_empty_value` | Unit | PASS |
| 5 | Explicit skip statuses complete optional dimensions | `test_explicit_skip_answers_complete_interview` | Unit | PASS |
| 6 | An invalid proposal is rejected before checkpoint persistence | `test_first_cv_run_rejects_proposal_before_interview` | Integration | PASS |
| 7 | A complete interview permits proposal review and confirmation | `test_complete_interview_then_proposal_can_be_confirmed` | Integration | PASS |
| 8 | Existing active profiles are reused | `test_later_run_reuses_active_profile_without_new_task` | Unit | PASS |
| 9 | Explicit source-backed updates repeat the interview gate | `test_explicit_update_creates_new_task_and_v2` | Integration | PASS |
| 10 | CLI questions are machine-readable typed objects | `test_profile_prepare_prints_machine_readable_checkpoint` | Unit | PASS |
| 11 | Manifest pins v2 contract without changing the fork SHA | `test_manifest_locks_approved_forks_and_required_capabilities` | Unit | PASS |
| 12 | Evaluation still requires a confirmed profile | `test_evaluation_requires_confirmed_profile` | Integration | PASS |

## Full Verification

Commands:

```text
uv run ruff check src tests
uv run pytest -m "not e2e" -q
uv run pytest -m "not e2e" --cov=src --cov-branch --cov-report=term-missing -q
uv run python scripts/privacy_guard.py
git diff --check
```

Results:

- Ruff: PASS
- Non-E2E suite: `501 passed, 1 skipped, 20 deselected`
- Coverage suite: `501 passed, 1 skipped, 20 deselected`
- Combined statement and branch coverage: `84.24%`
- Required coverage: `80.0%`
- Privacy guard: PASS
- Git diff check: PASS

## Warnings and Known Gaps

- Two existing Pydantic v1-style validator deprecation warnings remain in
  `config/settings.py`.
- Existing tests expose legacy SQLite connection `ResourceWarning` messages.
  They predate this change and do not affect the candidate interview contract.
- Browser E2E tests are intentionally deselected for this non-browser profile
  workflow.
- The supplied real resume run is a private post-verification checkpoint and
  is not reproduced in tracked fixtures or this report.

## Privacy

No PDF text, contact details, candidate answers, source-document copy, raw
checkpoint payload, database file, cookie, browser profile, log, or screenshot
is tracked by this evidence. The two unmodified integration checkouts remain
ignored runtime dependencies.
