from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.adapters.application_material import ApplicationMaterialAdapter
from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation, NativeDimension
from src.domain.job import ApplyType, CurrentSnapshotRecord

NOW = datetime(2026, 7, 27, tzinfo=UTC)
PROFILE_HASH = "a" * 64
SNAPSHOT_HASH = "b" * 64
COMMIT = "c" * 40


def _inputs(tmp_path: Path):
    cv = tmp_path / "cv.md"
    cv.write_text("# Bowen Bao\nEnterprise AI leader", encoding="utf-8")
    profile = CandidateProfile(
        id="candidate-1",
        version=2,
        target_roles=["Head of AI"],
        created_at=NOW,
        confirmed_at=NOW,
        content_hash=PROFILE_HASH,
    )
    bundle = CareerOpsProfileBundle(
        root=tmp_path,
        profile_id=profile.id,
        profile_version=profile.version,
        profile_hash=PROFILE_HASH,
        projection_version="bundle.v1",
        bundle_hash="d" * 64,
        cv_path=cv,
        profile_yml_path=tmp_path / "profile.yml",
        profile_md_path=tmp_path / "profile.md",
        manifest_path=tmp_path / "manifest.json",
        manifest={},
    )
    snapshot = CurrentSnapshotRecord(
        snapshot_id="11",
        job_id="job-1",
        title="Head of AI",
        company="Large Corporation",
        canonical_url="https://hk.jobsdb.com/job/job-1",
        apply_type=ApplyType.QUICK_APPLY,
        jd_text="Lead an enterprise LLM platform.",
        content_hash=SNAPSHOT_HASH,
    )
    evaluation = JobEvaluation(
        id="evaluation-1",
        job_snapshot_id="11",
        profile_version=2,
        profile_hash=PROFILE_HASH,
        snapshot_hash=SNAPSHOT_HASH,
        engine_version="career-ops",
        engine_commit="e" * 40,
        prompt_version="v1",
        overall_score=4.2,
        dimensions=[
            NativeDimension(code=code, title=code, score=4)
            for code in "ABCDEF"
        ],
        recommendation="Proceed",
        created_at=NOW,
    )
    return profile, bundle, snapshot, evaluation


def _result(task) -> dict:
    return {
        "task_id": task.task_id,
        "integration_id": task.integration_id,
        "integration_commit": task.integration_commit,
        "contract_version": task.contract_version,
        "job_id": task.job_id,
        "snapshot_id": task.snapshot_id,
        "snapshot_hash": task.snapshot_hash,
        "profile_id": task.profile_id,
        "profile_version": task.profile_version,
        "profile_hash": task.profile_hash,
        "evaluation_id": task.evaluation_id,
        "material_version": task.material_version,
        "source_cv_hash": task.source_cv_hash,
        "tailored_cv_source": {"summary": "Enterprise AI leader"},
        "resume_path": "staging/cv.pdf",
        "cover_letter_path": "staging/cover-letter.txt",
        "cover_letter_text": " ".join(["word"] * 120),
        "cover_letter_word_count": 120,
        "change_summary": ["强化企业级 LLM 平台经验"],
        "check_order": ["reviewer", "ats", "facts"],
        "reviewer": {"passed": True, "findings": []},
        "ats": {"passed": False, "findings": ["可增加关键词"]},
        "facts": {"passed": True, "findings": []},
        "engine_provenance": {"engine": "CC/Codex"},
        "prompt_provenance": {"version": "v1"},
    }


def test_task_binds_all_immutable_inputs_and_language_contract(
    tmp_path: Path,
) -> None:
    profile, bundle, snapshot, evaluation = _inputs(tmp_path)
    adapter = ApplicationMaterialAdapter(COMMIT, "application-material.v1")

    task = adapter.build_task(
        task_id="task-1",
        material_version=1,
        profile=profile,
        bundle=bundle,
        snapshot=snapshot,
        evaluation=evaluation,
        feedback="Emphasise leadership",
    )

    assert task.capability_paths == [
        ".claude/skills/job-application-assistant/SKILL.md",
        ".claude/skills/job-application-assistant/05-cv-templates.md",
        ".claude/skills/job-application-assistant/06-cover-letter-templates.md",
    ]
    assert task.document_language == "en"
    assert task.summary_language == "zh-CN"
    assert task.cover_letter_word_range == (100, 300)
    assert task.feedback == "Emphasise leadership"
    assert len(task.source_cv_hash) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("job_id", "other", "job"),
        ("snapshot_hash", "f" * 64, "snapshot"),
        ("profile_version", 3, "profile"),
        ("evaluation_id", "other", "evaluation"),
        ("material_version", 2, "version"),
        ("integration_commit", "f" * 40, "integration"),
        ("source_cv_hash", "f" * 64, "source CV"),
    ],
)
def test_result_rejects_identity_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    profile, bundle, snapshot, evaluation = _inputs(tmp_path)
    adapter = ApplicationMaterialAdapter(COMMIT, "application-material.v1")
    task = adapter.build_task(
        task_id="task-1",
        material_version=1,
        profile=profile,
        bundle=bundle,
        snapshot=snapshot,
        evaluation=evaluation,
    )
    payload = _result(task)
    payload[field] = value

    with pytest.raises(ValueError, match=message):
        adapter.validate_result(task, payload)


def test_result_requires_artifacts_word_limit_and_ordered_checks(
    tmp_path: Path,
) -> None:
    profile, bundle, snapshot, evaluation = _inputs(tmp_path)
    adapter = ApplicationMaterialAdapter(COMMIT, "application-material.v1")
    task = adapter.build_task(
        task_id="task-1",
        material_version=1,
        profile=profile,
        bundle=bundle,
        snapshot=snapshot,
        evaluation=evaluation,
    )
    valid = _result(task)
    result = adapter.validate_result(task, valid)
    assert result.cover_letter_word_count == 120

    for mutation in (
        {"resume_path": ""},
        {"cover_letter_word_count": 99},
        {"check_order": ["facts", "reviewer", "ats"]},
    ):
        payload = {**valid, **mutation}
        with pytest.raises(ValueError):
            adapter.validate_result(task, payload)
