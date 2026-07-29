"""Transactional persistence for three-slot evaluation pools."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from src.domain.agent_pool import (
    AgentPoolRecord,
    AgentPoolSlotRecord,
    AgentPoolSlotStatus,
    AgentPoolStatus,
    AgentPoolStatusSnapshot,
)
from src.domain.agent_work import AgentWorkKind, AgentWorkStatus
from src.storage.agent_work_repository import (
    AgentWorkRecord,
    RecoveredAgentWork,
)
from src.storage.database import Database


_LEASE = timedelta(minutes=5)


class AgentPoolRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start_pool(
        self,
        *,
        session_id: str,
        batch_key: str,
        assignments: tuple[tuple[str, int, int], ...],
        capability_context_id: str,
        profile_context_id: str,
        now: datetime,
    ) -> AgentPoolRecord:
        if not capability_context_id or not profile_context_id:
            raise ValueError("pool context identities are required")
        with self.database._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM agent_pools
                WHERE session_id = ? AND batch_key = ?
                  AND status IN ('starting', 'active', 'draining')
                ORDER BY created_at DESC LIMIT 1
                """,
                (session_id, batch_key),
            ).fetchone()
            if existing is not None:
                return self._pool_from_conn(conn, existing["id"])
            pool_id = f"pool-{uuid.uuid4().hex[:24]}"
            timestamp = now.isoformat()
            conn.execute(
                """
                INSERT INTO agent_pools (
                    id, session_id, kind, batch_key, status,
                    requested_concurrency, actual_concurrency,
                    capability_context_id, profile_context_id,
                    created_at, heartbeat_at
                ) VALUES (?, ?, 'job_evaluation', ?, 'starting', 3, 0, ?, ?, ?, ?)
                """,
                (
                    pool_id,
                    session_id,
                    batch_key,
                    capability_context_id,
                    profile_context_id,
                    timestamp,
                    timestamp,
                ),
            )
            for ordinal in range(1, 4):
                conn.execute(
                    """
                    INSERT INTO agent_pool_slots (
                        pool_id, slot_token, ordinal, status
                    ) VALUES (?, ?, ?, 'starting')
                    """,
                    (pool_id, f"slot-{uuid.uuid4().hex[:24]}", ordinal),
                )
            for work_id, ordinal, slot_ordinal in assignments:
                conn.execute(
                    """
                    INSERT INTO agent_evaluation_batch_tasks (
                        pool_id, work_id, ordinal, slot_ordinal
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (pool_id, work_id, ordinal, slot_ordinal),
                )
            return self._pool_from_conn(conn, pool_id)

    def ready_slot(
        self,
        pool_id: str,
        slot_token: str,
        *,
        capability_context_id: str,
        profile_context_id: str,
        now: datetime,
    ) -> AgentPoolSlotRecord:
        with self.database._connect() as conn:
            pool = conn.execute(
                "SELECT * FROM agent_pools WHERE id = ?",
                (pool_id,),
            ).fetchone()
            if pool is None:
                raise KeyError(pool_id)
            if (
                pool["capability_context_id"] != capability_context_id
                or pool["profile_context_id"] != profile_context_id
            ):
                raise ValueError("worker context identity mismatch")
            conn.execute(
                """
                UPDATE agent_pool_slots
                SET status = 'idle', heartbeat_at = ?
                WHERE pool_id = ? AND slot_token = ?
                """,
                (now.isoformat(), pool_id, slot_token),
            )
            ready = conn.execute(
                """
                SELECT COUNT(*) AS count FROM agent_pool_slots
                WHERE pool_id = ? AND status = 'idle'
                """,
                (pool_id,),
            ).fetchone()["count"]
            if ready == 3:
                conn.execute(
                    """
                    UPDATE agent_pools SET status = 'active', actual_concurrency = 3,
                        heartbeat_at = ? WHERE id = ?
                    """,
                    (now.isoformat(), pool_id),
                )
            return self._slot_from_row(
                conn.execute(
                    """
                    SELECT * FROM agent_pool_slots
                    WHERE pool_id = ? AND slot_token = ?
                    """,
                    (pool_id, slot_token),
                ).fetchone()
            )

    def claim_for_slot(
        self,
        pool_id: str,
        slot_token: str,
        *,
        now: datetime,
        lease_duration: timedelta = _LEASE,
    ) -> AgentWorkRecord | None:
        with self.database._connect() as conn:
            pool = conn.execute(
                "SELECT * FROM agent_pools WHERE id = ?",
                (pool_id,),
            ).fetchone()
            slot = conn.execute(
                """
                SELECT * FROM agent_pool_slots
                WHERE pool_id = ? AND slot_token = ?
                """,
                (pool_id, slot_token),
            ).fetchone()
            if pool is None or slot is None:
                raise KeyError(pool_id if pool is None else slot_token)
            if pool["status"] != AgentPoolStatus.ACTIVE.value:
                return None
            if slot["status"] == AgentPoolSlotStatus.ASSIGNED.value:
                row = conn.execute(
                    "SELECT * FROM agent_work_items WHERE id = ?",
                    (slot["current_work_id"],),
                ).fetchone()
                return self._work_from_row(row)
            if slot["assignment_count"] >= 5:
                return None
            queued = conn.execute(
                """
                SELECT work_id FROM agent_evaluation_batch_tasks
                WHERE pool_id = ? AND slot_ordinal = ?
                  AND work_id IN (
                    SELECT id FROM agent_work_items WHERE status = 'queued'
                  )
                ORDER BY ordinal LIMIT 1
                """,
                (pool_id, slot["ordinal"]),
            ).fetchone()
            if queued is None:
                return None
            work_id = queued["work_id"]
            updated = conn.execute(
                """
                UPDATE agent_work_items
                SET status = 'claimed', session_id = ?, attempt = attempt + 1,
                    lease_expires_at = ?, updated_at = ?, error_message = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (
                    pool["session_id"],
                    (now + lease_duration).isoformat(),
                    now.isoformat(),
                    work_id,
                ),
            )
            if updated.rowcount != 1:
                return None
            conn.execute(
                """
                UPDATE agent_pool_slots
                SET status = 'assigned', current_work_id = ?,
                    assignment_count = assignment_count + 1,
                    heartbeat_at = ?
                WHERE pool_id = ? AND slot_token = ?
                """,
                (work_id, now.isoformat(), pool_id, slot_token),
            )
            return self._work_from_row(
                conn.execute(
                    "SELECT * FROM agent_work_items WHERE id = ?",
                    (work_id,),
                ).fetchone()
            )

    def clear_slot(self, pool_id: str, slot_token: str, *, now: datetime) -> None:
        with self.database._connect() as conn:
            conn.execute(
                """
                UPDATE agent_pool_slots
                SET status = 'idle', current_work_id = NULL, heartbeat_at = ?
                WHERE pool_id = ? AND slot_token = ?
                """,
                (now.isoformat(), pool_id, slot_token),
            )

    def get_slot(self, pool_id: str, slot_token: str) -> AgentPoolSlotRecord:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_pool_slots
                WHERE pool_id = ? AND slot_token = ?
                """,
                (pool_id, slot_token),
            ).fetchone()
        if row is None:
            raise KeyError(slot_token)
        return self._slot_from_row(row)

    def stop_pool(
        self,
        pool_id: str,
        *,
        now: datetime,
    ) -> tuple[RecoveredAgentWork, ...]:
        with self.database._connect() as conn:
            pool = conn.execute(
                "SELECT * FROM agent_pools WHERE id = ?",
                (pool_id,),
            ).fetchone()
            if pool is None:
                raise KeyError(pool_id)
            rows = conn.execute(
                """
                SELECT work.* FROM agent_work_items AS work
                JOIN agent_pool_slots AS slot ON slot.current_work_id = work.id
                WHERE slot.pool_id = ? AND work.status = 'claimed'
                """,
                (pool_id,),
            ).fetchall()
            conn.execute(
                """
                UPDATE agent_work_items SET status = 'queued', session_id = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE id IN (
                    SELECT current_work_id FROM agent_pool_slots
                    WHERE pool_id = ? AND current_work_id IS NOT NULL
                ) AND status = 'claimed'
                """,
                (now.isoformat(), pool_id),
            )
            conn.execute(
                "UPDATE agent_pool_slots SET status = 'stopped', current_work_id = NULL WHERE pool_id = ?",
                (pool_id,),
            )
            conn.execute(
                "UPDATE agent_pools SET status = 'stopped', completed_at = ? WHERE id = ?",
                (now.isoformat(), pool_id),
            )
        return tuple(self._recovered(row) for row in rows)

    @staticmethod
    def _recovered(row) -> RecoveredAgentWork:
        record = AgentPoolRepository._work_from_row(row)
        _, task_id = record.internal_key.split(":", 1)
        return RecoveredAgentWork(
            work_id=record.id,
            kind=record.kind,
            internal_task_id=task_id,
            previous_session_id=record.session_id,
            recovery_reason="session_stopped",
        )

    def _pool_from_conn(self, conn, pool_id: str) -> AgentPoolRecord:
        row = conn.execute(
            "SELECT * FROM agent_pools WHERE id = ?", (pool_id,)
        ).fetchone()
        slots = conn.execute(
            """
            SELECT * FROM agent_pool_slots WHERE pool_id = ? ORDER BY ordinal
            """,
            (pool_id,),
        ).fetchall()
        return AgentPoolRecord(
            id=row["id"], session_id=row["session_id"], kind=row["kind"],
            batch_key=row["batch_key"], status=row["status"],
            requested_concurrency=row["requested_concurrency"],
            actual_concurrency=row["actual_concurrency"],
            capability_context_id=row["capability_context_id"],
            profile_context_id=row["profile_context_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            heartbeat_at=datetime.fromisoformat(row["heartbeat_at"]),
            completed_at=(None if row["completed_at"] is None else datetime.fromisoformat(row["completed_at"])),
            slots=tuple(self._slot_from_row(item) for item in slots),
        )

    @staticmethod
    def _slot_from_row(row) -> AgentPoolSlotRecord:
        return AgentPoolSlotRecord(
            pool_id=row["pool_id"], slot_token=row["slot_token"],
            ordinal=row["ordinal"], status=row["status"],
            generation=row["generation"], current_work_id=row["current_work_id"],
            assignment_count=row["assignment_count"],
            heartbeat_at=(None if row["heartbeat_at"] is None else datetime.fromisoformat(row["heartbeat_at"])),
        )

    @staticmethod
    def _work_from_row(row) -> AgentWorkRecord:
        from src.storage.agent_work_repository import AgentWorkRepository

        return AgentWorkRepository._work_from_row(row)
