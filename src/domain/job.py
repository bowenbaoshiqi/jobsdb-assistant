"""JobsDB job contracts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApplyType(str, Enum):
    QUICK_APPLY = "quick_apply"
    APPLY = "apply"
    UNKNOWN = "unknown"


class Job(BaseModel):
    jobsdb_job_id: str = Field(min_length=1)
    canonical_url: str
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str | None = None
    apply_type: ApplyType = ApplyType.UNKNOWN
    first_seen: datetime
    last_seen: datetime
    current_snapshot_id: str | None = None


class JobSnapshot(BaseModel):
    job_id: str = Field(min_length=1)
    jd_text: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime
    is_active: bool = True
