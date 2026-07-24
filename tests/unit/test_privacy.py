from pathlib import Path

from src.privacy import scan_tracked_files


def test_guard_rejects_private_runtime_paths(tmp_path: Path) -> None:
    findings = scan_tracked_files(
        tmp_path,
        tracked=[
            "data/jobsdb.db",
            "workspace/applications/42/cv.pdf",
            "integrations/candidate-profile/CLAUDE.md",
            "integrations/job-evaluation/modes/oferta.md",
            "accounts/personal.json",
            ".env",
            ".claude/settings.local.json",
        ],
    )

    assert {finding.path for finding in findings} == {
        "data/jobsdb.db",
        "workspace/applications/42/cv.pdf",
        "integrations/candidate-profile/CLAUDE.md",
        "integrations/job-evaluation/modes/oferta.md",
        "accounts/personal.json",
        ".env",
        ".claude/settings.local.json",
    }


def test_guard_allows_public_examples_and_source(tmp_path: Path) -> None:
    tracked = [
        ".env.example",
        "accounts/example.json",
        "src/main.py",
        "tests/fixtures/synthetic_job.json",
        "integrations/manifest.json",
        ".agents/skills/jobsdb-assistant/SKILL.md",
    ]

    assert scan_tracked_files(tmp_path, tracked=tracked) == []


def test_guard_rejects_secret_shaped_content(tmp_path: Path) -> None:
    secret_file = tmp_path / "config.py"
    synthetic_token = "ghp_" + "123456789012345678901234567890123456"
    secret_file.write_text(f"TOKEN = '{synthetic_token}'\n")

    findings = scan_tracked_files(tmp_path, tracked=["config.py"])

    assert [(finding.path, finding.reason) for finding in findings] == [
        ("config.py", "secret-like content")
    ]


def test_guard_does_not_report_synthetic_placeholders(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        "JOBSDB_EMAIL=your-email@example.com\nJOBSDB_PASSWORD=change-me\n"
    )

    assert scan_tracked_files(tmp_path, tracked=[".env.example"]) == []
