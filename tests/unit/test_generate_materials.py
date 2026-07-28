from datetime import UTC, datetime
from pathlib import Path

import fitz
import pytest

from src.adapters.application_material import ApplicationMaterialAdapter
from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.adapters.checkpoint_io import CheckpointStore
from src.application.generate_materials import MaterialGenerationService
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation, NativeDimension
from src.domain.job import ApplyType, CurrentSnapshotRecord, JobDetailCapture
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)
PROFILE_HASH = "a" * 64


class Projector:
    def __init__(self, root: Path) -> None:
        self.root = root

    def project(self, profile: CandidateProfile) -> CareerOpsProfileBundle:
        cv = self.root / "source-cv.pdf"
        if not cv.exists():
            document = fitz.open()
            first = document.new_page(width=595.2756, height=841.8898)
            first.insert_text(
                (41, 104),
                "PROFESSIONAL SUMMARY",
                fontsize=11,
            )
            first.insert_text((67, 125), "Original summary.", fontsize=9.6)
            first.insert_text((41, 199), "CAREER HIGHLIGHTS", fontsize=11)
            first.insert_text(
                (58, 220),
                "Original highlights.",
                fontsize=9.6,
            )
            first.insert_text((41, 390), "CORE COMPETENCIES", fontsize=11)
            first.insert_text(
                (58, 411),
                "Original competencies.",
                fontsize=9.6,
            )
            first.insert_text((41, 502), "WORK EXPERIENCE", fontsize=11)
            first.insert_text(
                (58, 530),
                "Immutable work history.",
                fontsize=9.6,
            )
            second = document.new_page(width=595.2756, height=841.8898)
            second.insert_text((41, 50), "Immutable education.", fontsize=11)
            document.save(cv)
            document.close()
        return CareerOpsProfileBundle(
            root=self.root,
            profile_id=profile.id,
            profile_version=profile.version,
            profile_hash=PROFILE_HASH,
            projection_version="bundle.v1",
            bundle_hash="b" * 64,
            cv_path=cv,
            profile_yml_path=self.root / "profile.yml",
            profile_md_path=self.root / "profile.md",
            manifest_path=self.root / "manifest.json",
            manifest={},
        )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        id="candidate-1",
        version=1,
        created_at=NOW,
        confirmed_at=NOW,
        content_hash=PROFILE_HASH,
    )


def _snapshot(index: int) -> CurrentSnapshotRecord:
    return CurrentSnapshotRecord(
        snapshot_id=str(index),
        job_id=f"job-{index}",
        title=f"AI Role {index}",
        company="Large Corporation",
        canonical_url=f"https://hk.jobsdb.com/job/job-{index}",
        apply_type=ApplyType.QUICK_APPLY,
        jd_text="Lead enterprise AI.",
        content_hash=f"{index:x}".zfill(64),
    )


def _evaluation(snapshot: CurrentSnapshotRecord) -> JobEvaluation:
    return JobEvaluation(
        id=f"evaluation-{snapshot.job_id}",
        job_snapshot_id=snapshot.snapshot_id,
        profile_version=1,
        profile_hash=PROFILE_HASH,
        snapshot_hash=snapshot.content_hash,
        engine_version="career-ops",
        engine_commit="d" * 40,
        prompt_version="v1",
        overall_score=4,
        dimensions=[
            NativeDimension(code=code, title=code, score=4)
            for code in "ABCDEF"
        ],
        recommendation="Proceed",
        created_at=NOW,
    )


def _service(tmp_path: Path):
    database = Database(":memory:")
    snapshots: list[CurrentSnapshotRecord] = []
    for index in range(1, 6):
        snapshot = _snapshot(index)
        database.save_discovered_job(
            JobDetailCapture(
                jobsdb_job_id=snapshot.job_id,
                canonical_url=snapshot.canonical_url,
                title=snapshot.title,
                company=snapshot.company,
                location="Hong Kong",
                jd_text=snapshot.jd_text,
                apply_type=snapshot.apply_type,
            ),
            captured_at=NOW,
        )
        stored = database.get_current_job_snapshot_record(snapshot.job_id)
        assert stored is not None
        snapshots.append(stored)
    repository = MaterialRepository(database)
    checkpoints = CheckpointStore(tmp_path / "tasks")
    service = MaterialGenerationService(
        repository=repository,
        adapter=ApplicationMaterialAdapter(
            "c" * 40,
            "application-material.v1",
        ),
        checkpoints=checkpoints,
        profile_projector=Projector(tmp_path),
        materials_root=tmp_path / "materials",
    )
    return service, repository, checkpoints, snapshots


def test_five_jobs_create_five_sorted_independent_idempotent_tasks(
    tmp_path: Path,
) -> None:
    service, repository, checkpoints, snapshots = _service(tmp_path)
    evaluations = [_evaluation(item) for item in snapshots]

    first = service.plan_batch(
        batch_id="batch-1",
        profile=_profile(),
        snapshots=list(reversed(snapshots)),
        evaluations=evaluations,
        created_at=NOW,
    )
    repeated = service.plan_batch(
        batch_id="batch-1",
        profile=_profile(),
        snapshots=list(reversed(snapshots)),
        evaluations=evaluations,
        created_at=NOW,
    )

    assert [item.task.job_id for item in first.pending] == [
        f"job-{index}" for index in range(1, 6)
    ]
    assert [item.task.task_id for item in repeated.pending] == [
        item.task.task_id for item in first.pending
    ]
    assert len(repository.list_batch("batch-1")) == 5
    assert all(
        checkpoints.read_task(item.task.task_id)["job_id"] == item.task.job_id
        for item in first.pending
    )


def test_missing_evaluation_fails_before_creating_any_checkpoint(
    tmp_path: Path,
) -> None:
    service, repository, _checkpoints, snapshots = _service(tmp_path)

    with pytest.raises(ValueError, match="current evaluation"):
        service.plan_batch(
            batch_id="batch-1",
            profile=_profile(),
            snapshots=snapshots,
            evaluations=[_evaluation(item) for item in snapshots[:-1]],
            created_at=NOW,
        )

    assert repository.list_batch("batch-1") == []
    assert not (tmp_path / "tasks").exists()


def test_invalid_result_fails_only_its_own_task(tmp_path: Path) -> None:
    service, repository, _checkpoints, snapshots = _service(tmp_path)
    plan = service.plan_batch(
        batch_id="batch-1",
        profile=_profile(),
        snapshots=snapshots[:2],
        evaluations=[_evaluation(item) for item in snapshots[:2]],
        created_at=NOW,
    )

    with pytest.raises(ValueError):
        service.submit(plan.pending[0], {"task_id": "wrong"}, completed_at=NOW)

    tasks = {item.id: item for item in repository.list_batch("batch-1")}
    assert tasks[plan.pending[0].task.task_id].status.value == "failed"
    assert (
        tasks[plan.pending[1].task.task_id].status.value
        == "waiting_for_agent"
    )
