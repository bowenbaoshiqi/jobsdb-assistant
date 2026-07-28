"""Safe Dashboard commands for tailored application materials."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.application.generate_materials import MaterialGenerationService
from src.domain.material import MaterialReviewAction
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository
from src.storage.material_repository import MaterialRepository
from src.storage.selection_repository import SelectionRepository


class DashboardMaterialService:
    def __init__(
        self,
        *,
        database: Database,
        repository: MaterialRepository,
        generation: MaterialGenerationService,
        materials_root: Path,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.repository = repository
        self.generation = generation
        self.materials_root = materials_root.resolve()
        self.now = now or (lambda: datetime.now(UTC))
        self.selections = SelectionRepository(database)
        self.profiles = CandidateRepository(database)
        self.evaluations = EvaluationRepository(database)

    def create_batch(self):
        selected = self.selections.list_selected()
        if not selected:
            raise ValueError("at least one selected job is required")
        profile = self.profiles.get_active()
        if profile is None:
            raise ValueError("active confirmed profile is required")
        snapshots = []
        for job_id in sorted(selected):
            snapshot = self.database.get_current_job_snapshot_record(job_id)
            if snapshot is None:
                raise ValueError(f"current snapshot missing for {job_id}")
            snapshots.append(snapshot)
        evaluations = self.evaluations.list_current(profile.version)
        batch_id = f"materials-{uuid.uuid4().hex[:16]}"
        return self.generation.plan_batch(
            batch_id=batch_id,
            profile=profile,
            snapshots=snapshots,
            evaluations=evaluations,
            created_at=self.now(),
        )

    def detail(self, package_id: str) -> dict:
        package = self.repository.get_package(package_id)
        cover = self._private_file(
            Path(package.cover_letter.path),
            expected_hash=package.cover_letter.sha256,
        )
        return {
            **package.model_dump(mode="json"),
            "cover_letter_text": cover.read_text(encoding="utf-8"),
            "versions": [
                {
                    "id": item.id,
                    "version": item.version,
                    "review_status": item.review_status.value,
                    "created_at": (
                        item.created_at.isoformat()
                        if item.created_at
                        else None
                    ),
                }
                for item in self.repository.list_versions(package.job_id)
            ],
            "review_events": [
                item.model_dump(mode="json")
                for item in self.repository.list_review_events(package_id)
            ],
        }

    def pdf_path(self, package_id: str) -> Path:
        package = self.repository.get_package(package_id)
        return self._private_file(
            Path(package.resume.path),
            expected_hash=package.resume.sha256,
        )

    def approved_pdf_for_job(self, job_id: str) -> Path:
        package = self.repository.current_approved_for_job(job_id)
        if package is None:
            raise ValueError("current approved package is required")
        return self._private_file(
            Path(package.resume.path),
            expected_hash=package.resume.sha256,
        )

    def approve(
        self,
        package_id: str,
        *,
        fact_warning_overridden: bool,
    ):
        return self.repository.record_review(
            package_id,
            MaterialReviewAction.APPROVE,
            fact_warning_overridden=fact_warning_overridden,
            reviewed_at=self.now(),
        )

    def reject(self, package_id: str, *, feedback: str | None):
        return self.repository.record_review(
            package_id,
            MaterialReviewAction.REJECT,
            feedback=feedback,
            reviewed_at=self.now(),
        )

    def regenerate(self, package_id: str, *, feedback: str | None):
        self.repository.get_package(package_id)
        return self.generation.plan_regeneration(
            batch_id=f"regenerate-{uuid.uuid4().hex[:16]}",
            previous_task_id=self.repository.task_id_for_package(package_id),
            feedback=feedback,
            created_at=self.now(),
        )

    def _private_file(self, path: Path, *, expected_hash: str) -> Path:
        if path.is_symlink():
            raise ValueError("material file must not be a symlink")
        resolved = path.resolve()
        if not resolved.is_relative_to(self.materials_root):
            raise ValueError("material file escapes private root")
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual != expected_hash:
            raise ValueError("material file hash mismatch")
        return resolved
