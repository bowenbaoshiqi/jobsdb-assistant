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

    assert "agent doctor" in text
    assert "agent start" in text
    assert "agent listen" in text
    assert "agent next" in text
    assert "agent submit" in text
    assert "agent fail" in text
    assert "agent stop" in text
    assert "agent pool start" in text
    assert "agent pool ready" in text
    assert "agent pool claim" in text
    assert "agent pool heartbeat" in text
    assert "requested_concurrency=3" in text
    assert "nested" in text.casefold()
    assert "Simplified Chinese" in text
    assert "Python and SQLite own" in text
    assert "API key" not in text
    assert "continue" in text.casefold()
    assert "human_required" in text
    assert "git pull" not in text
    assert "codex exec" not in text
    assert "claude -p" not in text


def test_canonical_skill_never_confirms_application_for_user() -> None:
    text = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "python -m src.main start" not in text
    assert "Never call a Quick Apply" in text
    assert "final submission confirmation" in text


def test_canonical_skill_drains_only_current_batch_evaluations() -> None:
    text = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "agent next" in text
    assert "Do not" in text
    assert "scan task directories" in text
    assert "idle is not completion" in text
    assert "Never send a final response" in text
    assert "work_id" in text
    assert "retry once" in text.casefold()
