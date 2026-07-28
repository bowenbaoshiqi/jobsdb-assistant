from pathlib import Path

import fitz

from src.materials.pdf_renderer import render_tailored_resume
from src.materials.template import ResumeTemplate, TailoredResumeSections


def _source_pdf(path: Path) -> Path:
    document = fitz.open()
    first = document.new_page(width=595.2756, height=841.8898)
    first.insert_text((41, 104), "PROFESSIONAL SUMMARY", fontsize=11)
    first.insert_text((67, 125), "Original summary.", fontsize=9.6)
    first.insert_text((41, 199), "CAREER HIGHLIGHTS", fontsize=11)
    first.insert_text((58, 220), "Original highlights.", fontsize=9.6)
    first.insert_text((41, 390), "CORE COMPETENCIES", fontsize=11)
    first.insert_text((58, 411), "Original competencies.", fontsize=9.6)
    first.insert_text((41, 502), "WORK EXPERIENCE", fontsize=11)
    first.insert_text((58, 530), "Frozen role and achievement.", fontsize=9.6)
    second = document.new_page(width=595.2756, height=841.8898)
    second.insert_text((41, 50), "FROZEN SECOND PAGE", fontsize=11)
    document.save(path)
    document.close()
    return path


def _sections() -> TailoredResumeSections:
    return TailoredResumeSections(
        professional_summary=(
            "Chief AI Architect leading enterprise LLM platforms and "
            "cross-functional delivery."
        ),
        career_highlights=(
            "Enterprise AI Platform - Unified production LLM services.",
            "Matrix Leadership - Enabled delivery across business teams.",
            "Business Impact - Delivered measurable operational outcomes.",
            "AI Governance - Deployed secure agent guardrails.",
        ),
        core_competencies=(
            "Enterprise AI Leadership - Team and matrix leadership",
            "LLM and Agent Platforms - RAG, LLMOps and optimization",
            "Architecture Governance - Security and technical approval",
        ),
    )


def test_renderer_preserves_page_count_and_frozen_text(
    tmp_path: Path,
) -> None:
    source = _source_pdf(tmp_path / "source.pdf")
    output = tmp_path / "output.pdf"

    result = render_tailored_resume(
        source,
        output,
        _sections(),
        ResumeTemplate.v5(),
    )

    assert result.page_count == 2
    assert result.overflow == ()
    with fitz.open(output) as rendered:
        text = "\n".join(page.get_text() for page in rendered)
    assert "Chief AI Architect leading enterprise LLM" in text
    assert "Original summary." not in text
    assert "Frozen role and achievement." in text
    assert "FROZEN SECOND PAGE" in text


def test_renderer_reports_overflow_without_emitting_partial_pdf(
    tmp_path: Path,
) -> None:
    source = _source_pdf(tmp_path / "source.pdf")
    output = tmp_path / "output.pdf"
    sections = _sections().model_copy(
        update={"professional_summary": "word " * 500}
    )

    result = render_tailored_resume(
        source,
        output,
        sections,
        ResumeTemplate.v5(),
    )

    assert result.overflow[0].region == "professional_summary"
    assert result.overflow[0].maximum_lines == 5
    assert not output.exists()


def test_renderer_rejects_wrong_source_page_count(tmp_path: Path) -> None:
    source = tmp_path / "one-page.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()

    result = render_tailored_resume(
        source,
        tmp_path / "output.pdf",
        _sections(),
        ResumeTemplate.v5(),
    )

    assert result.overflow[0].code == "template_mismatch"
