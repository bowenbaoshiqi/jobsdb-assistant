import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.application.agent_work_coordinator import AgentWorkCoordinator
from src.application.candidate_onboarding import (
    OnboardingOutcome,
    OnboardingStatus,
)
from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
from src.domain.candidate_interview import (
    InterviewDimension,
    InterviewQuestion,
)
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database


class FakeSources:
    def __init__(
        self,
        *,
        evaluations: tuple[str, ...] = (),
        materials: tuple[str, ...] = (),
    ) -> None:
        self.evaluations = evaluations
        self.materials = materials

    def current_evaluation_task_ids(self) -> tuple[str, ...]:
        return self.evaluations

    def pending_material_task_ids(self) -> tuple[str, ...]:
        return self.materials


def _write_task(
    root: Path,
    task_id: str,
    *,
    capabilities: tuple[str, ...] = ("integrations/capability.md",),
    integration_id: str | None = None,
) -> None:
    directory = root / task_id
    directory.mkdir(parents=True)
    (directory / "task.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "capability_paths": capabilities,
                "integration_id": integration_id,
            }
        ),
        encoding="utf-8",
    )


def _coordinator(
    tmp_path: Path,
    *,
    sources: FakeSources,
    dispatcher: Mock | None = None,
) -> AgentWorkCoordinator:
    return AgentWorkCoordinator(
        work=AgentWorkRepository(
            Database(str(tmp_path / "jobs.db"))
        ),
        sources=sources,
        dispatcher=dispatcher or Mock(),
        tasks_root=tmp_path / "workspace" / "ai-tasks",
        sleeper=lambda _seconds: None,
    )


def test_sync_pending_enqueues_current_evaluation_tasks_only(
    tmp_path,
) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "evaluation-current")
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(evaluations=("evaluation-current",)),
    )

    created = coordinator.sync_pending(now=datetime.now(UTC))

    assert len(created) == 1
    assert created[0].kind is AgentWorkKind.JOB_EVALUATION
    assert created[0].internal_key == "evaluation:evaluation-current"


def test_sync_pending_enqueues_material_tasks(tmp_path) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "material-current")
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(materials=("material-current",)),
    )

    created = coordinator.sync_pending(now=datetime.now(UTC))

    assert len(created) == 1
    assert created[0].kind is AgentWorkKind.APPLICATION_MATERIAL


def test_next_returns_an_opaque_envelope(tmp_path) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "evaluation-current")
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(evaluations=("evaluation-current",)),
    )
    session = coordinator.start(now=datetime.now(UTC))

    result = coordinator.next(
        session.id,
        wait_seconds=0,
        now=datetime.now(UTC),
    )

    assert result.state is AgentWorkStatus.CLAIMED
    assert result.work is not None
    assert result.work.work_id.startswith("work-")
    assert "evaluation-current" not in result.work.work_id
    assert result.work.task_path == (
        tasks_root / "evaluation-current" / "task.json"
    )


def test_next_returns_absolute_pinned_capability_paths(tmp_path) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(
        tasks_root,
        "evaluation-current",
        capabilities=("modes/oferta.md",),
        integration_id="job-evaluation",
    )
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(evaluations=("evaluation-current",)),
    )
    session = coordinator.start(now=datetime.now(UTC))

    result = coordinator.next(
        session.id,
        wait_seconds=0,
        now=datetime.now(UTC),
    )

    assert result.work is not None
    assert result.work.capability_paths == (
        (
            tmp_path
            / "integrations"
            / "job-evaluation"
            / "modes"
            / "oferta.md"
        ).resolve(),
    )


def test_start_reuses_the_active_agent_session(tmp_path) -> None:
    coordinator = _coordinator(tmp_path, sources=FakeSources())
    now = datetime.now(UTC)

    first = coordinator.start(now=now)
    second = coordinator.start(now=now)

    assert second.id == first.id


def test_submit_dispatches_by_persisted_kind_not_user_input(tmp_path) -> None:
    now = datetime.now(UTC)
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "evaluation-current")
    dispatcher = Mock()
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(evaluations=("evaluation-current",)),
        dispatcher=dispatcher,
    )
    session = coordinator.start(now=now)
    claimed = coordinator.next(session.id, wait_seconds=0, now=now)
    assert claimed.work is not None
    result_path = claimed.work.result_path
    result_path.write_text('{"valid": true}', encoding="utf-8")

    completed = coordinator.submit(
        session_id=session.id,
        work_id=claimed.work.work_id,
        result_path=result_path,
        now=now,
    )

    dispatcher.submit_evaluation.assert_called_once_with(
        "evaluation-current",
        {"valid": True},
    )
    assert completed.status is AgentWorkStatus.COMPLETED


def test_submit_rejects_a_different_result_path(tmp_path) -> None:
    now = datetime.now(UTC)
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "evaluation-current")
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(evaluations=("evaluation-current",)),
    )
    session = coordinator.start(now=now)
    claimed = coordinator.next(session.id, wait_seconds=0, now=now)
    assert claimed.work is not None
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="result path"):
        coordinator.submit(
            session_id=session.id,
            work_id=claimed.work.work_id,
            result_path=other,
            now=now,
        )


def test_prepare_profile_queues_the_python_returned_task(tmp_path) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "profile-current")
    task = json.loads(
        (tasks_root / "profile-current" / "task.json").read_text(
            encoding="utf-8"
        )
    )
    task["interview_complete"] = False
    (tasks_root / "profile-current" / "task.json").write_text(
        json.dumps(task),
        encoding="utf-8",
    )
    dispatcher = Mock()
    dispatcher.prepare_profile.return_value = OnboardingOutcome(
        status=OnboardingStatus.WAITING_FOR_AGENT,
        task_id="profile-current",
    )
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(),
        dispatcher=dispatcher,
    )

    record = coordinator.prepare_profile(
        source_documents=("/private/resume.pdf",),
        update=False,
        now=datetime.now(UTC),
    )

    assert record is not None
    assert record.kind is AgentWorkKind.CANDIDATE_QUESTIONS
    assert record.metadata["source_documents"] == ["/private/resume.pdf"]
    assert "run_id" in record.metadata


def test_prepare_profile_reuses_unfinished_profile_work(tmp_path) -> None:
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "profile-current")
    task_path = tasks_root / "profile-current" / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["interview_complete"] = False
    task_path.write_text(json.dumps(task), encoding="utf-8")
    dispatcher = Mock()
    dispatcher.prepare_profile.return_value = OnboardingOutcome(
        status=OnboardingStatus.WAITING_FOR_AGENT,
        task_id="profile-current",
    )
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(),
        dispatcher=dispatcher,
    )
    now = datetime.now(UTC)

    first = coordinator.prepare_profile(
        source_documents=("/private/resume.pdf",),
        update=False,
        now=now,
    )
    second = coordinator.prepare_profile(
        source_documents=("/private/resume.pdf",),
        update=False,
        now=now,
    )

    assert second == first
    dispatcher.prepare_profile.assert_called_once()


def test_profile_questions_become_a_human_gate(tmp_path) -> None:
    now = datetime.now(UTC)
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _write_task(tasks_root, "profile-current")
    task = json.loads(
        (tasks_root / "profile-current" / "task.json").read_text(
            encoding="utf-8"
        )
    )
    task["interview_complete"] = False
    (tasks_root / "profile-current" / "task.json").write_text(
        json.dumps(task),
        encoding="utf-8",
    )
    dispatcher = Mock()
    dispatcher.prepare_profile.return_value = OnboardingOutcome(
        status=OnboardingStatus.WAITING_FOR_AGENT,
        task_id="profile-current",
    )
    dispatcher.submit_profile_result.return_value = OnboardingOutcome(
        status=OnboardingStatus.NEEDS_ANSWERS,
        task_id="profile-current",
        questions=(
            InterviewQuestion(
                dimension=InterviewDimension.CAREER_GOALS,
                prompt="What role do you want next?",
            ),
        ),
    )
    coordinator = _coordinator(
        tmp_path,
        sources=FakeSources(),
        dispatcher=dispatcher,
    )
    session = coordinator.start(now=now)
    coordinator.prepare_profile(
        source_documents=("/private/resume.pdf",),
        update=False,
        now=now,
    )
    claimed = coordinator.next(session.id, wait_seconds=0, now=now)
    assert claimed.work is not None
    claimed.work.result_path.write_text(
        json.dumps({"task_id": "profile-current", "kind": "questions"}),
        encoding="utf-8",
    )

    coordinator.submit(
        session_id=session.id,
        work_id=claimed.work.work_id,
        result_path=claimed.work.result_path,
        now=now,
    )
    gate = coordinator.next(session.id, wait_seconds=0, now=now)

    assert gate.state is AgentWorkStatus.HUMAN_REQUIRED
    assert gate.work is not None
    prompt = json.loads(gate.work.prompt_path.read_text(encoding="utf-8"))
    assert prompt["action"] == "candidate_interview_answers"
    assert prompt["questions"][0]["dimension"] == "career_goals"
