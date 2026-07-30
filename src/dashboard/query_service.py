"""Compose current jobs and immutable evaluation data for the Dashboard."""

from pathlib import Path

from src.dashboard.evaluation_translation import (
    EvaluationTranslationCatalog,
    translate_evaluation,
)
from src.dashboard.schemas import (
    CandidateProfileSummary,
    DashboardDimension,
    DashboardFilters,
    DashboardJob,
    DashboardMaterialSummary,
    DashboardPage,
    DashboardSummary,
    EvaluationProvenance,
)
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.storage.application_execution_repository import (
    ApplicationExecutionRepository,
)
from src.storage.candidate_repository import CandidateRepository
from src.storage.dashboard_application_repository import (
    DashboardApplicationRepository,
)
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository
from src.storage.job_batch_repository import JobBatchRepository
from src.storage.material_repository import MaterialRepository
from src.storage.selection_repository import SelectionRepository


class DashboardQueryService:
    """Build a truthful read model without performing new AI analysis."""

    def __init__(
        self,
        database: Database,
        *,
        translation_catalog: EvaluationTranslationCatalog | None = None,
        job_batch_repository: JobBatchRepository | None = None,
    ) -> None:
        self.database = database
        self.profiles = CandidateRepository(database)
        self.evaluations = EvaluationRepository(database)
        self.selections = SelectionRepository(database)
        self.application_tasks = DashboardApplicationRepository(database)
        self.approved_applications = ApplicationExecutionRepository(database)
        self.materials = MaterialRepository(database)
        self.job_batches = job_batch_repository
        self.translation_catalog = (
            translation_catalog
            if translation_catalog is not None
            else EvaluationTranslationCatalog.from_path(
                Path("workspace/dashboard/evaluation-translations.json")
            )
        )

    def list_jobs(self, filters: DashboardFilters) -> DashboardPage:
        snapshots = self.database.list_current_snapshot_records()
        if self.job_batches is not None:
            current_job_ids = set(self.job_batches.current_job_ids())
            snapshots = [
                snapshot
                for snapshot in snapshots
                if snapshot.job_id in current_job_ids
            ]
        profile = self.profiles.get_active()
        evaluations = self._current_evaluations(profile)
        selections = self.selections.list_selected()
        tasks = self.application_tasks.latest_for_jobs(
            [snapshot.job_id for snapshot in snapshots]
        )
        approved_applications = self.approved_applications.latest_for_jobs(
            [snapshot.job_id for snapshot in snapshots]
        )

        all_jobs = [
            self._compose_job(
                snapshot,
                evaluation=evaluations.get(snapshot.snapshot_id),
                profile=profile,
                selection=selections.get(snapshot.job_id),
                application_task=tasks.get(snapshot.job_id),
                approved_application=approved_applications.get(
                    snapshot.job_id
                ),
            )
            for snapshot in snapshots
        ]
        summary = self._summary(all_jobs)
        visible = [
            job for job in all_jobs
            if self._matches(job, filters)
        ]
        visible.sort(key=self._sort_key)
        return DashboardPage(jobs=visible, summary=summary)

    def _current_evaluations(
        self,
        profile: CandidateProfile | None,
    ) -> dict[str, JobEvaluation]:
        if profile is None:
            return {}
        return {
            evaluation.job_snapshot_id: evaluation
            for evaluation in self.evaluations.list_current(profile.version)
        }

    def _compose_job(
        self,
        snapshot,
        *,
        evaluation,
        profile,
        selection,
        application_task,
        approved_application,
    ) -> DashboardJob:
        listing = self.database.get_job(snapshot.job_id)
        material_package = self.materials.latest_for_job(snapshot.job_id)
        material_summary = (
            None
            if material_package is None
            else DashboardMaterialSummary(
                package_id=material_package.id,
                version=material_package.version,
                material_mode=material_package.material_mode,
                review_status=material_package.review_status,
                task_status=None,
            )
        )
        profile_summary = (
            None if profile is None else CandidateProfileSummary(
                profile_id=profile.id,
                profile_version=profile.version,
                target_roles=profile.target_roles,
                preferences=profile.preferences,
                exclusions=profile.exclusions,
                writing_style=profile.writing_style,
            )
        )
        if evaluation is None:
            return DashboardJob(
                job_id=snapshot.job_id,
                snapshot_id=snapshot.snapshot_id,
                title=snapshot.title,
                company=snapshot.company,
                location=None if listing is None else listing.location,
                canonical_url=snapshot.canonical_url,
                apply_type=snapshot.apply_type,
                jd_text=snapshot.jd_text,
                evaluation_status="pending",
                profile_summary=profile_summary,
                selected=selection is not None,
                selection_status=(
                    None if selection is None else selection.status
                ),
                application_task=application_task,
                material=material_summary,
                approved_application=approved_application,
            )
        evaluation = translate_evaluation(
            evaluation,
            self.translation_catalog,
        )
        return DashboardJob(
            job_id=snapshot.job_id,
            snapshot_id=snapshot.snapshot_id,
            title=snapshot.title,
            company=snapshot.company,
            location=None if listing is None else listing.location,
            canonical_url=snapshot.canonical_url,
            apply_type=snapshot.apply_type,
            jd_text=(
                evaluation.jd_translation_zh_cn
                or snapshot.jd_text
            ),
            jd_translation_available=(
                evaluation.jd_translation_zh_cn is not None
            ),
            evaluation_status="evaluated",
            overall_score=evaluation.overall_score,
            dimensions=[
                DashboardDimension(
                    code=dimension.code,
                    title=dimension.title,
                    score=dimension.score,
                    findings=list(dimension.findings),
                    evidence=list(dimension.evidence),
                )
                for dimension in evaluation.dimensions
            ],
            recommendation=evaluation.recommendation,
            strengths=list(evaluation.strengths),
            gaps=list(evaluation.gaps),
            risks=list(evaluation.risks),
            evidence=list(evaluation.evidence),
            provenance=EvaluationProvenance(
                evaluation_id=evaluation.id,
                evaluation_created_at=evaluation.created_at,
                profile_version=evaluation.profile_version,
                profile_hash=evaluation.profile_hash,
                snapshot_id=evaluation.job_snapshot_id,
                snapshot_hash=evaluation.snapshot_hash,
                engine_version=evaluation.engine_version,
                engine_commit=evaluation.engine_commit,
                prompt_version=evaluation.prompt_version,
            ),
            profile_summary=profile_summary,
            selected=selection is not None,
            selection_status=(
                None if selection is None else selection.status
            ),
            application_task=application_task,
            material=material_summary,
            approved_application=approved_application,
        )

    @staticmethod
    def _matches(job: DashboardJob, filters: DashboardFilters) -> bool:
        if filters.show == "evaluated" and job.evaluation_status != "evaluated":
            return False
        if (
            filters.score_min is not None
            and (
                job.overall_score is None
                or job.overall_score < filters.score_min
            )
        ):
            return False
        if filters.apply_type is not None and job.apply_type is not filters.apply_type:
            return False
        if filters.selected is not None and job.selected is not filters.selected:
            return False
        if filters.query:
            query = filters.query.strip().casefold()
            searchable = f"{job.title} {job.company}".casefold()
            if query not in searchable:
                return False
        return True

    @staticmethod
    def _sort_key(job: DashboardJob) -> tuple:
        return (
            job.overall_score is None,
            -(job.overall_score or 0.0),
            job.company.casefold(),
            job.title.casefold(),
            job.job_id,
        )

    @staticmethod
    def _summary(jobs: list[DashboardJob]) -> DashboardSummary:
        buckets: dict[str, int] = {}
        for job in jobs:
            if job.overall_score is not None:
                key = f"{job.overall_score:.1f}"
                buckets[key] = buckets.get(key, 0) + 1
        evaluated = sum(
            job.evaluation_status == "evaluated"
            for job in jobs
        )
        return DashboardSummary(
            total=len(jobs),
            evaluated=evaluated,
            pending=len(jobs) - evaluated,
            selected=sum(job.selected for job in jobs),
            score_buckets=buckets,
        )
