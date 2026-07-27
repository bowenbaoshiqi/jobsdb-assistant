from pathlib import Path


def test_readme_documents_reproducible_local_dashboard() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "uv sync --extra dev --extra dashboard" in readme
    assert "uv pip list" in readme
    assert "dashboard doctor" in readme
    assert "dashboard start" in readme
    assert "127.0.0.1" in readme
    assert "JobsDB default CV" in readme
    assert "no cover letter" in readme
    assert "Ctrl+C" in readme


def test_canonical_skill_starts_dashboard_without_auto_clicking() -> None:
    instructions = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "dashboard doctor" in instructions
    assert "dashboard start" in instructions
    assert "Keep the foreground Agent session active" in instructions
    assert "must not click or call the Quick Apply endpoint" in instructions
    assert "JobsDB default CV" in instructions
    assert "no cover letter" in instructions


def test_claude_skill_delegates_dashboard_rules() -> None:
    instructions = Path(
        ".claude/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "dashboard doctor" in instructions
    assert "dashboard start" in instructions
    assert "Dashboard confirmation" in instructions
