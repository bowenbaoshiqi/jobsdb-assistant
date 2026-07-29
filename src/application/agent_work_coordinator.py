"""Adapt existing AI checkpoints to one durable Agent-work queue."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

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


class AgentWorkSources(Protocol):
    def current_evaluation_task_ids(self) -> tuple[str, ...]: ...

    def pending_material_task_ids(self) -> tuple[str, ...]: ...


class AgentWorkDispatcher(Protocol):
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

    def prepare_profile(
        self,
        *,
        source_documents: tuple[str, ...],
        update: bool,
        now: datetime,
    ) -> AgentWorkRecord | None:
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
            self.sync_pending(now=current)
            claimed = self.work.claim_next(
                session_id,
                now=current,
                lease_duration=timedelta(minutes=5),
            )
            if claimed is not None:
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
                capability_paths=tuple(
                    task.get("capability_paths", ())
                ),
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
