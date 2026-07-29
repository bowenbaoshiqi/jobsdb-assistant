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
    assert "workflow evaluation-next" in text
    assert "简体中文 JD 摘要" in text
    assert "workflow report" in text
    assert "workflow material-pending" in text
    assert "workflow material-submit" in text
    assert "workflow material-progress" in text
    assert "Python and SQLite are the state authority" in text
    assert "v0.6 application execution" in text
    assert "API key" not in text
    assert "continue other material tasks" in text
    assert "waiting_for_agent" in text
    assert "git pull" not in text
    assert "codex exec" not in text
    assert "claude -p" not in text


def test_canonical_skill_never_confirms_application_for_user() -> None:
    text = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "python -m src.main start" not in text
    assert "must not confirm submission" in text


def test_canonical_skill_drains_only_current_batch_evaluations() -> None:
    text = Path(
        ".agents/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "workspace/dashboard/evaluation-progress.json" in text
    assert "whose status is `queued`" in text
    assert "historical `workspace/ai-tasks` directory" in text
    assert "/api/job-batch" in text
    assert "reports `scored`" in text
    assert "MUST NOT send a final response" in text
    assert "queued or running" in text
