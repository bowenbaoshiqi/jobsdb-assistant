"""Requests and compact responses for material review endpoints."""

from pydantic import BaseModel, Field


class MaterialApprovalRequest(BaseModel):
    fact_warning_overridden: bool = False


class MaterialFeedbackRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)

