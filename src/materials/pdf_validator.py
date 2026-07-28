"""Blocking integrity checks for locally rendered tailored resumes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from src.materials.template import ResumeTemplate

MAX_PDF_BYTES = 5 * 1024 * 1024
GEOMETRY_TOLERANCE = 0.2
FONT_SIZE_TOLERANCE = 0.05


@dataclass(frozen=True)
class _Span:
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float


@dataclass(frozen=True)
class PdfIntegrityReport:
    passed: bool
    codes: tuple[str, ...]
    findings: tuple[str, ...]
    page_count: int
    extractable_characters: int
    file_size_bytes: int


def _spans(
    document: fitz.Document,
    template: ResumeTemplate,
) -> tuple[_Span, ...]:
    result: list[_Span] = []
    for page_number, page in enumerate(document):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", ()):
                for span in line.get("spans", ()):
                    text = span["text"]
                    if not text.strip():
                        continue
                    bbox = tuple(float(value) for value in span["bbox"])
                    if page_number == 0 and bbox[1] < template.frozen_y:
                        continue
                    result.append(
                        _Span(
                            page=page_number,
                            text=text,
                            bbox=bbox,
                            font_size=float(span["size"]),
                        )
                    )
    return tuple(result)


def _same_geometry(left: _Span, right: _Span) -> bool:
    if left.page != right.page:
        return False
    if abs(left.font_size - right.font_size) > FONT_SIZE_TOLERANCE:
        return False
    return all(
        abs(first - second) <= GEOMETRY_TOLERANCE
        for first, second in zip(left.bbox, right.bbox, strict=True)
    )


def validate_tailored_pdf(
    source: Path,
    generated: Path,
    template: ResumeTemplate,
) -> PdfIntegrityReport:
    generated = generated.resolve()
    size = generated.stat().st_size if generated.is_file() else 0
    try:
        source_document = fitz.open(source.resolve())
        generated_document = fitz.open(generated)
    except Exception as exc:
        return PdfIntegrityReport(
            passed=False,
            codes=("invalid_pdf",),
            findings=(f"PDF cannot be opened: {exc}",),
            page_count=0,
            extractable_characters=0,
            file_size_bytes=size,
        )
    with source_document, generated_document:
        page_count = len(generated_document)
        extracted = sum(
            len(page.get_text().strip()) for page in generated_document
        )
        if (
            len(source_document) != template.page_count
            or page_count != template.page_count
        ):
            return PdfIntegrityReport(
                passed=False,
                codes=("page_count_changed",),
                findings=(
                    f"Expected {template.page_count} pages, got {page_count}.",
                ),
                page_count=page_count,
                extractable_characters=extracted,
                file_size_bytes=size,
            )

        codes: list[str] = []
        findings: list[str] = []
        if size > MAX_PDF_BYTES:
            codes.append("file_too_large")
            findings.append(
                f"PDF size {size} bytes exceeds {MAX_PDF_BYTES} bytes."
            )
        if extracted == 0:
            codes.append("text_not_extractable")
            findings.append("Generated PDF has no extractable text.")

        source_spans = _spans(source_document, template)
        generated_spans = _spans(generated_document, template)
        source_text = tuple(item.text for item in source_spans)
        generated_text = tuple(item.text for item in generated_spans)
        if source_text != generated_text:
            codes.append("frozen_text_changed")
            findings.append(
                "Work Experience or a later section differs from the source."
            )
        elif len(source_spans) != len(generated_spans) or any(
            not _same_geometry(left, right)
            for left, right in zip(
                source_spans,
                generated_spans,
                strict=True,
            )
        ):
            codes.append("frozen_geometry_changed")
            findings.append(
                "Work Experience or a later section changed position or font."
            )

        return PdfIntegrityReport(
            passed=not codes,
            codes=tuple(codes),
            findings=tuple(findings),
            page_count=page_count,
            extractable_characters=extracted,
            file_size_bytes=size,
        )
