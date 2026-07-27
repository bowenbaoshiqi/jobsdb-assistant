"""Persistence for the Dashboard's current material selections."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.storage.database import Database


class Selection(BaseModel):
    """One current job selection."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: Literal["waiting_for_materials"]
    selected_at: datetime
    updated_at: datetime


class SelectionRepository:
    """Store only jobs that are currently selected."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def select(
        self,
        job_id: str,
        *,
        selected_at: datetime,
    ) -> Selection:
        timestamp = selected_at.isoformat()
        with self.database._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if exists is None:
                raise KeyError(job_id)
            conn.execute(
                """
                INSERT INTO job_selections (
                    job_id, status, selected_at, updated_at
                ) VALUES (?, 'waiting_for_materials', ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (job_id, timestamp, timestamp),
            )
            row = conn.execute(
                "SELECT * FROM job_selections WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._from_row(row)

    def deselect(self, job_id: str) -> bool:
        with self.database._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM job_selections WHERE job_id = ?",
                (job_id,),
            )
        return cursor.rowcount > 0

    def list_selected(self) -> dict[str, Selection]:
        with self.database._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_selections ORDER BY job_id"
            ).fetchall()
        return {
            row["job_id"]: self._from_row(row)
            for row in rows
        }

    @staticmethod
    def _from_row(row) -> Selection:
        return Selection(
            job_id=row["job_id"],
            status=row["status"],
            selected_at=datetime.fromisoformat(row["selected_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
