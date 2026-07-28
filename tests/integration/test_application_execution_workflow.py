from datetime import UTC, datetime
from pathlib import Path

from src.application.execute_application import ApplicationExecutionService
from src.domain.application_execution import ApplicationExecutionStatus
from src.domain.job import ApplyType, JobDetailCapture
from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
    MaterialMode,
    MaterialReviewAction,
)
from src.jobsdb.resumes import RemoteResumeReceipt
from src.storage.application_execution_repository import (
    ApplicationExecutionRepository,
)
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository
from src.storage.models import ApplyResult, ApplyStatus

NOW = datetime(2026, 7, 28, tzinfo=UTC)


class ResumeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    async def replace_all_with(
        self,
        pdf: Path,
        remote_name: str,
    ) -> RemoteResumeReceipt:
        self.calls.append((pdf, remote_name))
        return RemoteResumeReceipt(remote_name, NOW)


class Wizard:
    def __init__(self) -> None:
        self.prepared = []
        self.submitted = []

    async def prepare(self, context):
        self.prepared.append(context)
        return ApplyResult(
            status=ApplyStatus.READY_FOR_REVIEW,
            job_id=context.job_id,
        )

    async def submit(self, context):
        self.submitted.append(context)
        return ApplyResult(
            status=ApplyStatus.SUBMITTED,
            job_id=context.job_id,
        )


def _service(
    tmp_path: Path,
    *,
    apply_type: ApplyType = ApplyType.QUICK_APPLY,
    material_mode: MaterialMode = (
        MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    ),
):
    database = Database(str(tmp_path / "jobs.db"))
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="job-1",
            canonical_url="https://hk.jobsdb.com/job/job-1",
            title="Head of AI",
            company="Example Corporation",
            location="Hong Kong",
            jd_text="Lead enterprise AI.",
            apply_type=apply_type,
        ),
        captured_at=NOW,
    )
    snapshot = database.get_current_job_snapshot_record("job-1")
    assert snapshot is not None
    resume = tmp_path / "cv.pdf"
    if material_mode is not MaterialMode.COVER_LETTER_ONLY:
        resume.write_bytes(
            b"%PDF-1.7\n" + b"x" * 40 + b"\n%%EOF\n"
        )
    cover = tmp_path / "cover.txt"
    cover.write_text(" ".join(["approved"] * 120), encoding="utf-8")
    import hashlib

    materials = MaterialRepository(database)
    materials.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=int(snapshot.snapshot_id),
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={},
        created_at=NOW,
    )
    materials.save_package(
        task_id="task-1",
        package=ApplicationPackage(
            id="package-1",
            job_id="job-1",
            evaluation_id="evaluation-1",
            profile_version=1,
            version=1,
            material_mode=material_mode,
            resume=(
                None
                if material_mode is MaterialMode.COVER_LETTER_ONLY
                else MaterialArtifact(
                    path=str(resume),
                    sha256=hashlib.sha256(
                        resume.read_bytes()
                    ).hexdigest(),
                )
            ),
            cover_letter=MaterialArtifact(
                path=str(cover),
                sha256=hashlib.sha256(cover.read_bytes()).hexdigest(),
            ),
            cover_letter_word_count=120,
            reviewer=MaterialCheck(),
            ats=MaterialCheck(),
            facts=MaterialCheck(),
            layout=MaterialCheck(),
            created_at=NOW,
        ),
        saved_at=NOW,
    )
    materials.record_review(
        "package-1",
        MaterialReviewAction.APPROVE,
        reviewed_at=NOW,
    )
    resumes = ResumeManager()
    wizard = Wizard()
    executions = ApplicationExecutionRepository(database)
    return (
        ApplicationExecutionService(
            database=database,
            materials=materials,
            executions=executions,
            resume_manager=resumes,
            wizard=wizard,
            now=lambda: NOW,
        ),
        executions,
        resumes,
        wizard,
    )


async def test_queue_and_worker_prepare_bind_current_approved_package(
    tmp_path: Path,
) -> None:
    service, executions, resumes, wizard = _service(tmp_path)

    queued = service.queue("job-1", account_alias="personal")
    assert queued.identity.package_id == "package-1"
    assert await service.run_next()

    prepared = executions.get(queued.id)
    assert prepared.status is ApplicationExecutionStatus.PREPARING_RESUME
    assert await service.run_next()
    ready = executions.get(queued.id)
    assert ready.status is ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION
    assert resumes.calls[0][1].startswith("JBA_job-1_v1_")
    assert wizard.prepared[0].resume_sha256 == queued.identity.resume_sha256


async def test_cover_letter_only_prepare_keeps_default_resume(
    tmp_path: Path,
) -> None:
    service, executions, resumes, wizard = _service(
        tmp_path,
        material_mode=MaterialMode.COVER_LETTER_ONLY,
    )

    queued = service.queue("job-1", account_alias="personal")
    await service.run_next()
    await service.run_next()

    assert executions.get(queued.id).status is (
        ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    assert resumes.calls == []
    assert wizard.prepared[0].material_mode is (
        MaterialMode.COVER_LETTER_ONLY
    )
    assert wizard.prepared[0].resume_filename is None


async def test_confirm_then_worker_submits_exact_execution(
    tmp_path: Path,
) -> None:
    service, executions, _resumes, wizard = _service(tmp_path)
    queued = service.queue("job-1", account_alias="personal")
    await service.run_next()
    await service.run_next()

    confirmed = service.confirm_submission(queued.id)
    assert confirmed.status is ApplicationExecutionStatus.SUBMITTING
    assert await service.run_next()

    assert executions.get(queued.id).status is (
        ApplicationExecutionStatus.SUBMITTED
    )
    assert wizard.submitted[0].package_id == "package-1"


async def test_queue_is_idempotent_and_refuses_submitted_duplicate(
    tmp_path: Path,
) -> None:
    service, _executions, _resumes, _wizard = _service(tmp_path)
    first = service.queue("job-1", account_alias="personal")
    assert service.queue("job-1", account_alias="personal").id == first.id
    await service.run_next()
    await service.run_next()
    service.confirm_submission(first.id)
    await service.run_next()

    try:
        service.queue("job-1", account_alias="personal")
    except ValueError as exc:
        assert "already submitted" in str(exc)
    else:
        raise AssertionError("duplicate submitted job must be rejected")


def test_queue_retries_same_failed_execution(tmp_path: Path) -> None:
    service, executions, _resumes, _wizard = _service(tmp_path)
    first = service.queue("job-1", account_alias="personal")
    executions.transition(
        first.id,
        ApplicationExecutionStatus.FAILED,
        at=NOW,
        error_code="login_failed",
    )

    retried = service.queue("job-1", account_alias="personal")

    assert retried.id == first.id
    assert retried.status is ApplicationExecutionStatus.QUEUED
    assert retried.error_code is None


def test_manual_apply_handoff_uses_approved_material(tmp_path: Path) -> None:
    service, executions, _resumes, _wizard = _service(
        tmp_path,
        apply_type=ApplyType.APPLY,
    )

    handoff = service.manual_handoff(
        "job-1",
        account_alias="personal",
    )

    assert handoff.job_url == "https://hk.jobsdb.com/job/job-1"
    assert handoff.resume_path.name == "cv.pdf"
    assert len(handoff.cover_letter_text.split()) == 120
    assert executions.get(handoff.execution_id).status is (
        ApplicationExecutionStatus.MANUAL_HANDOFF
    )


def test_cover_only_manual_handoff_uses_default_resume(
    tmp_path: Path,
) -> None:
    service, _executions, _resumes, _wizard = _service(
        tmp_path,
        apply_type=ApplyType.APPLY,
        material_mode=MaterialMode.COVER_LETTER_ONLY,
    )

    handoff = service.manual_handoff(
        "job-1",
        account_alias="personal",
    )

    assert handoff.resume_path is None
    assert len(handoff.cover_letter_text.split()) == 120
