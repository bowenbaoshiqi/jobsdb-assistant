from pathlib import Path

import fitz

from src.materials.pdf_renderer import render_tailored_resume
from src.materials.pdf_validator import validate_tailored_pdf
from src.materials.template import ResumeTemplate, TailoredResumeSections


def _public_v5_fixture(path: Path) -> Path:
    document = fitz.open()
    first = document.new_page(width=595.2756, height=841.8898)
    first.insert_text((41, 104), "PROFESSIONAL SUMMARY", fontsize=11)
    first.insert_text((67, 125), "Original summary.", fontsize=9.6)
    first.insert_text((41, 199), "CAREER HIGHLIGHTS", fontsize=11)
    first.insert_text((58, 220), "Original highlights.", fontsize=9.6)
    first.insert_text((41, 390), "CORE COMPETENCIES", fontsize=11)
    first.insert_text((58, 411), "Original competencies.", fontsize=9.6)
    first.insert_text((41, 502), "WORK EXPERIENCE", fontsize=11)
    first.insert_text((58, 530), "Immutable work history.", fontsize=9.6)
    second = document.new_page(width=595.2756, height=841.8898)
    second.insert_text((41, 50), "Immutable education.", fontsize=11)
    document.save(path)
    document.close()
    return path


def test_rendered_v5_changes_only_allowed_regions(tmp_path: Path) -> None:
    source = _public_v5_fixture(tmp_path / "source.pdf")
    generated = tmp_path / "generated.pdf"
    sections = TailoredResumeSections(
        professional_summary="Tailored enterprise AI summary.",
        career_highlights=("One", "Two", "Three", "Four"),
        core_competencies=("Leadership", "Platforms", "Governance"),
    )

    render = render_tailored_resume(
        source,
        generated,
        sections,
        ResumeTemplate.v5(),
    )
    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert render.overflow == ()
    assert report.passed
    with fitz.open(generated) as document:
        text = "\n".join(page.get_text() for page in document)
    assert "Tailored enterprise AI summary." in text
    assert "Immutable work history." in text
    assert "Immutable education." in text
