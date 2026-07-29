from datetime import UTC, datetime

from src.dashboard.query_service import DashboardQueryService
from src.dashboard.schemas import DashboardFilters
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import (
    EvaluationCacheKey,
    JobEvaluation,
    NativeDimension,
)
from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


def _save_job(
    database: Database,
    *,
    job_id: str,
    title: str,
    company: str,
    apply_type: ApplyType,
) -> str:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title=title,
            company=company,
            location="Hong Kong",
            jd_text=f"Complete JD for {title}",
            apply_type=apply_type,
        ),
        captured_at=NOW,
    )
    snapshot = database.get_current_job_snapshot_record(job_id)
    assert snapshot is not None
    return snapshot.snapshot_id


def _save_profile(database: Database) -> CandidateProfile:
    profile = CandidateProfile(
        id="profile-2",
        version=2,
        verified_facts={"leadership": ["Led an AI team"]},
        target_roles=["Head of AI"],
        preferences={
            "company_size": "large mature enterprise",
            "minimum_monthly_salary_hkd": 75000,
        },
        exclusions=["small or unstable company"],
        writing_style={"tone": "factual and technically professional"},
        created_at=NOW,
        confirmed_at=NOW,
        content_hash="a" * 64,
    )
    with database._connect() as conn:
        conn.execute(
            """
            INSERT INTO candidate_profiles (
                id, version, payload_json, content_hash, is_active,
                created_at, confirmed_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                profile.id,
                profile.version,
                profile.model_dump_json(),
                profile.content_hash,
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    return profile


def _save_evaluation(
    database: Database,
    *,
    snapshot_id: str,
) -> JobEvaluation:
    snapshot = database.get_current_job_snapshot_record("high-score")
    assert snapshot is not None
    evaluation = JobEvaluation(
        id="evaluation-high",
        job_snapshot_id=snapshot_id,
        profile_version=2,
        profile_hash="a" * 64,
        snapshot_hash=snapshot.content_hash,
        engine_version="career-ops@01bf8b4",
        engine_commit="b" * 40,
        prompt_version="career-ops-native-af.v1",
        jd_translation_zh_cn="完整翻译：负责企业级人工智能架构与平台交付。",
        overall_score=4.6,
        dimensions=[
            NativeDimension(
                code=code,
                title=f"Native block {code}",
                score=4.5,
                findings=["native finding"],
                evidence=["JD: direct evidence"],
            )
            for code in "ABCDEF"
        ],
        recommendation="strong_apply",
        strengths=["Enterprise AI leadership"],
        gaps=["Team size not stated"],
        risks=["Salary not disclosed"],
        evidence=["JD: direct evidence"],
        created_at=NOW,
    )
    EvaluationRepository(database).save(
        evaluation,
        EvaluationCacheKey(
            snapshot_hash=snapshot.content_hash,
            profile_hash="a" * 64,
            profile_bundle_hash="c" * 64,
            profile_projection_version="career-ops-profile-bundle.v1",
            engine_commit="b" * 40,
            contract_version="career-ops-native-af.v1",
        ),
    )
    return evaluation


def _service() -> DashboardQueryService:
    database = Database(":memory:")
    high_snapshot = _save_job(
        database,
        job_id="high-score",
        title="AI Architect",
        company="Alpha Group",
        apply_type=ApplyType.QUICK_APPLY,
    )
    _save_job(
        database,
        job_id="pending",
        title="Data Platform Lead",
        company="Beta Group",
        apply_type=ApplyType.APPLY,
    )
    _save_profile(database)
    _save_evaluation(database, snapshot_id=high_snapshot)
    SelectionRepository(database).select("high-score", selected_at=NOW)
    return DashboardQueryService(database)


def test_defaults_to_evaluated_jobs_and_preserves_native_trace() -> None:
    page = _service().list_jobs(DashboardFilters())

    assert [job.job_id for job in page.jobs] == ["high-score"]
    assert [item.code for item in page.jobs[0].dimensions] == list("ABCDEF")
    assert page.jobs[0].dimensions[0].title == "职位与求职目标匹配度"
    assert page.jobs[0].dimensions[0].findings == ["原文：native finding"]
    assert page.jobs[0].dimensions[0].evidence == ["原文：JD: direct evidence"]
    assert page.jobs[0].recommendation == "强烈建议申请"
    assert page.jobs[0].strengths == ["原文：Enterprise AI leadership"]
    assert page.jobs[0].jd_text == "完整翻译：负责企业级人工智能架构与平台交付。"
    assert page.jobs[0].profile_summary.target_roles == ["Head of AI"]
    assert page.jobs[0].provenance.engine_commit == "b" * 40


def test_all_mode_labels_unscored_without_inventing_verdict() -> None:
    page = _service().list_jobs(DashboardFilters(show="all"))
    pending = next(job for job in page.jobs if job.job_id == "pending")

    assert pending.evaluation_status == "pending"
    assert pending.overall_score is None
    assert pending.dimensions == []
    assert pending.profile_requirement_verdicts is None


def test_filters_and_orders_deterministically() -> None:
    page = _service().list_jobs(
        DashboardFilters(
            show="all",
            apply_type=ApplyType.QUICK_APPLY,
            selected=True,
            query="architect",
        )
    )

    assert [job.job_id for job in page.jobs] == ["high-score"]
    assert page.summary.total == 2
    assert page.summary.evaluated == 1
    assert page.summary.pending == 1
    assert page.summary.selected == 1


def test_score_filter_excludes_lower_scores() -> None:
    page = _service().list_jobs(
        DashboardFilters(show="all", score_min=4.7)
    )

    assert page.jobs == []
