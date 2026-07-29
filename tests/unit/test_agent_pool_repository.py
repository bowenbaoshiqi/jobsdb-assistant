from datetime import UTC, datetime, timedelta

from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
from src.storage.agent_pool_repository import AgentPoolRepository
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database

NOW = datetime(2026, 7, 29, 8, 30, tzinfo=UTC)


def _repository(tmp_path):
    database = Database(str(tmp_path / "jobs.db"))
    return database, AgentPoolRepository(database), AgentWorkRepository(database)


def _work(work_repository, index: int, now: datetime = NOW):
    return work_repository.enqueue(
        kind=AgentWorkKind.JOB_EVALUATION,
        internal_key=f"evaluation:task-{index}",
        task_path=f"/private/task-{index}.json",
        result_path=f"/private/result-{index}.json",
        capability_paths=("/private/capability.md",),
        now=now,
    )


def _assignments(work_repository, count: int):
    return tuple(
        (
            _work(work_repository, index).id,
            index,
            (index % 3) + 1,
        )
        for index in range(count)
    )


def _ready_all(pool_repository, pool):
    for slot in pool.slots:
        pool_repository.ready_slot(
            pool.id,
            slot.slot_token,
            capability_context_id=pool.capability_context_id,
            profile_context_id=pool.profile_context_id,
            now=NOW,
        )


def test_pool_start_is_idempotent_and_requires_three_slots(tmp_path) -> None:
    database, pools, work = _repository(tmp_path)
    session = AgentWorkRepository(database).start_session(now=NOW)
    assignments = _assignments(work, 3)

    first = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=assignments,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )
    second = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=assignments,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW + timedelta(seconds=1),
    )

    assert first.id == second.id
    assert len(first.slots) == 3
    assert first.requested_concurrency == 3
    assert pools.claim_for_slot(first.id, first.slots[0].slot_token, now=NOW) is None


def test_pool_claim_requires_all_slots_ready_and_prevents_duplicate_claim(
    tmp_path,
) -> None:
    database, pools, work = _repository(tmp_path)
    session = AgentWorkRepository(database).start_session(now=NOW)
    assignment = _assignments(work, 3)
    pool = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=assignment,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )

    _ready_all(pools, pool)
    first = pools.claim_for_slot(pool.id, pool.slots[0].slot_token, now=NOW)
    duplicate = pools.claim_for_slot(
        pool.id,
        pool.slots[0].slot_token,
        now=NOW + timedelta(seconds=1),
    )

    assert first is not None
    assert first.status is AgentWorkStatus.CLAIMED
    assert duplicate == first


def test_pool_enforces_five_assignments_per_generation(tmp_path) -> None:
    database, pools, work = _repository(tmp_path)
    session = AgentWorkRepository(database).start_session(now=NOW)
    assignment = _assignments(work, 6)
    pool = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=assignment,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )
    _ready_all(pools, pool)

    for index in range(5):
        claimed = pools.claim_for_slot(
            pool.id,
            pool.slots[index % 3].slot_token,
            now=NOW + timedelta(seconds=index),
        )
        assert claimed is not None
        pools.clear_slot(pool.id, pool.slots[index % 3].slot_token, now=NOW)

    slot = pools.get_slot(pool.id, pool.slots[0].slot_token)
    assert slot.assignment_count <= 5


def test_stop_pool_releases_claimed_work(tmp_path) -> None:
    database, pools, work = _repository(tmp_path)
    session = AgentWorkRepository(database).start_session(now=NOW)
    assignment = _assignments(work, 3)
    pool = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=assignment,
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )
    _ready_all(pools, pool)
    claimed = pools.claim_for_slot(pool.id, pool.slots[0].slot_token, now=NOW)
    assert claimed is not None

    released = pools.stop_pool(pool.id, now=NOW + timedelta(seconds=1))

    assert [item.work_id for item in released] == [claimed.id]
    assert work.get(claimed.id).status is AgentWorkStatus.QUEUED


def test_heartbeat_renews_live_slots_and_stale_recovery_requeues_claim(
    tmp_path,
) -> None:
    database, pools, work = _repository(tmp_path)
    session = AgentWorkRepository(database).start_session(now=NOW)
    pool = pools.start_pool(
        session_id=session.id,
        batch_key="batch-1",
        assignments=_assignments(work, 3),
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )
    _ready_all(pools, pool)
    claimed = pools.claim_for_slot(pool.id, pool.slots[0].slot_token, now=NOW)
    assert claimed is not None

    renewed = pools.heartbeat(
        pool.id,
        live_slot_tokens=(pool.slots[0].slot_token,),
        now=NOW + timedelta(seconds=30),
    )
    assert renewed == 1

    recovered = pools.release_stale(
        pool.id,
        now=NOW + timedelta(seconds=121),
    )

    assert [item.work_id for item in recovered] == [claimed.id]
    assert work.get(claimed.id).status is AgentWorkStatus.QUEUED
