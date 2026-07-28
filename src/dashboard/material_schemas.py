"""Requests and compact responses for material review endpoints."""

from pydantic import BaseModel, Field

from src.domain.material import MaterialMode


class MaterialBatchRequest(BaseModel):
    material_mode: MaterialMode = (
        MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    )


class MaterialApprovalRequest(BaseModel):
    fact_warning_overridden: bool = False


class MaterialFeedbackRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=2000)
