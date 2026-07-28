import json
from datetime import UTC, datetime
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


class FakeMaterialService:
    def __init__(self):
        self.repository = SimpleNamespace(
            list_pending=lambda: [
                SimpleNamespace(
                    id="material-task-1",
                    batch_id="batch-1",
                    job_id="job-1",
                    target_version=1,
                    status=SimpleNamespace(value="waiting_for_agent"),
                    error_message=None,
                )
            ],
            list_batch=lambda batch_id: [
                SimpleNamespace(
                    id="material-task-1",
                    batch_id=batch_id,
                    job_id="job-1",
                    target_version=1,
                    status=SimpleNamespace(value="generated"),
                    error_message=None,
                )
            ],
        )

    def load_pending(self, task_id):
        return SimpleNamespace(task=SimpleNamespace(task_id=task_id))

    def submit(self, pending, payload, *, completed_at):
        return SimpleNamespace(
            id="package-1",
            job_id="job-1",
            version=1,
            review_status=SimpleNamespace(value="pending_review"),
        )


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


def test_evaluation_next_claims_one_dashboard_task(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    progress_path = Path(
        "workspace/dashboard/evaluation-progress.json"
    )
    from src.dashboard.evaluation_progress import EvaluationProgressStore

    EvaluationProgressStore(progress_path).start(
        ["evaluation-task-1", "evaluation-task-2"],
        now=datetime(2026, 7, 28, tzinfo=UTC),
    )

    result = runner.invoke(app, [
        "workflow",
        "evaluation-next",
    ])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "status": "claimed",
        "task_id": "evaluation-task-1",
        "task_path": (
            "workspace/ai-tasks/evaluation-task-1/task.json"
        ),
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


def test_material_pending_and_progress_are_machine_readable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.main._build_material_generation_service",
        FakeMaterialService,
    )

    pending = runner.invoke(app, ["workflow", "material-pending"])
    progress = runner.invoke(
        app,
        ["workflow", "material-progress", "--batch-id", "batch-1"],
    )

    assert pending.exit_code == 0
    assert json.loads(pending.stdout)["pending"][0]["task_id"] == (
        "material-task-1"
    )
    assert progress.exit_code == 0
    assert json.loads(progress.stdout)["counts"] == {"generated": 1}


def test_material_submit_reads_result_and_reports_review_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "src.main._build_material_generation_service",
        FakeMaterialService,
    )
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({"task_id": "material-task-1"}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "workflow",
            "material-submit",
            "--task-id",
            "material-task-1",
            "--result",
            str(result_file),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "status": "saved",
        "package_id": "package-1",
        "job_id": "job-1",
        "material_version": 1,
        "review_status": "pending_review",
    }
