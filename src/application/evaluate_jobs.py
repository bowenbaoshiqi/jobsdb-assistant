"""Incremental one-job-per-checkpoint native evaluation."""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from src.adapters.career_ops_profile import CareerOpsProfileBundle
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


class ProfileProjector(Protocol):
    def project(
        self,
        profile: CandidateProfile,
    ) -> CareerOpsProfileBundle: ...


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
        profile_projector: ProfileProjector,
    ) -> None:
        self.evaluations = evaluations
        self.adapter = adapter
        self.checkpoints = checkpoints
        self.profile_projector = profile_projector

    def cache_key(
        self,
        profile: CandidateProfile,
        bundle: CareerOpsProfileBundle,
        snapshot: CurrentSnapshotRecord,
    ) -> EvaluationCacheKey:
        if profile.content_hash is None:
            raise ValueError("confirmed profile hash is required")
        return EvaluationCacheKey(
            snapshot_hash=snapshot.content_hash,
            profile_hash=profile.content_hash,
            profile_bundle_hash=bundle.bundle_hash,
            profile_projection_version=bundle.projection_version,
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
        bundle = self.profile_projector.project(profile)
        for snapshot in sorted(
            snapshots,
            key=lambda item: item.snapshot_id,
        ):
            key = self.cache_key(profile, bundle, snapshot)
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
                bundle,
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
            cache_key=EvaluationCacheKey(
                snapshot_hash=snapshot.content_hash,
                profile_hash=task.profile_hash,
                profile_bundle_hash=task.profile_bundle_hash,
                profile_projection_version=(
                    task.profile_projection_version
                ),
                engine_commit=task.integration_commit,
                contract_version=task.contract_version,
            ),
        )
