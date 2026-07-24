from datetime import UTC, datetime

from src.domain.evaluation import JobEvaluation, NativeDimension
from src.domain.job import ApplyType, CurrentSnapshotRecord
from src.reporting.evaluation_report import (
    EvaluationReportItem,
    render_text,
)

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def item(
    snapshot_id: str,
    company: str,
    score: float,
) -> EvaluationReportItem:
    snapshot = CurrentSnapshotRecord(
        snapshot_id=snapshot_id,
        job_id=f"job-{snapshot_id}",
        title="AI Architect",
        company=company,
        canonical_url=f"https://hk.jobsdb.com/job/job-{snapshot_id}",
        apply_type=ApplyType.QUICK_APPLY,
        jd_text="PRIVATE FULL JD MUST NOT APPEAR",
        content_hash="a" * 64,
    )
    evaluation = JobEvaluation(
        id=f"evaluation-{snapshot_id}",
        job_snapshot_id=snapshot_id,
        profile_version=1,
        profile_hash="b" * 64,
        snapshot_hash="a" * 64,
        engine_version="career-ops@locked",
        engine_commit="c" * 40,
        prompt_version="career-ops-native-af.v1",
        overall_score=score,
        dimensions=[
            NativeDimension(
                code=code,
                title=f"Block {code}",
                score=score,
                findings=["Concise finding"],
                evidence=["JD: named requirement"],
            )
            for code in "ABCDEF"
        ],
        recommendation="strong_apply",
        strengths=["Architecture"],
        gaps=["Domain depth"],
        risks=["Location"],
        evidence=["JD: named requirement"],
        created_at=NOW,
    )
    return EvaluationReportItem(snapshot=snapshot, evaluation=evaluation)


def test_report_orders_score_descending_and_shows_native_blocks() -> None:
    rendered = render_text([
        item("1", "Lower Ltd", 3.8),
        item("2", "Higher Ltd", 4.7),
    ])

    assert rendered.index("Higher Ltd") < rendered.index("Lower Ltd")
    assert "A: 4.7" in rendered
    assert "F: 4.7" in rendered
    assert "Quick Apply" in rendered


def test_report_does_not_render_full_jd_or_profile_facts() -> None:
    rendered = render_text([item("1", "Synthetic Ltd", 4.2)])

    assert "PRIVATE FULL JD MUST NOT APPEAR" not in rendered
    assert "verified_facts" not in rendered
