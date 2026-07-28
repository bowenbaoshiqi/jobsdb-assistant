"""Immutable contracts for the approved-material application lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.job import ApplyType


class ApplicationExecutionStatus(str, Enum):
    QUEUED = "queued"
    PREPARING_RESUME = "preparing_resume"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    SUBMITTING = "submitting"
    WAITING_FOR_HUMAN = "waiting_for_human"
    SUBMISSION_UNCERTAIN = "submission_uncertain"
    SUBMITTED = "submitted"
    FAILED = "failed"
    MANUAL_HANDOFF = "manual_handoff"


_TERMINAL = {
    ApplicationExecutionStatus.SUBMITTED,
    ApplicationExecutionStatus.MANUAL_HANDOFF,
}

_TRANSITIONS = {
    ApplicationExecutionStatus.QUEUED: {
        ApplicationExecutionStatus.PREPARING_RESUME,
        ApplicationExecutionStatus.MANUAL_HANDOFF,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.PREPARING_RESUME: {
        ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION,
        ApplicationExecutionStatus.WAITING_FOR_HUMAN,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.WAITING_FOR_CONFIRMATION: {
        ApplicationExecutionStatus.SUBMITTING,
        ApplicationExecutionStatus.PREPARING_RESUME,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.SUBMITTING: {
        ApplicationExecutionStatus.SUBMITTED,
        ApplicationExecutionStatus.SUBMISSION_UNCERTAIN,
        ApplicationExecutionStatus.WAITING_FOR_HUMAN,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.WAITING_FOR_HUMAN: {
        ApplicationExecutionStatus.PREPARING_RESUME,
        ApplicationExecutionStatus.SUBMITTING,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.SUBMISSION_UNCERTAIN: {
        ApplicationExecutionStatus.SUBMITTED,
        ApplicationExecutionStatus.FAILED,
    },
    ApplicationExecutionStatus.FAILED: {
        ApplicationExecutionStatus.QUEUED,
    },
}


class ApplicationIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    account_alias: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    material_version: int = Field(gt=0)
    resume_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    cover_letter_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    apply_type: ApplyType

    def idempotency_key(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


class ApplicationExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    identity: ApplicationIdentity
    status: ApplicationExecutionStatus
    remote_resume_filename: str = Field(min_length=1)
    error_code: str | None = None
    error_message: str | None = None
    screenshot_path: str | None = None
    created_at: datetime
    updated_at: datetime

    def transition(
        self,
        status: ApplicationExecutionStatus,
        *,
        at: datetime,
        error_code: str | None = None,
        error_message: str | None = None,
        screenshot_path: str | None = None,
    ) -> ApplicationExecution:
        if self.status in _TERMINAL:
            raise ValueError(f"terminal application status: {self.status.value}")
        if status not in _TRANSITIONS.get(self.status, set()):
            raise ValueError(
                "invalid application transition: "
                f"{self.status.value} -> {status.value}"
            )
        return self.model_copy(
            update={
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
                "screenshot_path": screenshot_path,
                "updated_at": at,
            }
        )


class ApplicationExecutionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    execution_id: str
    from_status: ApplicationExecutionStatus
    to_status: ApplicationExecutionStatus
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
