"""Private, durable progress for the currently observed evaluation batch."""

import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvaluationTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    started_at: datetime
    tasks: dict[str, EvaluationTaskStatus]


class EvaluationProgress(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str | None = None
    status: Literal["idle", "active", "completed"]
    total: int
    queued: int
    running: int
    completed: int
    failed: int


class EvaluationProgressStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def start(
        self,
        task_ids: list[str],
        *,
        now: datetime,
    ) -> EvaluationBatch:
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError("a non-empty unique task list is required")
        batch = EvaluationBatch(
            id=f"evaluation-batch-{uuid.uuid4().hex[:12]}",
            started_at=now,
            tasks=dict.fromkeys(
                task_ids,
                EvaluationTaskStatus.QUEUED,
            ),
        )
        self._write(batch)
        return batch

    def mark(
        self,
        task_id: str,
        status: EvaluationTaskStatus,
    ) -> EvaluationBatch:
        batch = self._read()
        if batch is None or task_id not in batch.tasks:
            raise KeyError(task_id)
        tasks = dict(batch.tasks)
        tasks[task_id] = status
        updated = batch.model_copy(update={"tasks": tasks})
        self._write(updated)
        return updated

    def claim_next(self) -> str | None:
        batch = self._read()
        if batch is None:
            return None
        for task_id, status in batch.tasks.items():
            if status is EvaluationTaskStatus.RUNNING:
                return task_id
        for task_id, status in batch.tasks.items():
            if status is EvaluationTaskStatus.QUEUED:
                self.mark(task_id, EvaluationTaskStatus.RUNNING)
                return task_id
        return None

    def pending_task_ids(self) -> tuple[str, ...]:
        """Return current queued/running task IDs in durable batch order."""
        batch = self._read()
        if batch is None:
            return ()
        return tuple(
            task_id
            for task_id, status in batch.tasks.items()
            if status in {
                EvaluationTaskStatus.QUEUED,
                EvaluationTaskStatus.RUNNING,
            }
        )

    def get(self) -> EvaluationProgress:
        batch = self._read()
        if batch is None:
            return EvaluationProgress(
                status="idle",
                total=0,
                queued=0,
                running=0,
                completed=0,
                failed=0,
            )
        counts = {
            status: sum(value is status for value in batch.tasks.values())
            for status in EvaluationTaskStatus
        }
        active = (
            counts[EvaluationTaskStatus.QUEUED]
            + counts[EvaluationTaskStatus.RUNNING]
        )
        return EvaluationProgress(
            batch_id=batch.id,
            status="active" if active else "completed",
            total=len(batch.tasks),
            queued=counts[EvaluationTaskStatus.QUEUED],
            running=counts[EvaluationTaskStatus.RUNNING],
            completed=counts[EvaluationTaskStatus.COMPLETED],
            failed=counts[EvaluationTaskStatus.FAILED],
        )

    def _read(self) -> EvaluationBatch | None:
        if not self.path.is_file():
            return None
        return EvaluationBatch.model_validate_json(
            self.path.read_text(encoding="utf-8")
        )

    def _write(self, batch: EvaluationBatch) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                batch.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)
