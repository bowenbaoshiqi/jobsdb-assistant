from datetime import UTC, datetime
from pathlib import Path

from src.domain.job import ApplyType, JobDetailCapture
from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
    MaterialReviewAction,
)
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def test_material_state_survives_repository_restart(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"
    database = Database(str(path))
    saved = database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="job-1",
            canonical_url="https://hk.jobsdb.com/job/job-1",
            title="Head of AI",
            company="Example Corporation",
            location="Hong Kong",
            jd_text="Lead enterprise AI.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )
    repository = MaterialRepository(database)
    repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=int(saved.snapshot_id),
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={"private_path": "workspace/task-1.json"},
        created_at=NOW,
    )
    repository.save_package(
        task_id="task-1",
        package=ApplicationPackage(
            id="package-1",
            job_id="job-1",
            evaluation_id="evaluation-1",
            profile_version=1,
            version=1,
            resume=MaterialArtifact(path="cv.pdf", sha256="a" * 64),
            cover_letter=MaterialArtifact(
                path="cover-letter.txt",
                sha256="b" * 64,
            ),
            cover_letter_word_count=120,
            reviewer=MaterialCheck(),
            ats=MaterialCheck(),
            facts=MaterialCheck(),
            created_at=NOW,
        ),
        saved_at=NOW,
    )
    repository.record_review(
        "package-1",
        MaterialReviewAction.APPROVE,
        reviewed_at=NOW,
    )

    restored = MaterialRepository(Database(str(path)))

    assert restored.list_batch("batch-1")[0].payload == {
        "private_path": "workspace/task-1.json"
    }
    assert restored.current_approved_for_job("job-1").id == "package-1"
    assert len(restored.list_review_events("package-1")) == 1
