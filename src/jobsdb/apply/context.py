"""Immutable approved material supplied to the JobsDB apply wizard."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.material import MaterialMode


class ApplicationMaterialContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    material_mode: MaterialMode = (
        MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
    )
    resume_filename: str | None = Field(
        default=None,
        pattern=r"^JBA_[A-Za-z0-9_-]+_v[1-9][0-9]*_[a-f0-9]{8}\.pdf$"
    )
    resume_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    cover_letter_text: str = Field(min_length=1)
    cover_letter_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_cover_letter_length(self) -> "ApplicationMaterialContext":
        full = (
            self.material_mode
            is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
        )
        if full and (
            self.resume_filename is None or self.resume_sha256 is None
        ):
            raise ValueError("tailored material requires resume identity")
        if not full and (
            self.resume_filename is not None
            or self.resume_sha256 is not None
        ):
            raise ValueError(
                "cover-letter-only context must not contain resume identity"
            )
        if not 100 <= len(self.cover_letter_text.split()) <= 300:
            raise ValueError("cover letter must contain 100-300 words")
        return self
