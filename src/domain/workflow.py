"""Persisted workflow and AI checkpoint contracts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class WorkflowStage(str, Enum):
    CREATED = "created"
    INTEGRATIONS_CHECKED = "integrations_checked"
    PROFILE_TASK_READY = "profile_task_ready"
    PROFILE_REVIEW_REQUIRED = "profile_review_required"
    PROFILE_READY = "profile_ready"
    DISCOVERY_RUNNING = "discovery_running"
    EVALUATION_TASKS_READY = "evaluation_tasks_ready"
    EVALUATING = "evaluating"
    REPORT_READY = "report_ready"
    COMPLETED = "completed"


class RunCondition(str, Enum):
    ACTIVE = "active"
    WAITING_FOR_AGENT = "waiting_for_agent"
    WAITING_FOR_USER = "waiting_for_user"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    COMPLETED = "completed"


class WorkflowEvent(str, Enum):
    INTEGRATIONS_CHECKED = "integrations_checked"
    PROFILE_REQUIRED = "profile_required"
    PROFILE_TASK_COMPLETED = "profile_task_completed"
    PROFILE_CONFIRMED = "profile_confirmed"
    PROFILE_REUSED = "profile_reused"
    DISCOVERY_STARTED = "discovery_started"
    DISCOVERY_COMPLETED = "discovery_completed"
    EVALUATION_STARTED = "evaluation_started"
    EVALUATION_COMPLETED = "evaluation_completed"
    REPORT_COMPLETED = "report_completed"


class TaskType(str, Enum):
    CANDIDATE_PROFILE = "candidate_profile"
    JOB_EVALUATION = "job_evaluation"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    stage: WorkflowStage
    condition: RunCondition = RunCondition.ACTIVE
    created_at: datetime
    updated_at: datetime
    warning: str | None = None


class AITask(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    run_id: str = Field(min_length=1)
    type: TaskType
    status: TaskStatus
    contract_version: str = Field(min_length=1)
    integration_id: str = Field(min_length=1)
    integration_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: PositiveInt
    created_at: datetime


_TRANSITIONS = {
    (
        WorkflowStage.CREATED,
        WorkflowEvent.INTEGRATIONS_CHECKED,
    ): WorkflowStage.INTEGRATIONS_CHECKED,
    (
        WorkflowStage.INTEGRATIONS_CHECKED,
        WorkflowEvent.PROFILE_REQUIRED,
    ): WorkflowStage.PROFILE_TASK_READY,
    (
        WorkflowStage.INTEGRATIONS_CHECKED,
        WorkflowEvent.PROFILE_REUSED,
    ): WorkflowStage.PROFILE_READY,
    (
        WorkflowStage.PROFILE_TASK_READY,
        WorkflowEvent.PROFILE_TASK_COMPLETED,
    ): WorkflowStage.PROFILE_REVIEW_REQUIRED,
    (
        WorkflowStage.PROFILE_REVIEW_REQUIRED,
        WorkflowEvent.PROFILE_CONFIRMED,
    ): WorkflowStage.PROFILE_READY,
    (
        WorkflowStage.PROFILE_READY,
        WorkflowEvent.DISCOVERY_STARTED,
    ): WorkflowStage.DISCOVERY_RUNNING,
    (
        WorkflowStage.DISCOVERY_RUNNING,
        WorkflowEvent.DISCOVERY_COMPLETED,
    ): WorkflowStage.EVALUATION_TASKS_READY,
    (
        WorkflowStage.EVALUATION_TASKS_READY,
        WorkflowEvent.EVALUATION_STARTED,
    ): WorkflowStage.EVALUATING,
    (
        WorkflowStage.EVALUATING,
        WorkflowEvent.EVALUATION_COMPLETED,
    ): WorkflowStage.REPORT_READY,
    (
        WorkflowStage.REPORT_READY,
        WorkflowEvent.REPORT_COMPLETED,
    ): WorkflowStage.COMPLETED,
}


def next_stage(
    current: WorkflowStage,
    event: WorkflowEvent,
) -> WorkflowStage:
    """Return the only legal next stage for a persisted event."""
    try:
        return _TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise ValueError(
            f"illegal workflow transition: {current.value} + {event.value}"
        ) from exc
