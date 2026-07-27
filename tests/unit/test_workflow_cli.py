import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.application.candidate_onboarding import OnboardingStatus
from src.domain.candidate_interview import (
    InterviewDimension,
    InterviewQuestion,
)
from src.main import app

runner = CliRunner()


class FakeWorkflow:
    def prepare_profile(self, run_id, sources, *, update):
        return SimpleNamespace(
            status=OnboardingStatus.WAITING_FOR_AGENT,
            profile_version=None,
            task_id="profile-task-1",
            proposal_id=None,
            questions=(
                InterviewQuestion(
                    dimension=InterviewDimension.BEHAVIORAL_STYLE,
                    prompt="How do you prefer to work?",
                    optional=False,
                ),
            ),
        )

    def submit_profile_result(self, run_id, task_id, payload):
        return SimpleNamespace(
            status=OnboardingStatus.WAITING_FOR_USER,
            profile_version=None,
            task_id=task_id,
            proposal_id="proposal-1",
            questions=(),
        )

    def prepare_evaluations(self, run_id):
        pending = SimpleNamespace(
            snapshot_id="1",
            task=SimpleNamespace(task_id="evaluation-task-1"),
        )
        return SimpleNamespace(cached=(), pending=(pending,))

    def submit_evaluation_result(self, task_id, payload):
        return SimpleNamespace(
            id="evaluation-1",
            job_snapshot_id="1",
            overall_score=4.2,
        )

    def report(self):
        return "JobsDB Evaluation Report (1 jobs)"


def test_profile_prepare_prints_machine_readable_checkpoint(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.main._build_candidate_evaluation_workflow",
        lambda: FakeWorkflow(),
    )

    result = runner.invoke(app, [
        "workflow",
        "profile-prepare",
        "--run-id",
        "run-1",
        "--source",
        "workspace/candidate/cv.md",
    ])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "waiting_for_agent"
    assert payload["task_id"] == "profile-task-1"
    assert payload["questions"] == [
        {
            "dimension": "behavioral_style",
            "prompt": "How do you prefer to work?",
            "optional": False,
        }
    ]


def test_profile_submit_reads_private_json_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "src.main._build_candidate_evaluation_workflow",
        lambda: FakeWorkflow(),
    )
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({
            "kind": "proposal",
            "task_id": "profile-task-1",
            "profile": {},
        }),
        encoding="utf-8",
    )

    result = runner.invoke(app, [
        "workflow",
        "profile-submit",
        "--run-id",
        "run-1",
        "--task-id",
        "profile-task-1",
        "--result",
        str(result_file),
    ])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["proposal_id"] == "proposal-1"


def test_evaluation_prepare_prints_pending_task_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.main._build_candidate_evaluation_workflow",
        lambda: FakeWorkflow(),
    )

    result = runner.invoke(app, [
        "workflow",
        "evaluation-prepare",
        "--run-id",
        "run-1",
    ])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "cached": 0,
        "pending": [{
            "snapshot_id": "1",
            "task_id": "evaluation-task-1",
        }],
    }


def test_workflow_report_is_human_readable(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.main._build_candidate_evaluation_workflow",
        lambda: FakeWorkflow(),
    )

    result = runner.invoke(app, ["workflow", "report"])

    assert result.exit_code == 0
    assert "JobsDB Evaluation Report" in result.stdout


def test_agent_protocol_uses_native_profile_loading_order() -> None:
    expected = (
        "config/profile.yml → modes/_shared.md → "
        "modes/_profile.md → modes/oferta.md → cv.md"
    )
    for path in (
        Path(".agents/skills/jobsdb-assistant/SKILL.md"),
        Path(".claude/skills/jobsdb-assistant/SKILL.md"),
    ):
        instructions = path.read_text(encoding="utf-8")
        assert "profile_context_paths" in instructions
        assert expected in instructions
        assert "embedded confirmed profile" not in instructions
