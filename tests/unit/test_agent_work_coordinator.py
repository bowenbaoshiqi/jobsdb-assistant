import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.application.agent_work_coordinator import AgentWorkCoordinator
from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
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
) -> None:
    directory = root / task_id
    directory.mkdir(parents=True)
    (directory / "task.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "capability_paths": capabilities,
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
