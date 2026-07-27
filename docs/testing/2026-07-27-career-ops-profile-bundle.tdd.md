# Career-Ops Native Profile Bundle TDD Evidence

Date: 2026-07-27  
Scope: v0.3.0 candidate synthesis, native career-ops projection, and
bundle-backed job evaluation

## Design and plan

- Design:
  `docs/superpowers/specs/2026-07-27-career-ops-profile-bundle-design.md`
- Execution plan:
  `docs/superpowers/plans/2026-07-27-career-ops-profile-bundle.md`

Both pinned public forks remained unchanged:

- ai-job-search:
  `aa7c7073990492c9111fbdda48f6adde24a1d91b`
- career-ops:
  `01bf8b469ad5177a9c30230bc00509ead8e006c2`

## RED/GREEN checkpoints

| Area | RED commit | GREEN commit |
|---|---|---|
| Canonical candidate contract | `c5ca3aa` | `b80e284` |
| Complete synthesis persistence | `726dd45` | `be970d7` |
| Native profile bundle | `80a937d` | `a19d81e` |
| Bundle-backed evaluation | `52e089b` | `b76d214` |
| Workflow protocol | `b390e0d` | `eb96def` |
| Intent completeness regression | `158844d` | `3fc43f9` |
| Runtime projector wiring | `bd1c335` | `777b911` |

Each RED checkpoint was run before its implementation and failed for the
missing behavior. Focused GREEN suites passed after implementation.

## Verification

- `uv run ruff check src tests`: passed.
- `uv run pytest -m "not e2e" -q`: passed before the final release gate.
- `uv run pytest -m "not e2e" --cov=src --cov-branch
  --cov-report=term -q`: 526 passed, 1 skipped, 20 deselected; total
  coverage 85.24%.
- Native profile focused suite after the final regression:
  9 passed.
- Runtime construction and workflow focused suite:
  5 passed after reproducing the real CLI wiring failure.
- Both repository skill directories passed `quick_validate.py`.
- `uv run python scripts/privacy_guard.py`: passed.
- `git diff --check`: passed.
- Both pinned integrations passed local commit and required-path checks.

Known warnings are pre-existing Pydantic v1-validator deprecations and test
resource warnings from legacy browser/application coverage tests. They do not
change the result of this feature verification.

## Privacy and integrity guarantees

- Candidate bundles are written only below ignored
  `workspace/career-ops-profiles/`.
- Bundle directories are content-addressed, atomically created, private by
  filesystem permissions, and verified before reuse.
- Candidate content is never written below `integrations/`.
- The projection manifest hashes each native input and records canonical
  field and answer-hash provenance.
- Legacy profile JSON remains readable for compatibility. Local profile
  retention or deletion is a user-controlled runtime-data decision.
