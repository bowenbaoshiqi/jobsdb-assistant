"""Durable application execution records and transition audit."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from src.domain.application_execution import (
    ApplicationExecution,
    ApplicationExecutionEvent,
    ApplicationExecutionStatus,
)
from src.storage.database import Database


class ApplicationExecutionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, execution: ApplicationExecution) -> ApplicationExecution:
        key = execution.identity.idempotency_key()
        with self.database._connect() as conn:
            existing_id = conn.execute(
                "SELECT * FROM application_executions WHERE id = ?",
                (execution.id,),
            ).fetchone()
            if existing_id is not None:
                existing = self._from_row(existing_id)
                if existing != execution:
                    raise ValueError(
                        "application execution already exists with different data"
                    )
                return existing
            existing_key = conn.execute(
                """
                SELECT * FROM application_executions
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()
            if existing_key is not None:
                return self._from_row(existing_key)
            try:
                conn.execute(
                    """
                    INSERT INTO application_executions (
                        id, idempotency_key, job_id, package_id,
                        account_alias, status, remote_resume_filename,
                        payload_json, error_code, error_message,
                        screenshot_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution.id,
                        key,
                        execution.identity.job_id,
                        execution.identity.package_id,
                        execution.identity.account_alias,
                        execution.status.value,
                        execution.remote_resume_filename,
                        execution.model_dump_json(),
                        execution.error_code,
                        execution.error_message,
                        execution.screenshot_path,
                        execution.created_at.isoformat(),
                        execution.updated_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                row = conn.execute(
                    """
                    SELECT * FROM application_executions
                    WHERE idempotency_key = ?
                    """,
                    (key,),
                ).fetchone()
                if row is None:
                    raise
                return self._from_row(row)
        return execution

    def get(self, execution_id: str) -> ApplicationExecution | None:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM application_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def transition(
        self,
        execution_id: str,
        status: ApplicationExecutionStatus,
        *,
        at: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
        screenshot_path: str | None = None,
    ) -> ApplicationExecution:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM application_executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise KeyError(execution_id)
            current = self._from_row(row)
            changed = current.transition(
                status,
                at=at,
                error_code=error_code,
                error_message=error_message,
                screenshot_path=screenshot_path,
            )
            conn.execute(
                """
                UPDATE application_executions
                SET status = ?, payload_json = ?, error_code = ?,
                    error_message = ?, screenshot_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    changed.status.value,
                    changed.model_dump_json(),
                    changed.error_code,
                    changed.error_message,
                    changed.screenshot_path,
                    changed.updated_at.isoformat(),
                    changed.id,
                ),
            )
            conn.execute(
                """
                INSERT INTO application_execution_events (
                    id, execution_id, from_status, to_status,
                    error_code, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    execution_id,
                    current.status.value,
                    changed.status.value,
                    error_code,
                    error_message,
                    at.isoformat(),
                ),
            )
        return changed

    def next_runnable(self) -> ApplicationExecution | None:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM application_executions
                WHERE status IN ('queued', 'preparing_resume', 'submitting')
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else self._from_row(row)

    def has_submitted_job(self, job_id: str, account_alias: str) -> bool:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM application_executions
                WHERE job_id = ? AND account_alias = ? AND status = 'submitted'
                LIMIT 1
                """,
                (job_id, account_alias),
            ).fetchone()
        return row is not None

    def list_events(
        self,
        execution_id: str,
    ) -> list[ApplicationExecutionEvent]:
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM application_execution_events
                WHERE execution_id = ?
                ORDER BY created_at, id
                """,
                (execution_id,),
            ).fetchall()
        return [
            ApplicationExecutionEvent(
                id=row["id"],
                execution_id=row["execution_id"],
                from_status=row["from_status"],
                to_status=row["to_status"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _from_row(row) -> ApplicationExecution:
        return ApplicationExecution.model_validate_json(row["payload_json"])
