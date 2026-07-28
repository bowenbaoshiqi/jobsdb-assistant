from pathlib import Path

import fitz

from src.materials.pdf_validator import validate_tailored_pdf
from src.materials.template import ResumeTemplate


def _pdf(
    path: Path,
    *,
    frozen_text: str = "Frozen work experience.",
    frozen_x: float = 58.0,
    second_x: float = 41.0,
    pages: int = 2,
) -> Path:
    document = fitz.open()
    first = document.new_page(width=595.2756, height=841.8898)
    first.insert_text((67, 125), "Editable summary.", fontsize=9.6)
    first.insert_text((41, 502), "WORK EXPERIENCE", fontsize=11)
    first.insert_text((frozen_x, 530), frozen_text, fontsize=9.6)
    if pages == 2:
        second = document.new_page(width=595.2756, height=841.8898)
        second.insert_text((second_x, 50), "Frozen second page.", fontsize=11)
    document.save(path)
    document.close()
    return path


def test_validator_accepts_only_editable_region_changes(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(tmp_path / "generated.pdf")
    with fitz.open(generated) as document:
        page = document[0]
        page.add_redact_annot(fitz.Rect(60, 110, 560, 180))
        page.apply_redactions()
        page.insert_text((67, 125), "Tailored summary.", fontsize=9.6)
        document.save(tmp_path / "tailored.pdf")

    report = validate_tailored_pdf(
        source,
        tmp_path / "tailored.pdf",
        ResumeTemplate.v5(),
    )

    assert report.passed
    assert report.codes == ()
    assert report.page_count == 2
    assert report.extractable_characters > 0


def test_validator_rejects_changed_work_experience(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(
        tmp_path / "generated.pdf",
        frozen_text="Fabricated work experience.",
    )

    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert not report.passed
    assert "frozen_text_changed" in report.codes


def test_validator_rejects_frozen_coordinate_shift(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(tmp_path / "generated.pdf", frozen_x=60.0)

    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert "frozen_geometry_changed" in report.codes


def test_validator_rejects_page_two_coordinate_shift(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(tmp_path / "generated.pdf", second_x=43.0)

    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert "frozen_geometry_changed" in report.codes


def test_validator_rejects_wrong_page_count(tmp_path: Path) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(tmp_path / "generated.pdf", pages=1)

    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert report.codes == ("page_count_changed",)


def test_validator_rejects_file_larger_than_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = _pdf(tmp_path / "source.pdf")
    generated = _pdf(tmp_path / "generated.pdf")
    monkeypatch.setattr(
        "src.materials.pdf_validator.MAX_PDF_BYTES",
        generated.stat().st_size - 1,
    )

    report = validate_tailored_pdf(
        source,
        generated,
        ResumeTemplate.v5(),
    )

    assert "file_too_large" in report.codes
