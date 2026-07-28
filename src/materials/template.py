"""Fixed geometry and structured content for the v0.6 v5 resume."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TailoredResumeSections(BaseModel):
    model_config = ConfigDict(frozen=True)

    professional_summary: str = Field(min_length=1)
    career_highlights: tuple[str, str, str, str]
    core_competencies: tuple[str, str, str]


class RegionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Literal[
        "professional_summary",
        "career_highlights",
        "core_competencies",
    ]
    rect: tuple[float, float, float, float]
    font_name: str
    font_size: float
    line_height: float
    maximum_lines: int
    bullet_items: bool = False


class ResumeTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    page_count: int
    page_size: tuple[float, float]
    frozen_y: float
    regions: tuple[RegionSpec, RegionSpec, RegionSpec]

    @classmethod
    def v5(cls) -> ResumeTemplate:
        common = {
            "font_name": "ArialMT",
            "font_size": 9.6,
            "line_height": 12.4,
        }
        return cls(
            id="bowen-v5",
            page_count=2,
            page_size=(595.2756, 841.8898),
            frozen_y=492.0,
            regions=(
                RegionSpec(
                    name="professional_summary",
                    rect=(67.0, 112.0, 560.0, 179.0),
                    maximum_lines=5,
                    **common,
                ),
                RegionSpec(
                    name="career_highlights",
                    rect=(58.0, 207.0, 560.0, 372.0),
                    maximum_lines=12,
                    bullet_items=True,
                    **common,
                ),
                RegionSpec(
                    name="core_competencies",
                    rect=(58.0, 398.0, 560.0, 484.0),
                    maximum_lines=6,
                    bullet_items=True,
                    **common,
                ),
            ),
        )
