from datetime import UTC, datetime, timedelta

import pytest

from src.domain.agent_work import (
    AgentSessionStatus,
    AgentWorkKind,
    AgentWorkStatus,
)
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database


def _enqueue(
    repository: AgentWorkRepository,
    *,
    now: datetime,
    internal_key: str = "evaluation:private-task-id",
):
    return repository.enqueue(
        kind=AgentWorkKind.JOB_EVALUATION,
        internal_key=internal_key,
        task_path="workspace/ai-tasks/private-task-id/task.json",
        result_path="workspace/ai-tasks/private-task-id/agent-result.json",
        capability_paths=("integrations/job-evaluation/capability.md",),
        now=now,
    )


def test_enqueue_hides_internal_identity_and_deduplicates(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    session = repository.start_session(now=now)

    first = _enqueue(repository, now=now)
    second = _enqueue(repository, now=now)

    assert first.id == second.id
    assert first.id.startswith("work-")
    assert "private-task-id" not in first.id
    assert first.status is AgentWorkStatus.QUEUED
    assert session.id.startswith("agent-session-")
    assert session.status is AgentSessionStatus.ACTIVE


def test_start_or_resume_reuses_the_active_session(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))

    first = repository.start_or_resume_session(now=now)
    second = repository.start_or_resume_session(
        now=now + timedelta(minutes=1)
    )

    assert second.id == first.id
    assert second.heartbeat_at == now + timedelta(minutes=1)


def test_enqueue_rejects_changed_identity_for_existing_key(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    _enqueue(repository, now=now)

    with pytest.raises(ValueError, match="different data"):
        repository.enqueue(
            kind=AgentWorkKind.JOB_EVALUATION,
            internal_key="evaluation:private-task-id",
            task_path="different/task.json",
            result_path="different/result.json",
            capability_paths=(),
            now=now,
        )


def test_enqueue_reconciles_legacy_relative_capability_paths(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    first = _enqueue(repository, now=now)

    second = repository.enqueue(
        kind=AgentWorkKind.JOB_EVALUATION,
        internal_key="evaluation:private-task-id",
        task_path="workspace/ai-tasks/private-task-id/task.json",
        result_path="workspace/ai-tasks/private-task-id/agent-result.json",
        capability_paths=(
            "/private/project/integrations/job-evaluation/capability.md",
        ),
        now=now + timedelta(seconds=1),
    )

    assert second.id == first.id
    assert second.capability_paths == (
        "/private/project/integrations/job-evaluation/capability.md",
    )


def test_expired_claim_is_recovered_once(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    first_session = repository.start_session(now=now)
    work = _enqueue(repository, now=now)
    first_claim = repository.claim_next(
        first_session.id,
        now=now,
        lease_duration=timedelta(seconds=1),
    )

    second_session = repository.start_session(now=now + timedelta(seconds=2))
    claimed = repository.claim_next(
        second_session.id,
        now=now + timedelta(seconds=2),
        lease_duration=timedelta(minutes=5),
    )

    assert first_claim is not None
    assert claimed is not None
    assert claimed.id == work.id
    assert claimed.attempt == 2
    assert claimed.status is AgentWorkStatus.CLAIMED
    assert claimed.session_id == second_session.id


def test_active_claim_is_returned_to_its_owner(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    session = repository.start_session(now=now)
    _enqueue(repository, now=now)

    first = repository.claim_next(session.id, now=now)
    second = repository.claim_next(
        session.id,
        now=now + timedelta(seconds=1),
    )

    assert first is not None
    assert second == first
    assert second.attempt == 1


def test_duplicate_completion_with_same_hash_is_idempotent(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    session = repository.start_session(now=now)
    work = _enqueue(repository, now=now)
    repository.claim_next(session.id, now=now)

    first = repository.complete(
        session.id,
        work.id,
        result_hash="a" * 64,
        now=now,
    )
    second = repository.complete(
        session.id,
        work.id,
        result_hash="a" * 64,
        now=now,
    )

    assert first == second
    assert first.status is AgentWorkStatus.COMPLETED


def test_duplicate_completion_rejects_a_different_hash(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    session = repository.start_session(now=now)
    work = _enqueue(repository, now=now)
    repository.claim_next(session.id, now=now)
    repository.complete(
        session.id,
        work.id,
        result_hash="a" * 64,
        now=now,
    )

    with pytest.raises(ValueError, match="different result"):
        repository.complete(
            session.id,
            work.id,
            result_hash="b" * 64,
            now=now,
        )


def test_other_session_cannot_complete_an_active_lease(tmp_path) -> None:
    now = datetime.now(UTC)
    repository = AgentWorkRepository(Database(str(tmp_path / "jobs.db")))
    owner = repository.start_session(now=now)
    other = repository.start_session(now=now)
    work = _enqueue(repository, now=now)
    repository.claim_next(owner.id, now=now)

    with pytest.raises(ValueError, match="lease owner"):
        repository.complete(
            other.id,
            work.id,
            result_hash="a" * 64,
            now=now,
        )
