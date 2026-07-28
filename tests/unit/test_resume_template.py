import pytest
from pydantic import ValidationError

from src.materials.template import ResumeTemplate, TailoredResumeSections


def test_sections_require_four_highlights() -> None:
    with pytest.raises(ValidationError):
        TailoredResumeSections(
            professional_summary="Enterprise AI leader.",
            career_highlights=("Only one",),
            core_competencies=("Leadership", "Platforms", "Governance"),
        )


def test_sections_require_three_competency_groups() -> None:
    with pytest.raises(ValidationError):
        TailoredResumeSections(
            professional_summary="Enterprise AI leader.",
            career_highlights=("One", "Two", "Three", "Four"),
            core_competencies=("Only one",),
        )


def test_v5_regions_are_fixed_above_work_experience() -> None:
    template = ResumeTemplate.v5()

    assert template.id == "bowen-v5"
    assert template.page_count == 2
    assert template.frozen_y == 492.0
    assert tuple(region.name for region in template.regions) == (
        "professional_summary",
        "career_highlights",
        "core_competencies",
    )
    assert max(region.rect[3] for region in template.regions) < (
        template.frozen_y
    )


def test_v5_template_has_fixed_font_metrics() -> None:
    template = ResumeTemplate.v5()

    assert {region.font_size for region in template.regions} == {9.6}
    assert {region.line_height for region in template.regions} == {12.4}
    assert {region.font_name for region in template.regions} == {"ArialMT"}
