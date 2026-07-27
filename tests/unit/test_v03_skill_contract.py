from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "path",
    [
        Path(".agents/skills/jobsdb-assistant/SKILL.md"),
        Path(".claude/skills/jobsdb-assistant/SKILL.md"),
    ],
)
def test_skill_uses_python_as_state_authority(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    assert "workflow profile-prepare" in text
    assert "workflow profile-submit" in text
    assert "workflow profile-confirm" in text
    assert "discover --keyword" in text
    assert "workflow evaluation-prepare" in text
    assert "workflow evaluation-submit" in text
    assert "workflow report" in text
    assert "Python and SQLite are the state authority" in text
    assert "git pull" not in text
    assert "codex exec" not in text
    assert "claude -p" not in text


def test_canonical_skill_never_runs_application_execution() -> None:
    text = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "python -m src.main start" not in text
    assert "Quick Apply submission" not in text
