"""Tailored application-material contracts."""

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    model_validator,
)


class MaterialTaskStatus(str, Enum):
    WAITING_FOR_AGENT = "waiting_for_agent"
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class MaterialMode(str, Enum):
    COVER_LETTER_ONLY = "cover_letter_only"
    TAILORED_RESUME_AND_COVER_LETTER = (
        "tailored_resume_and_cover_letter"
    )


class MaterialReviewStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    PENDING_REVIEW_WITH_FACT_WARNING = (
        "pending_review_with_fact_warning"
    )
    APPROVED = "approved"
    APPROVED_WITH_FACT_OVERRIDE = "approved_with_fact_override"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MaterialReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REGENERATE = "regenerate"


class MaterialArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MaterialCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool = True
    findings: list[str] = Field(default_factory=list)


class ApplicationPackage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = ""
    job_id: str
    evaluation_id: str
    profile_version: PositiveInt
    version: PositiveInt
    material_mode: MaterialMode = (
        MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    )
    resume: MaterialArtifact | None
    cover_letter: MaterialArtifact
    cover_letter_word_count: int = Field(ge=100, le=300)
    reviewer: MaterialCheck = Field(default_factory=MaterialCheck)
    ats: MaterialCheck = Field(default_factory=MaterialCheck)
    facts: MaterialCheck = Field(default_factory=MaterialCheck)
    layout: MaterialCheck = Field(default_factory=MaterialCheck)
    review_status: MaterialReviewStatus | None = None
    created_at: datetime | None = None
    # Compatibility fields retained until the v0.5 persistence migration.
    reviewer_passed: bool = False
    ats_passed: bool = False
    facts_passed: bool = False

    @model_validator(mode="after")
    def default_review_status(self) -> "ApplicationPackage":
        if (
            self.material_mode
            is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
            and self.resume is None
        ):
            raise ValueError(
                "resume is required for tailored material mode"
            )
        if (
            self.material_mode is MaterialMode.COVER_LETTER_ONLY
            and self.resume is not None
        ):
            raise ValueError(
                "cover-letter-only package must not contain a resume"
            )
        if self.review_status is not None:
            return self
        status = (
            MaterialReviewStatus.PENDING_REVIEW
            if self.facts.passed and not self.facts.findings
            else MaterialReviewStatus.PENDING_REVIEW_WITH_FACT_WARNING
        )
        object.__setattr__(self, "review_status", status)
        return self


class MaterialReviewEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    package_id: str
    action: MaterialReviewAction
    resulting_status: MaterialReviewStatus
    feedback: str | None = None
    fact_warning_overridden: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def validate_fact_override(self) -> "MaterialReviewEvent":
        is_override_status = (
            self.resulting_status
            is MaterialReviewStatus.APPROVED_WITH_FACT_OVERRIDE
        )
        if is_override_status != self.fact_warning_overridden:
            raise ValueError(
                "fact warning override flag must match review status"
            )
        return self
