"""Incremental one-job-per-checkpoint native evaluation."""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from src.adapters.checkpoint_io import CheckpointStore
from src.adapters.job_evaluation import (
    JobEvaluationAdapter,
    JobEvaluationTask,
)
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import EvaluationCacheKey, JobEvaluation
from src.domain.job import CurrentSnapshotRecord


class EvaluationStore(Protocol):
    def find_by_cache_key(
        self,
        key: EvaluationCacheKey,
    ) -> JobEvaluation | None: ...

    def save(
        self,
        result: JobEvaluation,
        key: EvaluationCacheKey,
    ) -> None: ...


@dataclass(frozen=True)
class PendingEvaluation:
    snapshot_id: str
    task: JobEvaluationTask
    cache_key: EvaluationCacheKey


@dataclass(frozen=True)
class EvaluationPlan:
    cached: tuple[JobEvaluation, ...]
    pending: tuple[PendingEvaluation, ...]


class EvaluationService:
    def __init__(
        self,
        evaluations: EvaluationStore,
        adapter: JobEvaluationAdapter,
        checkpoints: CheckpointStore,
    ) -> None:
        self.evaluations = evaluations
        self.adapter = adapter
        self.checkpoints = checkpoints

    def cache_key(
        self,
        profile: CandidateProfile,
        snapshot: CurrentSnapshotRecord,
    ) -> EvaluationCacheKey:
        if profile.content_hash is None:
            raise ValueError("confirmed profile hash is required")
        return EvaluationCacheKey(
            snapshot_hash=snapshot.content_hash,
            profile_hash=profile.content_hash,
            engine_commit=self.adapter.integration_commit,
            contract_version=self.adapter.contract_version,
        )

    def plan(
        self,
        run_id: str,
        profile: CandidateProfile,
        snapshots: list[CurrentSnapshotRecord],
    ) -> EvaluationPlan:
        cached: list[JobEvaluation] = []
        pending: list[PendingEvaluation] = []
        for snapshot in sorted(
            snapshots,
            key=lambda item: item.snapshot_id,
        ):
            key = self.cache_key(profile, snapshot)
            existing = self.evaluations.find_by_cache_key(key)
            if existing is not None:
                cached.append(existing)
                continue
            identity = (
                f"{run_id}:{snapshot.snapshot_id}:{key.digest()}"
            ).encode()
            task_id = f"evaluation-{sha256(identity).hexdigest()[:16]}"
            task = self.adapter.build_task(
                task_id,
                profile,
                [snapshot],
            )
            self.checkpoints.write_task(
                task_id,
                task.model_dump(mode="json"),
            )
            pending.append(
                PendingEvaluation(
                    snapshot_id=snapshot.snapshot_id,
                    task=task,
                    cache_key=key,
                )
            )
        return EvaluationPlan(
            cached=tuple(cached),
            pending=tuple(pending),
        )

    def submit(
        self,
        pending: PendingEvaluation,
        payload: dict,
    ) -> JobEvaluation:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.checkpoints.submit_result(pending.task.task_id, encoded)
        results = self.adapter.validate_result(pending.task, payload)
        if len(results) != 1:
            raise ValueError("one-job task must return one evaluation")
        result = results[0]
        self.evaluations.save(result, pending.cache_key)
        return result

    def load_pending(self, task_id: str) -> PendingEvaluation:
        task = JobEvaluationTask.model_validate(
            self.checkpoints.read_task(task_id)
        )
        if len(task.snapshots) != 1:
            raise ValueError("v0.3 evaluation task must contain one snapshot")
        snapshot = task.snapshots[0]
        return PendingEvaluation(
            snapshot_id=snapshot.snapshot_id,
            task=task,
            cache_key=self.cache_key(task.profile, snapshot),
        )
