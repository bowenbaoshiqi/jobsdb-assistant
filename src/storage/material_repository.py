"""Durable material tasks, immutable packages, and human review audit."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.domain.material import (
    ApplicationPackage,
    MaterialReviewAction,
    MaterialReviewEvent,
    MaterialReviewStatus,
    MaterialTaskStatus,
)
from src.storage.database import Database


class MaterialTaskRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    batch_id: str
    job_id: str
    snapshot_id: int
    profile_version: int
    evaluation_id: str
    target_version: int
    status: MaterialTaskStatus
    feedback: str | None = None
    payload: dict[str, Any]
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class MaterialRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_task(
        self,
        *,
        task_id: str,
        batch_id: str,
        job_id: str,
        snapshot_id: int,
        profile_version: int,
        evaluation_id: str,
        target_version: int,
        payload: dict[str, Any],
        created_at: datetime,
        feedback: str | None = None,
    ) -> MaterialTaskRecord:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        timestamp = created_at.isoformat()
        with self.database._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM material_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if existing is not None:
                task = self._task_from_row(existing)
                expected = (
                    batch_id,
                    job_id,
                    snapshot_id,
                    profile_version,
                    evaluation_id,
                    target_version,
                    payload,
                    feedback,
                )
                actual = (
                    task.batch_id,
                    task.job_id,
                    task.snapshot_id,
                    task.profile_version,
                    task.evaluation_id,
                    task.target_version,
                    task.payload,
                    task.feedback,
                )
                if actual != expected:
                    raise ValueError("task identity already exists with different data")
                return task
            conn.execute(
                """
                INSERT INTO material_tasks (
                    id, batch_id, job_id, snapshot_id, profile_version,
                    evaluation_id, target_version, status, feedback,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    batch_id,
                    job_id,
                    snapshot_id,
                    profile_version,
                    evaluation_id,
                    target_version,
                    MaterialTaskStatus.WAITING_FOR_AGENT.value,
                    feedback,
                    encoded,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM material_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return self._task_from_row(row)

    def start_task(
        self,
        task_id: str,
        *,
        started_at: datetime,
    ) -> MaterialTaskRecord:
        return self._set_task_status(
            task_id,
            status=MaterialTaskStatus.GENERATING,
            timestamp=started_at,
            started_at=started_at,
        )

    def fail_task(
        self,
        task_id: str,
        *,
        error_message: str,
        completed_at: datetime,
    ) -> MaterialTaskRecord:
        return self._set_task_status(
            task_id,
            status=MaterialTaskStatus.FAILED,
            timestamp=completed_at,
            completed_at=completed_at,
            error_message=error_message,
        )

    def save_package(
        self,
        *,
        task_id: str,
        package: ApplicationPackage,
        saved_at: datetime,
    ) -> ApplicationPackage:
        if not package.id:
            raise ValueError("package id is required")
        timestamp = saved_at.isoformat()
        with self.database._connect() as conn:
            task = conn.execute(
                "SELECT * FROM material_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise KeyError(task_id)
            if (
                package.job_id != task["job_id"]
                or package.evaluation_id != task["evaluation_id"]
                or package.profile_version != task["profile_version"]
                or package.version != task["target_version"]
            ):
                raise ValueError("package identity does not match task")
            existing = conn.execute(
                "SELECT 1 FROM material_packages WHERE task_id = ? "
                "OR (job_id = ? AND version = ?)",
                (task_id, package.job_id, package.version),
            ).fetchone()
            if existing is not None:
                raise ValueError("material packages are immutable")
            maximum = conn.execute(
                "SELECT MAX(version) FROM material_packages WHERE job_id = ?",
                (package.job_id,),
            ).fetchone()[0]
            expected = 1 if maximum is None else maximum + 1
            if package.version != expected:
                raise ValueError(f"next material version must be {expected}")
            stored = package.model_copy(
                update={
                    "created_at": package.created_at or saved_at,
                }
            )
            conn.execute(
                """
                INSERT INTO material_packages (
                    id, task_id, job_id, version, review_status,
                    is_current_approved, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    stored.id,
                    task_id,
                    stored.job_id,
                    stored.version,
                    stored.review_status.value,
                    stored.model_dump_json(),
                    stored.created_at.isoformat(),
                    timestamp,
                ),
            )
            conn.execute(
                """
                UPDATE material_tasks
                SET status = ?, completed_at = ?, updated_at = ?,
                    error_message = NULL
                WHERE id = ?
                """,
                (
                    MaterialTaskStatus.GENERATED.value,
                    timestamp,
                    timestamp,
                    task_id,
                ),
            )
        return stored

    def get_package(self, package_id: str) -> ApplicationPackage:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM material_packages WHERE id = ?",
                (package_id,),
            ).fetchone()
        if row is None:
            raise KeyError(package_id)
        return self._package_from_row(row)

    def task_id_for_package(self, package_id: str) -> str:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT task_id FROM material_packages WHERE id = ?",
                (package_id,),
            ).fetchone()
        if row is None:
            raise KeyError(package_id)
        return str(row["task_id"])

    def latest_for_job(self, job_id: str) -> ApplicationPackage | None:
        versions = self.list_versions(job_id)
        return versions[0] if versions else None

    def list_versions(self, job_id: str) -> list[ApplicationPackage]:
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM material_packages
                WHERE job_id = ?
                ORDER BY version DESC
                """,
                (job_id,),
            ).fetchall()
        return [self._package_from_row(row) for row in rows]

    def current_approved_for_job(
        self,
        job_id: str,
    ) -> ApplicationPackage | None:
        with self.database._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM material_packages
                WHERE job_id = ? AND is_current_approved = 1
                """,
                (job_id,),
            ).fetchone()
        return None if row is None else self._package_from_row(row)

    def list_batch(self, batch_id: str) -> list[MaterialTaskRecord]:
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM material_tasks
                WHERE batch_id = ?
                ORDER BY created_at, id
                """,
                (batch_id,),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def list_pending(self) -> list[MaterialTaskRecord]:
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM material_tasks
                WHERE status IN ('waiting_for_agent', 'generating')
                ORDER BY created_at, id
                """
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def record_review(
        self,
        package_id: str,
        action: MaterialReviewAction,
        *,
        reviewed_at: datetime,
        feedback: str | None = None,
        fact_warning_overridden: bool = False,
    ) -> MaterialReviewEvent:
        timestamp = reviewed_at.isoformat()
        event_id = uuid.uuid4().hex
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT * FROM material_packages WHERE id = ?",
                (package_id,),
            ).fetchone()
            if row is None:
                raise KeyError(package_id)
            package = self._package_from_row(row)
            if action is MaterialReviewAction.APPROVE:
                has_warning = (
                    package.review_status
                    is MaterialReviewStatus.PENDING_REVIEW_WITH_FACT_WARNING
                    or not package.facts.passed
                    or bool(package.facts.findings)
                )
                if has_warning and not fact_warning_overridden:
                    raise ValueError(
                        "fact warning approval requires explicit override"
                    )
                resulting = (
                    MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE
                    if has_warning
                    else MaterialReviewStatus.APPROVED
                )
                conn.execute(
                    """
                    UPDATE material_packages
                    SET is_current_approved = 0, updated_at = ?
                    WHERE job_id = ? AND is_current_approved = 1
                    """,
                    (timestamp, package.job_id),
                )
                current = 1
            elif action is MaterialReviewAction.REJECT:
                resulting = MaterialReviewStatus.REJECTED
                current = 0
            else:
                resulting = (
                    package.review_status
                    if package.review_status
                    in {
                        MaterialReviewStatus.APPROVED,
                        MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE,
                    }
                    else MaterialReviewStatus.SUPERSEDED
                )
                current = int(row["is_current_approved"])
            event = MaterialReviewEvent(
                id=event_id,
                package_id=package_id,
                action=action,
                resulting_status=resulting,
                feedback=feedback,
                fact_warning_overridden=(
                    resulting
                    is MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE
                ),
                created_at=reviewed_at,
            )
            conn.execute(
                """
                UPDATE material_packages
                SET review_status = ?, is_current_approved = ?, updated_at = ?
                WHERE id = ?
                """,
                (resulting.value, current, timestamp, package_id),
            )
            conn.execute(
                """
                INSERT INTO material_review_events (
                    id, package_id, action, feedback,
                    fact_warning_overridden, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.package_id,
                    event.action.value,
                    event.feedback,
                    int(event.fact_warning_overridden),
                    event.model_dump_json(),
                    timestamp,
                ),
            )
        return event

    def list_review_events(
        self,
        package_id: str,
    ) -> list[MaterialReviewEvent]:
        with self.database._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM material_review_events
                WHERE package_id = ?
                ORDER BY created_at, id
                """,
                (package_id,),
            ).fetchall()
        return [
            MaterialReviewEvent.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def _set_task_status(
        self,
        task_id: str,
        *,
        status: MaterialTaskStatus,
        timestamp: datetime,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> MaterialTaskRecord:
        with self.database._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE material_tasks
                SET status = ?,
                    started_at = COALESCE(?, started_at),
                    completed_at = COALESCE(?, completed_at),
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    started_at.isoformat() if started_at else None,
                    completed_at.isoformat() if completed_at else None,
                    error_message,
                    timestamp.isoformat(),
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(task_id)
            row = conn.execute(
                "SELECT * FROM material_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return self._task_from_row(row)

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> MaterialTaskRecord:
        return MaterialTaskRecord(
            id=row["id"],
            batch_id=row["batch_id"],
            job_id=row["job_id"],
            snapshot_id=row["snapshot_id"],
            profile_version=row["profile_version"],
            evaluation_id=row["evaluation_id"],
            target_version=row["target_version"],
            status=row["status"],
            feedback=row["feedback"],
            payload=json.loads(row["payload_json"]),
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=(
                datetime.fromisoformat(row["started_at"])
                if row["started_at"]
                else None
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _package_from_row(row: sqlite3.Row) -> ApplicationPackage:
        package = ApplicationPackage.model_validate_json(row["payload_json"])
        return package.model_copy(
            update={"review_status": MaterialReviewStatus(row["review_status"])}
        )
