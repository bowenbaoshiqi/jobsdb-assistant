"""Adapt existing AI checkpoints to one durable Agent-work queue."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from src.domain.agent_pool import AgentPoolRecord, AgentPoolSlotRecord
from src.domain.agent_work import (
    AgentHumanGate,
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
from src.storage.agent_pool_repository import AgentPoolRepository


class AgentWorkSources(Protocol):
    def current_evaluation_task_ids(self) -> tuple[str, ...]: ...

    def pending_material_task_ids(self) -> tuple[str, ...]: ...


class AgentWorkDispatcher(Protocol):
    def mark_claimed(
        self,
        kind: AgentWorkKind,
        task_id: str,
        *,
        now: datetime,
    ) -> None: ...

    def mark_failed(
        self,
        kind: AgentWorkKind,
        task_id: str,
        *,
        error_message: str,
        now: datetime,
    ) -> None: ...

    def mark_requeued(
        self,
        kind: AgentWorkKind,
        task_id: str,
        *,
        now: datetime,
    ) -> None: ...

    def prepare_profile(
        self,
        run_id: str,
        source_documents: list[str],
        *,
        update: bool,
    ) -> object: ...

    def submit_profile_result(
        self,
        run_id: str,
        task_id: str,
        payload: dict,
    ) -> object: ...

    def submit_profile_answers(
        self,
        run_id: str,
        source_documents: list[str],
        answers: dict,
    ) -> object: ...

    def confirm_profile(self, proposal_id: str) -> object: ...

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
        pool: AgentPoolRepository | None = None,
    ) -> None:
        self.work = work
        self.sources = sources
        self.dispatcher = dispatcher
        self.tasks_root = tasks_root.resolve()
        self.sleeper = sleeper
        self.now_factory = now_factory or (lambda: datetime.now(UTC))
        self.pool = pool or AgentPoolRepository(work.database)

    def start(self, *, now: datetime) -> AgentSessionRecord:
        self.recover_stale_work(now=now)
        self.sync_pending(now=now)
        return self.work.start_or_resume_session(now=now)

    def recover_stale_work(self, *, now: datetime):
        """Recover expired claims and reconcile their external projections."""
        recovered = self.work.recover_expired(now=now)
        for item in recovered:
            with suppress(KeyError):
                self.dispatcher.mark_requeued(
                    item.kind,
                    item.internal_task_id,
                    now=now,
                )
        return tuple(recovered)

    def status(self, session_id: str, *, now: datetime) -> dict[str, object]:
        self.recover_stale_work(now=now)
        session = self.work.session(session_id)
        counts = self.work.status_counts(session_id=session_id)
        active = counts[AgentWorkStatus.QUEUED.value] + counts[
            AgentWorkStatus.CLAIMED.value
        ]
        return {
            "session_state": session.status.value,
            "work": {
                "queued": counts[AgentWorkStatus.QUEUED.value],
                "claimed": counts[AgentWorkStatus.CLAIMED.value],
                "completed": counts[AgentWorkStatus.COMPLETED.value],
                "failed": counts[AgentWorkStatus.FAILED.value],
            },
            "terminal": active == 0,
        }

    def pool_start(
        self,
        *,
        session_id: str,
        now: datetime,
        capability_context_id: str,
        profile_context_id: str,
    ) -> AgentPoolRecord:
        records = self.sync_pending(now=now)
        evaluations = [
            record
            for record in records
            if record.kind is AgentWorkKind.JOB_EVALUATION
        ]
        assignments = tuple(
            (record.id, ordinal, ((ordinal - 1) % 3) + 1)
            for ordinal, record in enumerate(evaluations, start=1)
        )
        batch_key = hashlib.sha256(
            "|".join(record.internal_key for record in evaluations).encode()
        ).hexdigest()
        return self.pool.start_pool(
            session_id=session_id,
            batch_key=batch_key,
            assignments=assignments,
            capability_context_id=capability_context_id,
            profile_context_id=profile_context_id,
            now=now,
        )

    def pool_ready(
        self,
        *,
        pool_id: str,
        slot_token: str,
        capability_context_id: str,
        profile_context_id: str,
        now: datetime,
    ) -> AgentPoolSlotRecord:
        return self.pool.ready_slot(
            pool_id,
            slot_token,
            capability_context_id=capability_context_id,
            profile_context_id=profile_context_id,
            now=now,
        )

    def pool_claim(
        self,
        *,
        session_id: str,
        pool_id: str,
        slot_token: str,
        now: datetime,
    ) -> AgentWorkRecord | None:
        record = self.pool.claim_for_slot(
            pool_id,
            slot_token,
            now=now,
        )
        if record is not None and record.status is AgentWorkStatus.CLAIMED:
            self.dispatcher.mark_claimed(
                record.kind,
                record.internal_key.split(":", 1)[1],
                now=now,
            )
        return record

    def pool_status(self, pool_id: str) -> dict[str, object]:
        pool = self.pool.get_pool(pool_id)
        counts = self.pool.status_counts(pool_id)
        open_count = counts[AgentWorkStatus.QUEUED.value] + counts[
            AgentWorkStatus.CLAIMED.value
        ]
        return {
            "requested_concurrency": pool.requested_concurrency,
            "actual_concurrency": pool.actual_concurrency,
            "pool_state": pool.status.value,
            "work": {
                "queued": counts[AgentWorkStatus.QUEUED.value],
                "claimed": counts[AgentWorkStatus.CLAIMED.value],
                "completed": counts[AgentWorkStatus.COMPLETED.value],
                "failed": counts[AgentWorkStatus.FAILED.value],
            },
            "terminal": open_count == 0,
        }

    def prepare_profile(
        self,
        *,
        source_documents: tuple[str, ...],
        update: bool,
        now: datetime,
    ) -> AgentWorkRecord | None:
        existing = self.work.first_open_by_kinds(
            (
                AgentWorkKind.CANDIDATE_QUESTIONS,
                AgentWorkKind.CANDIDATE_PROPOSAL,
                AgentWorkKind.HUMAN_RESPONSE,
            )
        )
        if existing is not None:
            return existing
        run_id = f"agent-run-{uuid.uuid4().hex}"
        outcome = self.dispatcher.prepare_profile(
            run_id,
            list(source_documents),
            update=update,
        )
        return self._handle_profile_outcome(
            outcome,
            run_id=run_id,
            source_documents=source_documents,
            now=now,
        )

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
            self.recover_stale_work(now=current)
            self.sync_pending(now=current)
            claimed = self.work.claim_next(
                session_id,
                now=current,
                lease_duration=timedelta(minutes=5),
            )
            if claimed is not None:
                if claimed.kind is not AgentWorkKind.HUMAN_RESPONSE:
                    self.dispatcher.mark_claimed(
                        claimed.kind,
                        claimed.internal_key.split(":", 1)[1],
                        now=current,
                    )
                if claimed.kind is AgentWorkKind.HUMAN_RESPONSE:
                    return AgentNextResult(
                        state=AgentWorkStatus.HUMAN_REQUIRED,
                        work=AgentHumanGate(
                            session=session_id,
                            work_id=claimed.id,
                            prompt_path=claimed.task_path,
                            response_path=claimed.result_path,
                        ),
                    )
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
        profile_outcome = None
        if record.kind in {
            AgentWorkKind.CANDIDATE_QUESTIONS,
            AgentWorkKind.CANDIDATE_PROPOSAL,
        }:
            profile_outcome = self.dispatcher.submit_profile_result(
                record.metadata["run_id"],
                task_id,
                payload,
            )
        elif record.kind is AgentWorkKind.HUMAN_RESPONSE:
            action = record.metadata["action"]
            if action == "candidate_interview_answers":
                profile_outcome = self.dispatcher.submit_profile_answers(
                    record.metadata["run_id"],
                    list(record.metadata["source_documents"]),
                    payload,
                )
            elif action == "candidate_profile_confirmation":
                if payload.get("approved") is not True:
                    raise ValueError("explicit profile approval is required")
                self.dispatcher.confirm_profile(
                    record.metadata["proposal_id"]
                )
            else:
                raise ValueError(f"unsupported human action: {action}")
        elif record.kind is AgentWorkKind.JOB_EVALUATION:
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
        self.pool.clear_slot_for_work(work_id, now=now)
        if profile_outcome is not None:
            self._handle_profile_outcome(
                profile_outcome,
                run_id=record.metadata["run_id"],
                source_documents=tuple(
                    record.metadata["source_documents"]
                ),
                now=now,
                previous_result_path=record.result_path,
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
        record = self.work.get(work_id)
        if (
            record.status is not AgentWorkStatus.CLAIMED
            or record.session_id != session_id
        ):
            raise ValueError("agent session is not the active lease owner")
        task_id = record.internal_key.split(":", 1)[1]
        self.dispatcher.mark_failed(
            record.kind,
            task_id,
            error_message=error_message,
            now=now,
        )
        failed = self.work.fail(
            session_id,
            work_id,
            error_message=error_message,
            now=now,
        )
        self.pool.clear_slot_for_work(work_id, now=now)
        return failed

    def stop(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> AgentSessionRecord:
        released = self.work.release_session(session_id, now=now)
        for item in released:
            with suppress(KeyError):
                self.dispatcher.mark_requeued(
                    item.kind,
                    item.internal_task_id,
                    now=now,
                )
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
            capability_paths=self._capability_paths(task),
            now=now,
        )

    def _handle_profile_outcome(
        self,
        outcome,
        *,
        run_id: str,
        source_documents: tuple[str, ...],
        now: datetime,
        previous_result_path: str | None = None,
    ) -> AgentWorkRecord | None:
        status = outcome.status.value
        if status == "ready":
            return None
        if status == "waiting_for_agent":
            if outcome.task_id is None:
                raise ValueError("profile Agent task ID is required")
            task_path = self.tasks_root / outcome.task_id / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            kind = (
                AgentWorkKind.CANDIDATE_PROPOSAL
                if task.get("interview_complete") is True
                else AgentWorkKind.CANDIDATE_QUESTIONS
            )
            return self.work.enqueue(
                kind=kind,
                internal_key=f"profile:{outcome.task_id}",
                task_path=str(task_path),
                result_path=str(
                    self.tasks_root
                    / outcome.task_id
                    / "agent-result.json"
                ),
                capability_paths=self._capability_paths(task),
                metadata={
                    "run_id": run_id,
                    "source_documents": list(source_documents),
                },
                now=now,
            )
        if status == "needs_answers":
            questions = [
                item.model_dump(mode="json")
                for item in outcome.questions
            ]
            return self._enqueue_human(
                internal_key=f"human:answers:{run_id}",
                prompt={
                    "action": "candidate_interview_answers",
                    "questions": questions,
                },
                metadata={
                    "action": "candidate_interview_answers",
                    "run_id": run_id,
                    "source_documents": list(source_documents),
                },
                now=now,
            )
        if status == "waiting_for_user":
            if outcome.proposal_id is None:
                raise ValueError("profile proposal ID is required")
            return self._enqueue_human(
                internal_key=f"human:confirm:{outcome.proposal_id}",
                prompt={
                    "action": "candidate_profile_confirmation",
                    "proposal_result_path": previous_result_path,
                },
                metadata={
                    "action": "candidate_profile_confirmation",
                    "run_id": run_id,
                    "source_documents": list(source_documents),
                    "proposal_id": outcome.proposal_id,
                },
                now=now,
            )
        raise ValueError(f"unsupported profile outcome: {status}")

    def _enqueue_human(
        self,
        *,
        internal_key: str,
        prompt: dict,
        metadata: dict,
        now: datetime,
    ) -> AgentWorkRecord:
        digest = hashlib.sha256(internal_key.encode("utf-8")).hexdigest()[:16]
        directory = self.tasks_root.parent / "agent-human" / digest
        directory.mkdir(parents=True, exist_ok=True)
        prompt_path = directory / "prompt.json"
        temporary = prompt_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                prompt,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(prompt_path)
        return self.work.enqueue(
            kind=AgentWorkKind.HUMAN_RESPONSE,
            internal_key=internal_key,
            task_path=str(prompt_path),
            result_path=str(directory / "response.json"),
            capability_paths=(),
            metadata=metadata,
            now=now,
        )

    def _capability_paths(self, task: dict) -> tuple[str, ...]:
        project_root = self.tasks_root.parents[1]
        integration_id = task.get("integration_id")
        integration_root = (
            project_root / "integrations" / integration_id
            if integration_id
            else project_root
        )
        resolved: list[str] = []
        for raw_path in task.get("capability_paths", ()):
            path = Path(raw_path)
            if not path.is_absolute():
                path = integration_root / path
            resolved.append(str(path.resolve()))
        return tuple(resolved)

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
