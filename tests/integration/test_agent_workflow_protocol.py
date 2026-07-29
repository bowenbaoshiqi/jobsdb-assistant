import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from src.application.agent_runtime import (
    RuntimeAgentWorkDispatcher,
    RuntimeAgentWorkSources,
)
from src.application.agent_work_coordinator import AgentWorkCoordinator
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database
from src.storage.job_batch_repository import JobBatchRepository
from src.storage.material_repository import MaterialRepository


def _task(root, task_id: str, *, capability: str) -> None:
    directory = root / task_id
    directory.mkdir(parents=True)
    (directory / "task.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "capability_paths": [capability],
            }
        ),
        encoding="utf-8",
    )


def test_current_dashboard_evaluations_flow_through_one_agent_session(
    tmp_path,
) -> None:
    now = datetime.now(UTC)
    database = Database(str(tmp_path / "jobs.db"))
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _task(
        tasks_root,
        "evaluation-current",
        capability="integrations/job-evaluation/capability.md",
    )
    progress = EvaluationProgressStore(
        tmp_path / "workspace" / "dashboard" / "progress.json"
    )
    progress.start(["evaluation-current"], now=now)
    dispatcher = Mock()
    coordinator = AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=RuntimeAgentWorkSources(
            progress=progress,
            materials=MaterialRepository(database),
        ),
        dispatcher=dispatcher,
        tasks_root=tasks_root,
        sleeper=lambda _seconds: None,
    )

    session = coordinator.start(now=now)
    claimed = coordinator.next(session.id, wait_seconds=0, now=now)
    assert claimed.state is AgentWorkStatus.CLAIMED
    assert claimed.work is not None
    assert claimed.work.kind is AgentWorkKind.JOB_EVALUATION
    claimed.work.result_path.write_text('{"score": 4.0}', encoding="utf-8")

    completed = coordinator.submit(
        session_id=session.id,
        work_id=claimed.work.work_id,
        result_path=claimed.work.result_path,
        now=now,
    )

    assert completed.status is AgentWorkStatus.COMPLETED
    dispatcher.submit_evaluation.assert_called_once_with(
        "evaluation-current",
        {"score": 4.0},
    )


def test_new_coordinator_resumes_claimed_work_exactly_once(tmp_path) -> None:
    now = datetime.now(UTC)
    database = Database(str(tmp_path / "jobs.db"))
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _task(
        tasks_root,
        "evaluation-current",
        capability="integrations/job-evaluation/capability.md",
    )
    progress = EvaluationProgressStore(tmp_path / "progress.json")
    progress.start(["evaluation-current"], now=now)
    sources = RuntimeAgentWorkSources(
        progress=progress,
        materials=MaterialRepository(database),
    )
    first = AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=sources,
        dispatcher=Mock(),
        tasks_root=tasks_root,
        sleeper=lambda _seconds: None,
    )
    session = first.start(now=now)
    initial = first.next(session.id, wait_seconds=0, now=now)
    assert initial.work is not None

    second = AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=sources,
        dispatcher=Mock(),
        tasks_root=tasks_root,
        sleeper=lambda _seconds: None,
    )
    resumed_session = second.start(now=now + timedelta(seconds=1))
    resumed = second.next(
        resumed_session.id,
        wait_seconds=0,
        now=now + timedelta(seconds=1),
    )

    assert resumed_session.id == session.id
    assert resumed.work is not None
    assert resumed.work.work_id == initial.work.work_id
    assert resumed.work.attempt == 1


def test_runtime_dispatch_marks_completed_batch_scored(tmp_path) -> None:
    now = datetime.now(UTC)
    database = Database(str(tmp_path / "jobs.db"))
    batches = JobBatchRepository(database)
    batch = batches.create("AI Lead", now=now)
    batches.mark_scoring(batch.id)
    progress = EvaluationProgressStore(tmp_path / "progress.json")
    progress.start(["evaluation-current"], now=now)
    workflow = Mock()
    workflow.submit_evaluation_result.return_value = Mock(id="evaluation-1")
    dispatcher = RuntimeAgentWorkDispatcher(
        database=database,
        progress=progress,
        workflow=workflow,
        materials=Mock(),
    )

    dispatcher.submit_evaluation(
        "evaluation-current",
        {"task_id": "evaluation-current"},
    )

    assert progress.get().completed == 1
    assert batches.current().status == "scored"


def test_dashboard_material_tasks_reach_the_same_agent_session(
    tmp_path,
) -> None:
    now = datetime.now(UTC)
    database = Database(str(tmp_path / "jobs.db"))
    tasks_root = tmp_path / "workspace" / "ai-tasks"
    _task(
        tasks_root,
        "material-current",
        capability="integrations/candidate-profile/material.md",
    )
    materials = MaterialRepository(database)
    materials.create_task(
        task_id="material-current",
        batch_id="materials-batch",
        job_id="job-1",
        snapshot_id=1,
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={"task_id": "material-current"},
        created_at=now,
    )
    progress = EvaluationProgressStore(tmp_path / "progress.json")
    coordinator = AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=RuntimeAgentWorkSources(
            progress=progress,
            materials=materials,
        ),
        dispatcher=Mock(),
        tasks_root=tasks_root,
        sleeper=lambda _seconds: None,
    )
    session = coordinator.start(now=now)

    claimed = coordinator.next(session.id, wait_seconds=0, now=now)

    assert claimed.state is AgentWorkStatus.CLAIMED
    assert claimed.work is not None
    assert claimed.work.kind is AgentWorkKind.APPLICATION_MATERIAL
