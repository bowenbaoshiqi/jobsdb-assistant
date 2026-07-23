from pathlib import Path


def test_ci_enforces_privacy_branch_coverage_and_lint() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text()
    project = Path("pyproject.toml").read_text()

    assert "python scripts/privacy_guard.py" in workflow
    assert "--cov-branch" in workflow
    assert "--cov=src" in workflow
    assert "ruff check src/ tests/ scripts/privacy_guard.py" in workflow
    assert "upload-artifact" not in workflow
    assert '"pytest-cov' in project
