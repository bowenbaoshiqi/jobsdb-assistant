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

Each RED checkpoint was run before its implementation and failed for the
missing behavior. Focused GREEN suites passed after implementation.

## Verification

- `uv run ruff check src tests`: passed.
- `uv run pytest -m "not e2e" -q`: 523 passed, 1 skipped,
  20 deselected before the final intent-completeness regression.
- `uv run pytest -m "not e2e" --cov=src --cov-branch
  --cov-report=term -q`: 523 passed, total coverage 84.64%.
- Native profile focused suite after the final regression:
  9 passed.
- Final full non-E2E regression after all changes:
  525 passed, 1 skipped, 20 deselected.
- Both repository skill directories passed `quick_validate.py`.
- `uv run python scripts/privacy_guard.py`: passed.
- `git diff --check`: passed.

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
- Existing profile v1 remains historical. A complete v2 profile requires an
  explicit update interview and user confirmation.
