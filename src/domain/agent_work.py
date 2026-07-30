"""Stable contracts between Python workflow state and an active AI Agent."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = 1


class AgentWorkKind(str, Enum):
    CANDIDATE_QUESTIONS = "candidate_questions"
    CANDIDATE_PROPOSAL = "candidate_proposal"
    JOB_EVALUATION = "job_evaluation"
    APPLICATION_MATERIAL = "application_material"
    HUMAN_RESPONSE = "human_response"


class AgentWorkStatus(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    HUMAN_REQUIRED = "human_required"
    COMPLETED = "completed"
    FAILED = "failed"
    IDLE = "idle"
    STOPPED = "stopped"


class AgentSessionStatus(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    FAILED = "failed"


class AgentWorkEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol_version: Literal[1] = PROTOCOL_VERSION
    session: str = Field(min_length=1)
    state: Literal[AgentWorkStatus.CLAIMED] = AgentWorkStatus.CLAIMED
    work_id: str = Field(pattern=r"^work-[a-f0-9]{24}$")
    kind: AgentWorkKind
    task_path: Path
    result_path: Path
    capability_paths: tuple[Path, ...]
    attempt: int = Field(ge=1)
    lease_expires_at: datetime


class AgentHumanGate(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol_version: Literal[1] = PROTOCOL_VERSION
    session: str = Field(min_length=1)
    state: Literal[AgentWorkStatus.HUMAN_REQUIRED] = (
        AgentWorkStatus.HUMAN_REQUIRED
    )
    work_id: str = Field(pattern=r"^work-[a-f0-9]{24}$")
    prompt_path: Path
    response_path: Path


class AgentNextResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol_version: Literal[1] = PROTOCOL_VERSION
    state: AgentWorkStatus
    work: AgentWorkEnvelope | AgentHumanGate | None = None
    message: str | None = None

    @model_validator(mode="after")
    def validate_state_payload(self) -> "AgentNextResult":
        expects_work = self.state in {
            AgentWorkStatus.CLAIMED,
            AgentWorkStatus.HUMAN_REQUIRED,
        }
        if expects_work != (self.work is not None):
            raise ValueError("work-bearing state and envelope must match")
        if self.work is not None and self.work.state is not self.state:
            raise ValueError("result state and work state must match")
        return self


class AgentSubmission(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol_version: Literal[1] = PROTOCOL_VERSION
    session: str = Field(min_length=1)
    work_id: str = Field(pattern=r"^work-[a-f0-9]{24}$")
    result_path: Path
