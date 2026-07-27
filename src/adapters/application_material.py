"""Pinned AI Job Search contract for tailored application materials."""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.domain.job import CurrentSnapshotRecord
from src.domain.material import MaterialCheck

_CAPABILITIES = [
    ".claude/skills/job-application-assistant/SKILL.md",
    ".claude/skills/job-application-assistant/05-cv-templates.md",
    ".claude/skills/job-application-assistant/06-cover-letter-templates.md",
]


class ApplicationMaterialTask(BaseModel):
    task_id: str
    integration_id: Literal["application-material"] = "application-material"
    integration_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    contract_version: str
    capability_paths: list[str]
    document_language: Literal["en"] = "en"
    summary_language: Literal["zh-CN"] = "zh-CN"
    cover_letter_word_range: tuple[int, int] = (100, 300)
    job_id: str
    snapshot_id: str
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    job_title: str
    company: str
    job_url: str
    jd_text: str
    profile_id: str
    profile_version: int = Field(gt=0)
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_context_paths: list[str]
    evaluation_id: str
    evaluation: JobEvaluation
    material_version: int = Field(gt=0)
    source_cv_path: str
    source_cv_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    feedback: str | None = None


class ApplicationMaterialResult(BaseModel):
    task_id: str
    integration_id: Literal["application-material"]
    integration_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    contract_version: str
    job_id: str
    snapshot_id: str
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    profile_id: str
    profile_version: int = Field(gt=0)
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluation_id: str
    material_version: int = Field(gt=0)
    source_cv_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    tailored_cv_source: dict[str, Any]
    resume_path: str = Field(min_length=1)
    cover_letter_path: str = Field(min_length=1)
    cover_letter_text: str = Field(min_length=1)
    cover_letter_word_count: int = Field(ge=100, le=300)
    change_summary: list[str]
    check_order: list[str]
    reviewer: MaterialCheck
    ats: MaterialCheck
    facts: MaterialCheck
    engine_provenance: dict[str, Any]
    prompt_provenance: dict[str, Any]

    @model_validator(mode="after")
    def validate_generated_content(self) -> ApplicationMaterialResult:
        if self.check_order != ["reviewer", "ats", "facts"]:
            raise ValueError("checks must be ordered reviewer, ats, facts")
        actual_words = len(self.cover_letter_text.split())
        if actual_words != self.cover_letter_word_count:
            raise ValueError("cover letter word count mismatch")
        return self


class ApplicationMaterialAdapter:
    def __init__(
        self,
        integration_commit: str,
        contract_version: str,
    ) -> None:
        self.integration_commit = integration_commit
        self.contract_version = contract_version

    def build_task(
        self,
        *,
        task_id: str,
        material_version: int,
        profile: CandidateProfile,
        bundle: CareerOpsProfileBundle,
        snapshot: CurrentSnapshotRecord,
        evaluation: JobEvaluation,
        feedback: str | None = None,
    ) -> ApplicationMaterialTask:
        if profile.content_hash is None:
            raise ValueError("confirmed profile hash is required")
        if (
            bundle.profile_id != profile.id
            or bundle.profile_version != profile.version
            or bundle.profile_hash != profile.content_hash
        ):
            raise ValueError("profile bundle identity mismatch")
        if (
            evaluation.job_snapshot_id != snapshot.snapshot_id
            or evaluation.snapshot_hash != snapshot.content_hash
        ):
            raise ValueError("evaluation snapshot identity mismatch")
        if (
            evaluation.profile_version != profile.version
            or evaluation.profile_hash != profile.content_hash
        ):
            raise ValueError("evaluation profile identity mismatch")
        if not evaluation.id:
            raise ValueError("evaluation id is required")
        source_cv = bundle.cv_path
        if not source_cv.is_file():
            raise ValueError("source CV does not exist")
        source_hash = hashlib.sha256(source_cv.read_bytes()).hexdigest()
        return ApplicationMaterialTask(
            task_id=task_id,
            integration_commit=self.integration_commit,
            contract_version=self.contract_version,
            capability_paths=list(_CAPABILITIES),
            job_id=snapshot.job_id,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.content_hash,
            job_title=snapshot.title,
            company=snapshot.company,
            job_url=snapshot.canonical_url,
            jd_text=snapshot.jd_text,
            profile_id=profile.id,
            profile_version=profile.version,
            profile_hash=profile.content_hash,
            profile_bundle_hash=bundle.bundle_hash,
            profile_context_paths=[
                str(bundle.profile_yml_path),
                str(bundle.profile_md_path),
                str(bundle.cv_path),
            ],
            evaluation_id=evaluation.id,
            evaluation=evaluation,
            material_version=material_version,
            source_cv_path=str(source_cv),
            source_cv_hash=source_hash,
            feedback=feedback,
        )

    def validate_result(
        self,
        task: ApplicationMaterialTask,
        payload: object,
    ) -> ApplicationMaterialResult:
        result = ApplicationMaterialResult.model_validate(payload)
        checks = [
            ("task id", result.task_id, task.task_id),
            ("integration id", result.integration_id, task.integration_id),
            (
                "integration commit",
                result.integration_commit,
                task.integration_commit,
            ),
            (
                "contract version",
                result.contract_version,
                task.contract_version,
            ),
            ("job id", result.job_id, task.job_id),
            ("snapshot id", result.snapshot_id, task.snapshot_id),
            ("snapshot hash", result.snapshot_hash, task.snapshot_hash),
            ("profile id", result.profile_id, task.profile_id),
            ("profile version", result.profile_version, task.profile_version),
            ("profile hash", result.profile_hash, task.profile_hash),
            ("evaluation id", result.evaluation_id, task.evaluation_id),
            (
                "material version",
                result.material_version,
                task.material_version,
            ),
            ("source CV hash", result.source_cv_hash, task.source_cv_hash),
        ]
        for label, actual, expected in checks:
            if actual != expected:
                raise ValueError(f"{label} mismatch")
        return result
