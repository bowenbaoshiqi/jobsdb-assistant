"""Transactional persistence for the unified Agent-work protocol."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.agent_work import (
    AgentSessionStatus,
    AgentWorkKind,
    AgentWorkStatus,
)
from src.storage.database import Database

_DEFAULT_LEASE = timedelta(minutes=5)


class AgentSessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: AgentSessionStatus
    started_at: datetime
    heartbeat_at: datetime
    stopped_at: datetime | None = None


class AgentWorkRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    internal_key: str
    kind: AgentWorkKind
    status: AgentWorkStatus
    task_path: str
    result_path: str
    capability_paths: tuple[str, ...]
    metadata: dict[str, Any]
    session_id: str | None = None
    attempt: int
    lease_expires_at: datetime | None = None
    result_hash: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class AgentWorkRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start_session(self, *, now: datetime) -> AgentSessionRecord:
        session_id = f"agent-session-{uuid.uuid4().hex[:24]}"
        timestamp = now.isoformat()
        with self.database._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    id, status, started_at, heartbeat_at
                ) VALUES (?, 'active', ?, ?)
                """,
                (session_id, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row)

    def enqueue(
        self,
        *,
        kind: AgentWorkKind,
        internal_key: str,
        task_path: str,
        result_path: str,
        capability_paths: tuple[str, ...],
        metadata: dict[str, Any] | None = None,
        now: datetime,
    ) -> AgentWorkRecord:
        if not internal_key:
            raise ValueError("internal key is required")
        encoded_paths = json.dumps(
            list(capability_paths),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        encoded_metadata = json.dumps(
            metadata or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.database._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM agent_work_items WHERE internal_key = ?",
                (internal_key,),
            ).fetchone()
            if existing is not None:
                record = self._work_from_row(existing)
                expected = (
                    kind,
                    task_path,
                    result_path,
                    tuple(capability_paths),
                    metadata or {},
                )
                actual = (
                    record.kind,
                    record.task_path,
                    record.result_path,
                    record.capability_paths,
                    record.metadata,
                )
                if actual != expected:
                    raise ValueError(
                        "work identity already exists with different data"
                    )
                return record
            work_id = f"work-{uuid.uuid4().hex[:24]}"
            timestamp = now.isoformat()
            conn.execute(
                """
                INSERT INTO agent_work_items (
                    id, internal_key, kind, status, task_path, result_path,
                    capability_paths_json, metadata_json, created_at,
                    updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    internal_key,
                    kind.value,
                    task_path,
                    result_path,
                    encoded_paths,
                    encoded_metadata,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
        return self._work_from_row(row)

    def claim_next(
        self,
        session_id: str,
        *,
        now: datetime,
        lease_duration: timedelta = _DEFAULT_LEASE,
    ) -> AgentWorkRecord | None:
        if lease_duration.total_seconds() <= 0:
            raise ValueError("lease duration must be positive")
        timestamp = now.isoformat()
        lease_expires_at = (now + lease_duration).isoformat()
        with self.database._connect() as conn:
            self._require_active_session(conn, session_id)
            self._recover_expired_in_connection(conn, now=now)
            owned = conn.execute(
                """
                SELECT * FROM agent_work_items
                WHERE status = 'claimed' AND session_id = ?
                ORDER BY created_at, id
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if owned is not None:
                conn.execute(
                    """
                    UPDATE agent_sessions
                    SET heartbeat_at = ? WHERE id = ?
                    """,
                    (timestamp, session_id),
                )
                return self._work_from_row(owned)
            queued = conn.execute(
                """
                SELECT id FROM agent_work_items
                WHERE status = 'queued'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if queued is None:
                conn.execute(
                    """
                    UPDATE agent_sessions
                    SET heartbeat_at = ? WHERE id = ?
                    """,
                    (timestamp, session_id),
                )
                return None
            conn.execute(
                """
                UPDATE agent_work_items
                SET status = 'claimed', session_id = ?,
                    attempt = attempt + 1, lease_expires_at = ?,
                    updated_at = ?, error_message = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (
                    session_id,
                    lease_expires_at,
                    timestamp,
                    queued["id"],
                ),
            )
            conn.execute(
                """
                UPDATE agent_sessions
                SET heartbeat_at = ? WHERE id = ?
                """,
                (timestamp, session_id),
            )
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (queued["id"],),
            ).fetchone()
        return self._work_from_row(row)

    def recover_expired(self, *, now: datetime) -> int:
        with self.database._connect() as conn:
            return self._recover_expired_in_connection(conn, now=now)

    def complete(
        self,
        session_id: str,
        work_id: str,
        *,
        result_hash: str,
        now: datetime,
    ) -> AgentWorkRecord:
        if len(result_hash) != 64:
            raise ValueError("result hash must be SHA-256")
        timestamp = now.isoformat()
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
            if row is None:
                raise KeyError(work_id)
            record = self._work_from_row(row)
            if record.status is AgentWorkStatus.COMPLETED:
                if record.result_hash != result_hash:
                    raise ValueError(
                        "work already completed with a different result"
                    )
                return record
            self._require_claim_owner(record, session_id)
            conn.execute(
                """
                UPDATE agent_work_items
                SET status = 'completed', result_hash = ?,
                    lease_expires_at = NULL, completed_at = ?,
                    updated_at = ?, error_message = NULL
                WHERE id = ?
                """,
                (result_hash, timestamp, timestamp, work_id),
            )
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
        return self._work_from_row(row)

    def fail(
        self,
        session_id: str,
        work_id: str,
        *,
        error_message: str,
        now: datetime,
    ) -> AgentWorkRecord:
        if not error_message:
            raise ValueError("error message is required")
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
            if row is None:
                raise KeyError(work_id)
            record = self._work_from_row(row)
            self._require_claim_owner(record, session_id)
            timestamp = now.isoformat()
            conn.execute(
                """
                UPDATE agent_work_items
                SET status = 'failed', error_message = ?,
                    lease_expires_at = NULL, completed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (error_message, timestamp, timestamp, work_id),
            )
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
        return self._work_from_row(row)

    def stop_session(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> AgentSessionRecord:
        timestamp = now.isoformat()
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            conn.execute(
                """
                UPDATE agent_sessions
                SET status = 'stopped', heartbeat_at = ?, stopped_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, session_id),
            )
            conn.execute(
                """
                UPDATE agent_work_items
                SET status = 'queued', session_id = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE session_id = ? AND status = 'claimed'
                """,
                (timestamp, session_id),
            )
            row = conn.execute(
                "SELECT * FROM agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row)

    def get(self, work_id: str) -> AgentWorkRecord:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_work_items WHERE id = ?",
                (work_id,),
            ).fetchone()
        if row is None:
            raise KeyError(work_id)
        return self._work_from_row(row)

    @staticmethod
    def _recover_expired_in_connection(conn, *, now: datetime) -> int:
        cursor = conn.execute(
            """
            UPDATE agent_work_items
            SET status = 'queued', session_id = NULL,
                lease_expires_at = NULL, updated_at = ?
            WHERE status = 'claimed' AND lease_expires_at <= ?
            """,
            (now.isoformat(), now.isoformat()),
        )
        return cursor.rowcount

    @staticmethod
    def _require_active_session(conn, session_id: str) -> None:
        row = conn.execute(
            "SELECT status FROM agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        if row["status"] != AgentSessionStatus.ACTIVE.value:
            raise ValueError("agent session is not active")

    @staticmethod
    def _require_claim_owner(
        record: AgentWorkRecord,
        session_id: str,
    ) -> None:
        if (
            record.status is not AgentWorkStatus.CLAIMED
            or record.session_id != session_id
        ):
            raise ValueError("agent session is not the active lease owner")

    @staticmethod
    def _session_from_row(row) -> AgentSessionRecord:
        return AgentSessionRecord(
            id=row["id"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            heartbeat_at=datetime.fromisoformat(row["heartbeat_at"]),
            stopped_at=(
                None
                if row["stopped_at"] is None
                else datetime.fromisoformat(row["stopped_at"])
            ),
        )

    @staticmethod
    def _work_from_row(row) -> AgentWorkRecord:
        return AgentWorkRecord(
            id=row["id"],
            internal_key=row["internal_key"],
            kind=row["kind"],
            status=row["status"],
            task_path=row["task_path"],
            result_path=row["result_path"],
            capability_paths=tuple(json.loads(row["capability_paths_json"])),
            metadata=json.loads(row["metadata_json"]),
            session_id=row["session_id"],
            attempt=row["attempt"],
            lease_expires_at=(
                None
                if row["lease_expires_at"] is None
                else datetime.fromisoformat(row["lease_expires_at"])
            ),
            result_hash=row["result_hash"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            completed_at=(
                None
                if row["completed_at"] is None
                else datetime.fromisoformat(row["completed_at"])
            ),
        )
