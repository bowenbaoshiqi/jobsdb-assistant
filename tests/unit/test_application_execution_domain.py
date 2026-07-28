from datetime import UTC, datetime

import pytest

from src.domain.application_execution import (
    ApplicationExecution,
    ApplicationExecutionStatus,
    ApplicationIdentity,
)
from src.domain.job import ApplyType

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def _identity(*, material_version: int = 1) -> ApplicationIdentity:
    return ApplicationIdentity(
        job_id="job-1",
        snapshot_id="11",
        snapshot_hash="a" * 64,
        account_alias="personal",
        package_id=f"package-{material_version}",
        material_version=material_version,
        resume_sha256="b" * 64,
        cover_letter_sha256="c" * 64,
        apply_type=ApplyType.QUICK_APPLY,
    )


def _execution(
    status: ApplicationExecutionStatus = ApplicationExecutionStatus.QUEUED,
) -> ApplicationExecution:
    return ApplicationExecution(
        id="execution-1",
        identity=_identity(),
        status=status,
        remote_resume_filename="JBA_job-1_v1_bbbbbbbb.pdf",
        created_at=NOW,
        updated_at=NOW,
    )


def test_application_identity_changes_with_material_version() -> None:
    assert _identity(material_version=1).idempotency_key() != _identity(
        material_version=2
    ).idempotency_key()


def test_application_identity_is_stable() -> None:
    assert _identity().idempotency_key() == _identity().idempotency_key()


def test_submitted_cannot_transition_back_to_queued() -> None:
    with pytest.raises(ValueError, match="terminal"):
        _execution(ApplicationExecutionStatus.SUBMITTED).transition(
            ApplicationExecutionStatus.QUEUED,
            at=NOW,
        )


def test_queued_can_transition_to_resume_preparation() -> None:
    changed = _execution().transition(
        ApplicationExecutionStatus.PREPARING_RESUME,
        at=NOW,
    )

    assert changed.status is ApplicationExecutionStatus.PREPARING_RESUME


def test_invalid_forward_transition_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid application transition"):
        _execution().transition(
            ApplicationExecutionStatus.SUBMITTED,
            at=NOW,
        )
