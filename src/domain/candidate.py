"""Candidate profile contracts."""

from datetime import datetime

from pydantic import BaseModel, Field, PositiveInt


class CandidateProfile(BaseModel):
    version: PositiveInt
    verified_facts: dict[str, list[str]] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)
    preferences: dict[str, str | int | float | bool] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    writing_style: dict[str, str] = Field(default_factory=dict)
    source_documents: list[str] = Field(default_factory=list)
    created_at: datetime
