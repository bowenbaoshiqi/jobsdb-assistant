"""Application workflow state contracts."""

from enum import Enum


class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    EVALUATED = "evaluated"
    WAITING_FIRST_APPROVAL = "waiting_first_approval"
    GENERATING_MATERIALS = "generating_materials"
    WAITING_SECOND_APPROVAL = "waiting_second_approval"
    QUEUED = "queued"
    AUTO_APPLYING = "auto_applying"
    MANUAL_APPLY_READY = "manual_apply_ready"
    SUBMITTED = "submitted"
    SUBMITTED_MANUALLY = "submitted_manually"
    MANUAL_ACTION_REQUIRED = "manual_action_required"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    ABANDONED = "abandoned"
