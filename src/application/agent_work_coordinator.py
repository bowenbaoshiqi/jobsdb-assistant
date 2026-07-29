"""Adapt existing AI checkpoints to one durable Agent-work queue."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from src.domain.agent_work import (
    AgentNextResult,
    AgentWorkEnvelope,
    AgentWorkKind,
    AgentWorkStatus,
)
from src.storage.agent_work_repository import (
    AgentSessionRecord,
    AgentWorkRecord,
    AgentWorkRepository,
)


class AgentWorkSources(Protocol):
    def current_evaluation_task_ids(self) -> tuple[str, ...]: ...

    def pending_material_task_ids(self) -> tuple[str, ...]: ...


class AgentWorkDispatcher(Protocol):
    def submit_evaluation(self, task_id: str, payload: dict) -> object: ...

    def submit_material(self, task_id: str, payload: dict) -> object: ...


class AgentWorkCoordinator:
    def __init__(
        self,
        *,
        work: AgentWorkRepository,
        sources: AgentWorkSources,
        dispatcher: AgentWorkDispatcher,
        tasks_root: Path,
        sleeper: Callable[[float], None] = time.sleep,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.work = work
        self.sources = sources
        self.dispatcher = dispatcher
        self.tasks_root = tasks_root.resolve()
        self.sleeper = sleeper
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    def start(self, *, now: datetime) -> AgentSessionRecord:
        self.sync_pending(now=now)
        return self.work.start_session(now=now)

    def sync_pending(self, *, now: datetime) -> tuple[AgentWorkRecord, ...]:
        created: list[AgentWorkRecord] = []
        for task_id in self.sources.current_evaluation_task_ids():
            created.append(
                self._enqueue_task(
                    task_id,
                    kind=AgentWorkKind.JOB_EVALUATION,
                    prefix="evaluation",
                    now=now,
                )
            )
        for task_id in self.sources.pending_material_task_ids():
            created.append(
                self._enqueue_task(
                    task_id,
                    kind=AgentWorkKind.APPLICATION_MATERIAL,
                    prefix="material",
                    now=now,
                )
            )
        return tuple(created)

    def next(
        self,
        session_id: str,
        *,
        wait_seconds: int,
        now: datetime | None = None,
    ) -> AgentNextResult:
        if not 0 <= wait_seconds <= 30:
            raise ValueError("wait seconds must be between 0 and 30")
        deadline = time.monotonic() + wait_seconds
        current = now or self.now_factory()
        while True:
            self.sync_pending(now=current)
            claimed = self.work.claim_next(
                session_id,
                now=current,
                lease_duration=timedelta(minutes=5),
            )
            if claimed is not None:
                return AgentNextResult(
                    state=AgentWorkStatus.CLAIMED,
                    work=self._envelope(session_id, claimed),
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return AgentNextResult(state=AgentWorkStatus.IDLE)
            self.sleeper(min(1.0, remaining))
            current = self.now_factory()

    def submit(
        self,
        *,
        session_id: str,
        work_id: str,
        result_path: Path,
        now: datetime,
    ) -> AgentWorkRecord:
        record = self.work.get(work_id)
        if (
            record.status is not AgentWorkStatus.CLAIMED
            or record.session_id != session_id
        ):
            raise ValueError("agent session is not the active lease owner")
        expected_path = Path(record.result_path).resolve()
        supplied_path = result_path.resolve()
        if supplied_path != expected_path:
            raise ValueError("result path does not match claimed work")
        encoded = supplied_path.read_bytes()
        payload = json.loads(encoded)
        task_id = record.internal_key.split(":", 1)[1]
        if record.kind is AgentWorkKind.JOB_EVALUATION:
            self.dispatcher.submit_evaluation(task_id, payload)
        elif record.kind is AgentWorkKind.APPLICATION_MATERIAL:
            self.dispatcher.submit_material(task_id, payload)
        else:
            raise ValueError(f"unsupported work kind: {record.kind.value}")
        completed = self.work.complete(
            session_id,
            work_id,
            result_hash=hashlib.sha256(encoded).hexdigest(),
            now=now,
        )
        self.sync_pending(now=now)
        return completed

    def fail(
        self,
        *,
        session_id: str,
        work_id: str,
        error_message: str,
        now: datetime,
    ) -> AgentWorkRecord:
        return self.work.fail(
            session_id,
            work_id,
            error_message=error_message,
            now=now,
        )

    def stop(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> AgentSessionRecord:
        return self.work.stop_session(session_id, now=now)

    def _enqueue_task(
        self,
        task_id: str,
        *,
        kind: AgentWorkKind,
        prefix: str,
        now: datetime,
    ) -> AgentWorkRecord:
        task_path = self.tasks_root / task_id / "task.json"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        if task.get("task_id") != task_id:
            raise ValueError("checkpoint task identity mismatch")
        result_path = self.tasks_root / task_id / "agent-result.json"
        return self.work.enqueue(
            kind=kind,
            internal_key=f"{prefix}:{task_id}",
            task_path=str(task_path),
            result_path=str(result_path),
            capability_paths=tuple(task.get("capability_paths", ())),
            now=now,
        )

    @staticmethod
    def _envelope(
        session_id: str,
        record: AgentWorkRecord,
    ) -> AgentWorkEnvelope:
        if record.lease_expires_at is None:
            raise ValueError("claimed work requires a lease")
        return AgentWorkEnvelope(
            session=session_id,
            work_id=record.id,
            kind=record.kind,
            task_path=record.task_path,
            result_path=record.result_path,
            capability_paths=record.capability_paths,
            attempt=record.attempt,
            lease_expires_at=record.lease_expires_at,
        )
