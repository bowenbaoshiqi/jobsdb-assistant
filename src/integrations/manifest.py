"""Load and validate the approved integration lock manifest."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

APPROVED_URLS = frozenset({
    "https://github.com/bowenbaoshiqi/ai-job-search.git",
    "https://github.com/bowenbaoshiqi/career-ops.git",
})


class IntegrationSpec(BaseModel):
    """One exact external capability revision."""

    url: str
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    license: Literal["MIT"]
    contract_version: str = Field(min_length=1)
    required_paths: list[str] = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def approved_url(cls, value: str) -> str:
        if value not in APPROVED_URLS:
            raise ValueError("unapproved integration URL")
        return value


class IntegrationManifest(BaseModel):
    """Versioned collection of approved integrations."""

    schema_version: Literal[1]
    integrations: dict[str, IntegrationSpec]


def load_manifest(path: Path) -> IntegrationManifest:
    """Load a tracked lock manifest without resolving remote state."""
    return IntegrationManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
