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
    assert "v0.6.0" in readme
    assert "仅定制求职信" in readme
    assert "定制简历 + 求职信" in readme
    assert "不删除、上传或切换简历" in readme
    assert "100–300" in readme
    assert "Reviewer" in readme
    assert "ATS" in readme
    assert "事实一致性" in readme
    assert "批准" in readme
    assert "拒绝" in readme
    assert "重新生成" in readme
    assert "Professional Summary" in readme
    assert "Career Highlights" in readme
    assert "Core Competencies" in readme
    assert "保留默认简历、删除其他非默认简历" in readme
    assert "确认提交" in readme
    assert "workspace/materials/" in readme


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
    assert "Professional Summary" in instructions
    assert "Career Highlights" in instructions
    assert "Core Competencies" in instructions
    assert "material_mode" in instructions
    assert "cover_letter_only" in instructions
    assert "tailored_resume_and_cover_letter" in instructions
    assert "`material_mode` into the result unchanged" in instructions
    assert "keeps the JobsDB default resume" in instructions
    assert "must not confirm submission" in instructions


def test_claude_skill_delegates_dashboard_rules() -> None:
    instructions = Path(
        ".claude/skills/jobsdb-assistant/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "dashboard doctor" in instructions
    assert "dashboard start" in instructions
    assert "Dashboard confirmation" in instructions


def test_ci_never_uploads_private_material_artifacts() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "upload-artifact" not in workflow
    assert "workspace/materials" not in workflow
