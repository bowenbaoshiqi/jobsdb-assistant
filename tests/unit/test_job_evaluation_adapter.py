from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.adapters.job_evaluation import JobEvaluationAdapter
from src.domain.candidate import CandidateProfile
from src.domain.job import ApplyType, CurrentSnapshotRecord

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def profile() -> CandidateProfile:
    return CandidateProfile(
        id="profile-1",
        version=1,
        verified_facts={"skills": ["Python"]},
        target_roles=["AI Architect"],
        created_at=NOW,
        confirmed_at=NOW,
        content_hash="a" * 64,
    )


def snapshot() -> CurrentSnapshotRecord:
    return CurrentSnapshotRecord(
        snapshot_id="1",
        job_id="job-1",
        title="AI Architect",
        company="Synthetic Ltd",
        canonical_url="https://hk.jobsdb.com/job/job-1",
        apply_type=ApplyType.QUICK_APPLY,
        jd_text="Synthetic JD",
        content_hash="b" * 64,
    )


def result_payload(codes: str = "ABCDEF") -> dict:
    return {
        "task_id": "evaluation-run-1",
        "evaluations": [{
            "id": "evaluation-1",
            "job_snapshot_id": "1",
            "profile_version": 1,
            "profile_hash": "a" * 64,
            "snapshot_hash": "b" * 64,
            "engine_version": "career-ops@locked",
            "engine_commit": "c" * 40,
            "prompt_version": "career-ops-native-af.v1",
            "overall_score": 4.2,
            "dimensions": [
                {
                    "code": code,
                    "title": f"Block {code}",
                    "score": 4.0,
                    "findings": ["Synthetic finding"],
                    "evidence": ["JD: evidence"],
                }
                for code in codes
            ],
            "recommendation": "strong_apply",
            "strengths": ["Relevant experience"],
            "gaps": ["Synthetic gap"],
            "risks": ["Synthetic risk"],
            "evidence": ["JD: evidence"],
            "created_at": NOW.isoformat(),
        }],
    }


def test_evaluation_task_uses_only_native_career_ops_scoring() -> None:
    adapter = JobEvaluationAdapter(
        integration_commit="c" * 40,
        contract_version="career-ops-native-af.v1",
    )

    task = adapter.build_task(
        "evaluation-run-1",
        profile(),
        [snapshot()],
    )

    assert task.capability_paths == [
        ".agents/skills/career-ops/SKILL.md",
        "modes/_shared.md",
        "modes/oferta.md",
    ]
    assert task.mode == "evaluation_only"


def test_evaluation_adapter_accepts_matching_native_result() -> None:
    adapter = JobEvaluationAdapter(
        "c" * 40,
        "career-ops-native-af.v1",
    )
    task = adapter.build_task(
        "evaluation-run-1",
        profile(),
        [snapshot()],
    )

    evaluations = adapter.validate_result(task, result_payload())

    assert evaluations[0].overall_score == 4.2


def test_evaluation_adapter_rejects_missing_native_block() -> None:
    adapter = JobEvaluationAdapter(
        "c" * 40,
        "career-ops-native-af.v1",
    )
    task = adapter.build_task(
        "evaluation-run-1",
        profile(),
        [snapshot()],
    )

    with pytest.raises(ValidationError, match="A through F"):
        adapter.validate_result(task, result_payload("ABCDE"))
