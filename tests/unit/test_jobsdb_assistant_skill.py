from pathlib import Path

SKILLS = (
    Path(".agents/skills/jobsdb-assistant/SKILL.md"),
    Path(".claude/skills/jobsdb-assistant/SKILL.md"),
)


def test_both_skills_use_only_unified_agent_commands() -> None:
    forbidden = (
        "workflow evaluation-next",
        "workflow evaluation-submit",
        "workflow material-pending",
        "workflow material-submit",
        "workspace/ai-tasks/<task_id>",
        "poll `/api/job-batch`",
    )
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        assert "agent start" in text
        assert "agent next" in text
        assert "agent submit" in text
        assert "work_id" in text
        assert all(item not in text for item in forbidden)


def test_both_skills_treat_idle_as_continued_listening() -> None:
    for path in SKILLS:
        text = path.read_text(encoding="utf-8").casefold()
        assert "idle is not completion" in text
        assert "agent stop" in text
        assert "explicit" in text


def test_skills_preserve_human_approval_boundaries() -> None:
    for path in SKILLS:
        text = path.read_text(encoding="utf-8")
        assert "human_required" in text
        assert "Quick Apply" in text
        assert "验证码" in text
