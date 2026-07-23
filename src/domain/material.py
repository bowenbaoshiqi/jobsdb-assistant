"""Tailored application-material contracts."""

from pydantic import BaseModel, Field, PositiveInt


class MaterialArtifact(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ApplicationPackage(BaseModel):
    job_id: str
    evaluation_id: str
    profile_version: PositiveInt
    version: PositiveInt
    resume: MaterialArtifact
    cover_letter: MaterialArtifact
    cover_letter_word_count: int = Field(ge=100, le=300)
    reviewer_passed: bool = False
    ats_passed: bool = False
    facts_passed: bool = False
