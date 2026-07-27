"""Durable state for Dashboard-triggered Quick Apply tasks."""

import sqlite3
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.storage.database import Database


class DashboardApplicationStatus(str, Enum):
    APPLYING = "applying"
    SUBMITTED = "submitted"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"
    SKIPPED_ALREADY_APPLIED = "skipped_already_applied"


class ApplicationBusyError(RuntimeError):
    """Another Dashboard application currently owns the browser profile."""


class DashboardApplicationTask(BaseModel):
    """One immutable view of a durable direct-application task."""

    model_config = ConfigDict(frozen=True)

    id: str
    job_id: str
    status: DashboardApplicationStatus
    resume_mode: str
    cover_letter_mode: str
    session_id: str | None = None
    error_message: str | None = None
    screenshot_path: str | None = None
    created_at: datetime
    updated_at: datetime


class DashboardApplicationRepository:
    """Persist and enforce the one-active-application invariant."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        job_id: str,
        *,
        now: datetime,
    ) -> DashboardApplicationTask:
        task_id = f"dashboard-apply-{uuid.uuid4().hex}"
        timestamp = now.isoformat()
        try:
            with self.database._connect() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if exists is None:
                    raise KeyError(job_id)
                conn.execute(
                    """
                    INSERT INTO dashboard_application_tasks (
                        id, job_id, status, resume_mode,
                        cover_letter_mode, created_at, updated_at
                    ) VALUES (
                        ?, ?, 'applying', 'jobsdb_default',
                        'none', ?, ?
                    )
                    """,
                    (task_id, job_id, timestamp, timestamp),
                )
                row = self._fetch(conn, task_id)
        except sqlite3.IntegrityError as exc:
            if self._has_active_task():
                raise ApplicationBusyError(
                    "another application is already running"
                ) from exc
            raise
        return self._from_row(row)

    def finish(
        self,
        task_id: str,
        status: DashboardApplicationStatus,
        *,
        now: datetime,
        session_id: str | None = None,
        error_message: str | None = None,
        screenshot_path: str | None = None,
    ) -> DashboardApplicationTask:
        if status is DashboardApplicationStatus.APPLYING:
            raise ValueError("terminal status is required")
        with self.database._connect() as conn:
            existing = self._fetch(conn, task_id)
            if existing is None:
                raise KeyError(task_id)
            if existing["status"] != DashboardApplicationStatus.APPLYING.value:
                raise ValueError("application task is not applying")
            conn.execute(
                """
                UPDATE dashboard_application_tasks
                SET status = ?, session_id = ?, error_message = ?,
                    screenshot_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    session_id,
                    error_message,
                    screenshot_path,
                    now.isoformat(),
                    task_id,
                ),
            )
            row = self._fetch(conn, task_id)
        return self._from_row(row)

    def get(self, task_id: str) -> DashboardApplicationTask | None:
        with self.database._connect() as conn:
            row = self._fetch(conn, task_id)
        return None if row is None else self._from_row(row)

    def latest_for_jobs(
        self,
        job_ids: list[str],
    ) -> dict[str, DashboardApplicationTask]:
        if not job_ids:
            return {}
        placeholders = ", ".join("?" for _ in job_ids)
        with self.database._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT task.*
                FROM dashboard_application_tasks AS task
                JOIN (
                    SELECT job_id, MAX(created_at) AS latest_created
                    FROM dashboard_application_tasks
                    WHERE job_id IN ({placeholders})
                    GROUP BY job_id
                ) AS latest
                ON latest.job_id = task.job_id
                AND latest.latest_created = task.created_at
                ORDER BY task.job_id, task.id DESC
                """,
                tuple(job_ids),
            ).fetchall()
        result: dict[str, DashboardApplicationTask] = {}
        for row in rows:
            result.setdefault(row["job_id"], self._from_row(row))
        return result

    def _has_active_task(self) -> bool:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM dashboard_application_tasks
                WHERE status = 'applying' LIMIT 1
                """
            ).fetchone()
        return row is not None

    @staticmethod
    def _fetch(conn: sqlite3.Connection, task_id: str):
        return conn.execute(
            "SELECT * FROM dashboard_application_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()

    @staticmethod
    def _from_row(row) -> DashboardApplicationTask:
        return DashboardApplicationTask(
            id=row["id"],
            job_id=row["job_id"],
            status=row["status"],
            resume_mode=row["resume_mode"],
            cover_letter_mode=row["cover_letter_mode"],
            session_id=row["session_id"],
            error_message=row["error_message"],
            screenshot_path=row["screenshot_path"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
