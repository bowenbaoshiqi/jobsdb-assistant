from datetime import UTC, datetime, timedelta

from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
from src.storage.agent_pool_repository import AgentPoolRepository
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database


NOW = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)


def test_fifteen_jobs_drain_as_three_independent_five_job_lanes(tmp_path) -> None:
    database = Database(str(tmp_path / "jobs.db"))
    work = AgentWorkRepository(database)
    pools = AgentPoolRepository(database)
    session = work.start_session(now=NOW)
    records = [
        work.enqueue(
            kind=AgentWorkKind.JOB_EVALUATION,
            internal_key=f"evaluation:task-{index}",
            task_path=f"/private/task-{index}.json",
            result_path=f"/private/result-{index}.json",
            capability_paths=("/private/capability.md",),
            now=NOW,
        )
        for index in range(15)
    ]
    pool = pools.start_pool(
        session_id=session.id,
        batch_key="batch-15",
        assignments=tuple(
            (record.id, index + 1, (index % 3) + 1)
            for index, record in enumerate(records)
        ),
        capability_context_id="cap-v1",
        profile_context_id="profile-v1",
        now=NOW,
    )
    for slot in pool.slots:
        pools.ready_slot(
            pool.id,
            slot.slot_token,
            capability_context_id="cap-v1",
            profile_context_id="profile-v1",
            now=NOW,
        )

    completed: list[str] = []
    for round_index in range(5):
        active = []
        for slot in pool.slots:
            item = pools.claim_for_slot(
                pool.id,
                slot.slot_token,
                now=NOW + timedelta(seconds=round_index),
            )
            assert item is not None
            active.append((slot, item))
        assert len({item.id for _slot, item in active}) == 3
        for slot, item in reversed(active):
            work.complete(
                session.id,
                item.id,
                result_hash=(str(round_index) + "a" * 64)[:64],
                now=NOW,
            )
            pools.clear_slot(pool.id, slot.slot_token, now=NOW)
            completed.append(item.id)

    snapshot = pools.status_counts(pool.id)
    assert len(completed) == 15
    assert snapshot[AgentWorkStatus.COMPLETED.value] == 15
    assert snapshot[AgentWorkStatus.CLAIMED.value] == 0
    assert pools.get_pool(pool.id).status.value == "completed"

