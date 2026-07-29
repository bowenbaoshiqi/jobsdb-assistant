"""Domain records for the durable parallel evaluation pool."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class AgentPoolStatus(str, Enum):
    STARTING = "starting"
    ACTIVE = "active"
    DRAINING = "draining"
    COMPLETED = "completed"
    STALE = "stale"
    STOPPED = "stopped"


class AgentPoolSlotStatus(str, Enum):
    STARTING = "starting"
    IDLE = "idle"
    ASSIGNED = "assigned"
    REPLACING = "replacing"
    STOPPED = "stopped"


class AgentPoolSlotRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    pool_id: str
    slot_token: str
    ordinal: int
    status: AgentPoolSlotStatus
    generation: int
    current_work_id: str | None = None
    assignment_count: int = 0
    heartbeat_at: datetime | None = None


class AgentPoolRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    session_id: str
    kind: str
    batch_key: str
    status: AgentPoolStatus
    requested_concurrency: int
    actual_concurrency: int
    capability_context_id: str
    profile_context_id: str
    created_at: datetime
    heartbeat_at: datetime
    completed_at: datetime | None = None
    slots: tuple[AgentPoolSlotRecord, ...] = ()


class AgentPoolStatusSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    pool: AgentPoolRecord
    queued: int
    claimed: int
    completed: int
    failed: int
    terminal: bool
