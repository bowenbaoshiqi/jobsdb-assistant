# README Product Image TDD Evidence

## Source

The user requested that a real JobsDB Assistant Dashboard screenshot be added
to the README and published through a pull request.

## User journey

As a prospective user, I want to see a real product screenshot near the
architecture overview so that I can understand the local Dashboard before
installing the project.

As a repository maintainer, I want only the explicitly approved README image
to bypass the generated-image privacy rule so that unrelated screenshots
remain blocked from the public repository.

## RED/GREEN report

| Stage | Command | Result | Evidence |
|---|---|---|---|
| RED | `uv run pytest tests/unit/test_privacy.py::test_guard_allows_only_approved_readme_product_image -q` | FAIL | Both the approved image path and an unrelated PNG were reported as sensitive generated files. |
| GREEN | `uv run pytest tests/unit/test_privacy.py -q` | PASS | Five privacy tests passed; only the exact README product-image path is allowed. |
| Documentation | `uv run pytest tests/unit/test_dashboard_documentation.py -q` | PASS | The reorganized README contract remains valid after adding the product section. |
| Privacy gate | `uv run python scripts/privacy_guard.py` | PASS | The approved product image is publishable and no other tracked privacy finding exists. |
| Lint | `uv run ruff check src/privacy.py tests/unit/test_privacy.py scripts/privacy_guard.py` | PASS | The focused source and test changes satisfy lint rules. |

## Test specification

| # | Guarantee | Test | Type | Result |
|---|---|---|---|---|
| 1 | The approved product screenshot path is publishable. | `test_guard_allows_only_approved_readme_product_image` | Unit | PASS |
| 2 | A different PNG under the same documentation directory remains blocked. | `test_guard_allows_only_approved_readme_product_image` | Unit | PASS |
| 3 | Existing private runtime paths and generated documents remain blocked. | `test_guard_rejects_private_runtime_paths` | Unit | PASS |
| 4 | The README continues to document the supported Dashboard workflow. | `test_readme_documents_reproducible_local_dashboard` | Documentation contract | PASS |

## Coverage and known gaps

Focused command:

```text
uv run pytest tests/unit/test_privacy.py tests/unit/test_dashboard_documentation.py \
  --cov=src.privacy --cov-branch --cov-report=term-missing -q
```

Result: 10 tests passed and `src/privacy.py` reached 90.59% combined
line-and-branch coverage. The screenshot itself was also inspected visually;
it contains job and product UI data but no account, resume, credential, local
path, or browser-login information.

## Merge evidence

- RED checkpoint: `ff2c7d1 test: require exact public product image allowlist`
- GREEN checkpoint: `cbf6e5a docs: add approved Dashboard product screenshot`
