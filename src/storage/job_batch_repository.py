"""Durable current/archived Dashboard job batches."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from src.storage.database import Database


class ActiveDiscoveryError(RuntimeError):
    """A discovery batch is already running."""


@dataclass(frozen=True)
class JobBatch:
    id: str
    keyword: str
    status: str
    created_at: datetime
    archived_at: datetime | None
    error_code: str | None
    error_message: str | None


class JobBatchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, keyword: str, *, now: datetime) -> JobBatch:
        normalized = " ".join(keyword.split())
        if not normalized:
            raise ValueError("keyword must not be empty")
        batch_id = f"batch-{uuid.uuid4().hex[:16]}"
        with self.database._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_batches (
                    id, keyword, status, created_at
                ) VALUES (?, ?, 'discovering', ?)
                """,
                (batch_id, normalized, now.isoformat()),
            )
        return self.get(batch_id)  # type: ignore[return-value]

    def archive_and_create(
        self,
        keyword: str,
        *,
        now: datetime,
    ) -> JobBatch:
        normalized = " ".join(keyword.split())
        if not normalized:
            raise ValueError("keyword must not be empty")
        batch_id = f"batch-{uuid.uuid4().hex[:16]}"
        with self.database._connect() as conn:
            current = conn.execute(
                "SELECT * FROM job_batches WHERE archived_at IS NULL"
            ).fetchone()
            if current is not None and current["status"] == "discovering":
                raise ActiveDiscoveryError("a discovery batch is running")
            if current is not None:
                conn.execute(
                    """
                    UPDATE job_batches
                    SET status = 'archived', archived_at = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), current["id"]),
                )
            conn.execute(
                """
                INSERT INTO job_batches (
                    id, keyword, status, created_at
                ) VALUES (?, ?, 'discovering', ?)
                """,
                (batch_id, normalized, now.isoformat()),
            )
        return self.get(batch_id)  # type: ignore[return-value]

    def add_jobs(
        self,
        batch_id: str,
        job_ids: list[str],
        *,
        now: datetime,
    ) -> None:
        with self.database._connect() as conn:
            start = conn.execute(
                """
                SELECT COALESCE(MAX(position), 0)
                FROM job_batch_jobs WHERE batch_id = ?
                """,
                (batch_id,),
            ).fetchone()[0]
            for offset, job_id in enumerate(dict.fromkeys(job_ids), 1):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO job_batch_jobs (
                        batch_id, job_id, position, added_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (batch_id, job_id, start + offset, now.isoformat()),
                )

    def mark_ready(self, batch_id: str) -> None:
        self._set_status(batch_id, "waiting_for_scoring")

    def mark_failed(self, batch_id: str, message: str) -> None:
        with self.database._connect() as conn:
            conn.execute(
                """
                UPDATE job_batches
                SET status = 'failed', error_code = 'discovery_failed',
                    error_message = ?
                WHERE id = ?
                """,
                (message, batch_id),
            )

    def _set_status(self, batch_id: str, status: str) -> None:
        with self.database._connect() as conn:
            conn.execute(
                "UPDATE job_batches SET status = ? WHERE id = ?",
                (status, batch_id),
            )

    def get(self, batch_id: str) -> JobBatch | None:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM job_batches WHERE id = ?",
                (batch_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def current(self) -> JobBatch | None:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM job_batches
                WHERE archived_at IS NULL
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return None if row is None else self._from_row(row)

    def current_job_ids(self) -> list[str]:
        current = self.current()
        if current is None:
            return []
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id FROM job_batch_jobs
                WHERE batch_id = ? ORDER BY position
                """,
                (current.id,),
            ).fetchall()
        return [row["job_id"] for row in rows]

    def historical_job_ids(self) -> set[str]:
        with self.database._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT job_id FROM job_batch_jobs"
            ).fetchall()
        return {row["job_id"] for row in rows}

    def purge_expired(self, *, cutoff: datetime) -> set[str]:
        with self.database._connect() as conn:
            batches = conn.execute(
                """
                SELECT id FROM job_batches
                WHERE archived_at IS NOT NULL AND archived_at < ?
                """,
                (cutoff.isoformat(),),
            ).fetchall()
            batch_ids = [row["id"] for row in batches]
            if not batch_ids:
                return set()
            placeholders = ", ".join("?" for _ in batch_ids)
            candidates = {
                row["job_id"]
                for row in conn.execute(
                    f"""
                    SELECT DISTINCT job_id FROM job_batch_jobs
                    WHERE batch_id IN ({placeholders})
                    """,
                    batch_ids,
                ).fetchall()
            }
            conn.execute(
                f"DELETE FROM job_batch_jobs WHERE batch_id IN ({placeholders})",
                batch_ids,
            )
            conn.execute(
                f"DELETE FROM job_batches WHERE id IN ({placeholders})",
                batch_ids,
            )
            retained = {
                row["job_id"]
                for row in conn.execute(
                    "SELECT DISTINCT job_id FROM job_batch_jobs"
                ).fetchall()
            }
            removable = candidates - retained
            self._delete_job_data(conn, removable)
        return removable

    @staticmethod
    def _delete_job_data(conn, job_ids: set[str]) -> None:
        for job_id in job_ids:
            snapshot_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM job_snapshots WHERE job_id = ?",
                    (job_id,),
                ).fetchall()
            ]
            for snapshot_id in snapshot_ids:
                conn.execute(
                    "DELETE FROM job_evaluations WHERE job_snapshot_id = ?",
                    (snapshot_id,),
                )
            package_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM material_packages WHERE job_id = ?",
                    (job_id,),
                ).fetchall()
            ]
            for package_id in package_ids:
                conn.execute(
                    "DELETE FROM material_review_events WHERE package_id = ?",
                    (package_id,),
                )
            execution_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM application_executions WHERE job_id = ?",
                    (job_id,),
                ).fetchall()
            ]
            for execution_id in execution_ids:
                conn.execute(
                    """
                    DELETE FROM application_execution_events
                    WHERE execution_id = ?
                    """,
                    (execution_id,),
                )
            for table in (
                "material_packages",
                "material_tasks",
                "dashboard_application_tasks",
                "application_executions",
                "applications",
                "job_selections",
                "job_snapshots",
            ):
                conn.execute(
                    f"DELETE FROM {table} WHERE job_id = ?",
                    (job_id,),
                )
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    @staticmethod
    def _from_row(row) -> JobBatch:
        return JobBatch(
            id=row["id"],
            keyword=row["keyword"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            archived_at=(
                None
                if row["archived_at"] is None
                else datetime.fromisoformat(row["archived_at"])
            ),
            error_code=row["error_code"],
            error_message=row["error_message"],
        )
