"""Adapter contract for native career-ops A-F evaluation."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.domain.job import CurrentSnapshotRecord

_CAPABILITIES = [
    ".agents/skills/career-ops/SKILL.md",
    "modes/_shared.md",
    "modes/oferta.md",
]


class JobEvaluationTask(BaseModel):
    task_id: str
    integration_id: Literal["job-evaluation"] = "job-evaluation"
    integration_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    contract_version: str
    capability_paths: list[str]
    mode: Literal["evaluation_only"] = "evaluation_only"
    output_language: Literal["zh-CN"] = "zh-CN"
    profile_id: str
    profile_version: int = Field(gt=0)
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_projection_version: str
    profile_context_paths: list[str] = Field(min_length=3, max_length=3)
    snapshots: list[CurrentSnapshotRecord] = Field(min_length=1)


class JobEvaluationResult(BaseModel):
    task_id: str
    evaluations: list[JobEvaluation]

    @model_validator(mode="after")
    def unique_snapshots(self) -> "JobEvaluationResult":
        snapshot_ids = [
            evaluation.job_snapshot_id
            for evaluation in self.evaluations
        ]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("duplicate evaluation snapshot")
        return self


class JobEvaluationAdapter:
    def __init__(
        self,
        integration_commit: str,
        contract_version: str,
    ) -> None:
        self.integration_commit = integration_commit
        self.contract_version = contract_version

    def build_task(
        self,
        task_id: str,
        profile: CandidateProfile,
        bundle: CareerOpsProfileBundle,
        snapshots: list[CurrentSnapshotRecord],
    ) -> JobEvaluationTask:
        if profile.content_hash is None:
            raise ValueError("confirmed profile hash is required")
        if (
            bundle.profile_id != profile.id
            or bundle.profile_version != profile.version
            or bundle.profile_hash != profile.content_hash
        ):
            raise ValueError("profile bundle identity mismatch")
        return JobEvaluationTask(
            task_id=task_id,
            integration_commit=self.integration_commit,
            contract_version=self.contract_version,
            capability_paths=list(_CAPABILITIES),
            profile_id=profile.id,
            profile_version=profile.version,
            profile_hash=profile.content_hash,
            profile_bundle_hash=bundle.bundle_hash,
            profile_projection_version=bundle.projection_version,
            profile_context_paths=[
                str(bundle.profile_yml_path),
                str(bundle.profile_md_path),
                str(bundle.cv_path),
            ],
            snapshots=snapshots,
        )

    def validate_result(
        self,
        task: JobEvaluationTask,
        payload: object,
    ) -> list[JobEvaluation]:
        result = JobEvaluationResult.model_validate(payload)
        if result.task_id != task.task_id:
            raise ValueError("task id mismatch")
        expected = {
            snapshot.snapshot_id: snapshot
            for snapshot in task.snapshots
        }
        if {item.job_snapshot_id for item in result.evaluations} != set(
            expected
        ):
            raise ValueError("evaluation snapshots do not match task")
        for evaluation in result.evaluations:
            snapshot = expected[evaluation.job_snapshot_id]
            if evaluation.jd_summary_zh_cn is None:
                raise ValueError("Chinese JD summary is required")
            if evaluation.snapshot_hash != snapshot.content_hash:
                raise ValueError("snapshot hash mismatch")
            if evaluation.profile_version != task.profile_version:
                raise ValueError("profile version mismatch")
            if evaluation.profile_hash != task.profile_hash:
                raise ValueError("profile hash mismatch")
            if evaluation.engine_commit != task.integration_commit:
                raise ValueError("integration commit mismatch")
        return result.evaluations
