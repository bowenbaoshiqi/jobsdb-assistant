"""Resumable one-job-per-task tailored material generation."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from src.adapters.application_material import (
    ApplicationMaterialAdapter,
    ApplicationMaterialResult,
    ApplicationMaterialTask,
)
from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.adapters.checkpoint_io import CheckpointStore
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.domain.job import CurrentSnapshotRecord
from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
    MaterialMode,
    MaterialReviewAction,
)
from src.materials.artifacts import (
    count_cover_letter_words,
    hash_file,
    install_package_files,
)
from src.materials.pdf_renderer import render_tailored_resume
from src.materials.pdf_validator import validate_tailored_pdf
from src.materials.template import ResumeTemplate
from src.storage.material_repository import MaterialRepository


class ProfileProjector(Protocol):
    def project(
        self,
        profile: CandidateProfile,
    ) -> CareerOpsProfileBundle: ...


@dataclass(frozen=True)
class PendingMaterial:
    task: ApplicationMaterialTask


@dataclass(frozen=True)
class MaterialBatchPlan:
    batch_id: str
    pending: tuple[PendingMaterial, ...]


class MaterialGenerationService:
    def __init__(
        self,
        *,
        repository: MaterialRepository,
        adapter: ApplicationMaterialAdapter,
        checkpoints: CheckpointStore,
        profile_projector: ProfileProjector,
        materials_root: Path,
    ) -> None:
        self.repository = repository
        self.adapter = adapter
        self.checkpoints = checkpoints
        self.profile_projector = profile_projector
        self.materials_root = materials_root.resolve()

    def plan_batch(
        self,
        *,
        batch_id: str,
        profile: CandidateProfile,
        snapshots: list[CurrentSnapshotRecord],
        evaluations: list[JobEvaluation],
        material_mode: MaterialMode = (
            MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
        ),
        created_at: datetime,
    ) -> MaterialBatchPlan:
        if not profile.confirmed_at or not profile.content_hash:
            raise ValueError("confirmed current profile is required")
        if not snapshots:
            raise ValueError("at least one current snapshot is required")
        evaluation_by_snapshot = {
            item.job_snapshot_id: item for item in evaluations
        }
        missing = [
            item.snapshot_id
            for item in snapshots
            if item.snapshot_id not in evaluation_by_snapshot
        ]
        if missing:
            raise ValueError(
                f"current evaluation is required for snapshot {missing[0]}"
            )
        bundle = self.profile_projector.project(profile)
        pending: list[PendingMaterial] = []
        for snapshot in sorted(snapshots, key=lambda item: item.job_id):
            evaluation = evaluation_by_snapshot[snapshot.snapshot_id]
            latest = self.repository.latest_for_job(snapshot.job_id)
            version = 1 if latest is None else latest.version + 1
            identity = (
                f"{batch_id}:{snapshot.job_id}:{snapshot.snapshot_id}:"
                f"{profile.content_hash}:{evaluation.id}:{version}:"
                f"{material_mode.value}"
            ).encode()
            task_id = f"material-{hashlib.sha256(identity).hexdigest()[:16]}"
            task = self.adapter.build_task(
                task_id=task_id,
                material_version=version,
                material_mode=material_mode,
                profile=profile,
                bundle=bundle,
                snapshot=snapshot,
                evaluation=evaluation,
            )
            self.repository.create_task(
                task_id=task.task_id,
                batch_id=batch_id,
                job_id=task.job_id,
                snapshot_id=int(task.snapshot_id),
                profile_version=task.profile_version,
                evaluation_id=task.evaluation_id,
                target_version=task.material_version,
                payload=task.model_dump(mode="json"),
                created_at=created_at,
            )
            self.checkpoints.write_task(
                task.task_id,
                task.model_dump(mode="json"),
            )
            pending.append(PendingMaterial(task=task))
        return MaterialBatchPlan(batch_id=batch_id, pending=tuple(pending))

    def load_pending(self, task_id: str) -> PendingMaterial:
        return PendingMaterial(
            task=ApplicationMaterialTask.model_validate(
                self.checkpoints.read_task(task_id)
            )
        )

    def submit(
        self,
        pending: PendingMaterial,
        payload: dict,
        *,
        completed_at: datetime,
    ) -> ApplicationPackage:
        try:
            self.checkpoints.submit_result(
                pending.task.task_id,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
            result = self.adapter.validate_result(pending.task, payload)
            package = self._install_and_package(
                pending.task,
                result,
                completed_at=completed_at,
            )
            return self.repository.save_package(
                task_id=pending.task.task_id,
                package=package,
                saved_at=completed_at,
            )
        except Exception as exc:
            self.repository.fail_task(
                pending.task.task_id,
                error_message=str(exc),
                completed_at=completed_at,
            )
            raise

    def plan_regeneration(
        self,
        *,
        batch_id: str,
        previous_task_id: str,
        feedback: str | None,
        created_at: datetime,
    ) -> PendingMaterial:
        previous = self.load_pending(previous_task_id).task
        latest = self.repository.latest_for_job(previous.job_id)
        version = 1 if latest is None else latest.version + 1
        identity = (
            f"{batch_id}:{previous.job_id}:{previous.snapshot_id}:"
            f"{previous.profile_hash}:{previous.evaluation_id}:{version}"
        ).encode()
        task_id = f"material-{hashlib.sha256(identity).hexdigest()[:16]}"
        task = previous.model_copy(
            update={
                "task_id": task_id,
                "material_version": version,
                "feedback": feedback,
            }
        )
        self.repository.create_task(
            task_id=task.task_id,
            batch_id=batch_id,
            job_id=task.job_id,
            snapshot_id=int(task.snapshot_id),
            profile_version=task.profile_version,
            evaluation_id=task.evaluation_id,
            target_version=task.material_version,
            payload=task.model_dump(mode="json"),
            feedback=feedback,
            created_at=created_at,
        )
        self.checkpoints.write_task(task.task_id, task.model_dump(mode="json"))
        if latest is not None:
            self.repository.record_review(
                latest.id,
                MaterialReviewAction.REGENERATE,
                feedback=feedback,
                reviewed_at=created_at,
            )
        return PendingMaterial(task=task)

    def _install_and_package(
        self,
        task: ApplicationMaterialTask,
        result: ApplicationMaterialResult,
        *,
        completed_at: datetime,
    ) -> ApplicationPackage:
        staging = self.checkpoints.staging_dir(task.task_id)
        cover = self.checkpoints.resolve_staged_path(
            task.task_id,
            result.cover_letter_path,
        )
        resume: Path | None = None
        layout = MaterialCheck()
        layout_manifest: dict = {"passed": True, "findings": []}
        if (
            task.material_mode
            is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
        ):
            source = Path(task.source_cv_path).resolve()
            if (
                not source.is_file()
                or hash_file(source) != task.source_cv_hash
            ):
                raise ValueError(
                    "source CV hash mismatch before rendering"
                )
            resume = staging / "cv.pdf"
            template = ResumeTemplate.v5()
            rendered = render_tailored_resume(
                source,
                resume,
                result.tailored_sections,
                template,
            )
            if rendered.overflow:
                details = ", ".join(
                    f"{item.region}:{item.actual_lines}/"
                    f"{item.maximum_lines}"
                    for item in rendered.overflow
                )
                raise ValueError(f"resume layout overflow: {details}")
            validation = validate_tailored_pdf(source, resume, template)
            if not validation.passed:
                raise ValueError(
                    "resume layout validation failed: "
                    + ", ".join(validation.codes)
                )
            layout = MaterialCheck(
                passed=validation.passed,
                findings=list(validation.findings),
            )
            layout_manifest = {
                "passed": validation.passed,
                "codes": list(validation.codes),
                "findings": list(validation.findings),
                "page_count": validation.page_count,
                "extractable_characters": (
                    validation.extractable_characters
                ),
            }
        cover_text = cover.read_text(encoding="utf-8")
        if cover_text.strip() != result.cover_letter_text.strip():
            raise ValueError("cover letter artifact content mismatch")
        if (
            count_cover_letter_words(cover_text)
            != result.cover_letter_word_count
        ):
            raise ValueError("cover letter word count mismatch")
        installed = install_package_files(
            staging_root=staging,
            resume_path=resume,
            cover_letter_path=cover,
            materials_root=self.materials_root,
            job_id=task.job_id,
            version=task.material_version,
            manifest={
                "task_id": task.task_id,
                "material_mode": task.material_mode.value,
                "change_summary": result.change_summary,
                "resume_template_id": task.resume_template_id,
                "tailored_sections": result.tailored_sections.model_dump(
                    mode="json"
                ),
                "layout": layout_manifest,
                "engine_provenance": result.engine_provenance,
                "prompt_provenance": result.prompt_provenance,
            },
        )
        return ApplicationPackage(
            id=f"package-{uuid.uuid4().hex}",
            job_id=task.job_id,
            evaluation_id=task.evaluation_id,
            profile_version=task.profile_version,
            version=task.material_version,
            material_mode=task.material_mode,
            resume=(
                None
                if installed.resume_path is None
                or installed.resume_sha256 is None
                else MaterialArtifact(
                    path=str(installed.resume_path),
                    sha256=installed.resume_sha256,
                )
            ),
            cover_letter=MaterialArtifact(
                path=str(installed.cover_letter_path),
                sha256=installed.cover_letter_sha256,
            ),
            cover_letter_word_count=result.cover_letter_word_count,
            reviewer=result.reviewer,
            ats=result.ats,
            facts=result.facts,
            layout=layout,
            created_at=completed_at,
        )
