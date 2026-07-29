from datetime import UTC, datetime
from unittest.mock import Mock

from src.application.agent_runtime import RuntimeAgentWorkSources
from src.application.agent_work_coordinator import AgentWorkCoordinator
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.domain.agent_work import AgentWorkStatus
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository


def test_pool_failure_requeues_once_then_becomes_terminal(tmp_path) -> None:
    now = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)
    database = Database(str(tmp_path / "jobs.db"))
    task_root = tmp_path / "tasks"
    task_root.mkdir()
    task_id = "evaluation-retry"
    task_dir = task_root / task_id
    task_dir.mkdir()
    (task_dir / "task.json").write_text(
        '{"task_id":"evaluation-retry","capability_paths":[]}',
        encoding="utf-8",
    )
    progress = EvaluationProgressStore(tmp_path / "progress.json")
    progress.start([task_id], now=now)
    coordinator = AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=RuntimeAgentWorkSources(
            progress=progress,
            materials=MaterialRepository(database),
        ),
        dispatcher=Mock(),
        tasks_root=task_root,
        sleeper=lambda _seconds: None,
    )
    session = coordinator.start(now=now)
    pool = coordinator.pool_start(
        session_id=session.id,
        now=now,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
    )
    for slot in pool.slots:
        coordinator.pool_ready(
            pool_id=pool.id,
            slot_token=slot.slot_token,
            capability_context_id="cap-v1",
            profile_context_id="profile-v1",
            now=now,
        )
    claimed = coordinator.pool_claim(
        session_id=session.id,
        pool_id=pool.id,
        slot_token=pool.slots[0].slot_token,
        now=now,
    )
    assert claimed is not None

    first = coordinator.fail(
        session_id=session.id,
        work_id=claimed.id,
        error_message="transient worker error",
        now=now,
    )
    assert first.status is AgentWorkStatus.QUEUED
    retried = coordinator.pool_claim(
        session_id=session.id,
        pool_id=pool.id,
        slot_token=pool.slots[0].slot_token,
        now=now,
    )
    assert retried is not None
    second = coordinator.fail(
        session_id=session.id,
        work_id=retried.id,
        error_message="schema error",
        now=now,
    )
    assert second.status is AgentWorkStatus.FAILED
