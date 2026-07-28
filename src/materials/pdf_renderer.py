"""Deterministically redraw only the three allowed v5 resume regions."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from src.materials.template import (
    RegionSpec,
    ResumeTemplate,
    TailoredResumeSections,
)


@dataclass(frozen=True)
class RenderOverflow:
    region: str
    maximum_lines: int
    actual_lines: int
    code: str = "content_overflow"


@dataclass(frozen=True)
class RenderResult:
    page_count: int
    overflow: tuple[RenderOverflow, ...] = ()


_ARIAL_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
)


def _font_resource() -> tuple[str, Path | None, fitz.Font]:
    for path in _ARIAL_CANDIDATES:
        if path.is_file():
            return "JBAArial", path, fitz.Font(fontfile=str(path))
    return "helv", None, fitz.Font("helv")


def _wrap_line(
    text: str,
    *,
    width: float,
    font_size: float,
    font: fitz.Font,
    continuation_indent: str,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        measured = font.text_length(candidate, fontsize=font_size)
        if measured <= width:
            current = candidate
            continue
        lines.append(current)
        current = f"{continuation_indent}{word}" if lines else word
    lines.append(current)
    return lines


def _region_lines(
    region: RegionSpec,
    value: str | tuple[str, ...],
    *,
    font_name: str,
    font: fitz.Font,
) -> list[str]:
    width = region.rect[2] - region.rect[0]
    items = (value,) if isinstance(value, str) else value
    lines: list[str] = []
    for item in items:
        text = f"• {item}" if region.bullet_items else item
        indent = "  " if region.bullet_items else ""
        lines.extend(
            _wrap_line(
                text,
                width=width,
                font_size=region.font_size,
                font=font,
                continuation_indent=indent,
            )
        )
    return lines


def _template_mismatch(
    document: fitz.Document,
    template: ResumeTemplate,
) -> RenderOverflow | None:
    if len(document) != template.page_count:
        return RenderOverflow(
            region="template",
            maximum_lines=0,
            actual_lines=0,
            code="template_mismatch",
        )
    expected_width, expected_height = template.page_size
    for page in document:
        if (
            abs(page.rect.width - expected_width) > 1.0
            or abs(page.rect.height - expected_height) > 1.0
        ):
            return RenderOverflow(
                region="template",
                maximum_lines=0,
                actual_lines=0,
                code="template_mismatch",
            )
    return None


def render_tailored_resume(
    source: Path,
    output: Path,
    sections: TailoredResumeSections,
    template: ResumeTemplate,
) -> RenderResult:
    source = source.resolve()
    output = output.resolve()
    with fitz.open(source) as document:
        mismatch = _template_mismatch(document, template)
        if mismatch:
            return RenderResult(page_count=len(document), overflow=(mismatch,))
        font_name, font_path, font = _font_resource()
        values: dict[str, str | tuple[str, ...]] = {
            "professional_summary": sections.professional_summary,
            "career_highlights": sections.career_highlights,
            "core_competencies": sections.core_competencies,
        }
        rendered_lines: dict[str, list[str]] = {}
        overflow: list[RenderOverflow] = []
        for region in template.regions:
            lines = _region_lines(
                region,
                values[region.name],
                font_name=font_name,
                font=font,
            )
            rendered_lines[region.name] = lines
            if len(lines) > region.maximum_lines:
                overflow.append(
                    RenderOverflow(
                        region=region.name,
                        maximum_lines=region.maximum_lines,
                        actual_lines=len(lines),
                    )
                )
        if overflow:
            return RenderResult(
                page_count=len(document),
                overflow=tuple(overflow),
            )

        page = document[0]
        for region in template.regions:
            page.add_redact_annot(fitz.Rect(region.rect), fill=(1, 1, 1))
        page.apply_redactions()
        if font_path is not None:
            page.insert_font(
                fontname=font_name,
                fontfile=str(font_path),
                set_simple=True,
            )
        for region in template.regions:
            y = region.rect[1] + region.font_size
            for line in rendered_lines[region.name]:
                page.insert_text(
                    (region.rect[0], y),
                    line,
                    fontname=font_name,
                    fontsize=region.font_size,
                    set_simple=1,
                    color=(0.102, 0.102, 0.102),
                    overlay=True,
                )
                y += region.line_height

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            suffix=".pdf",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        try:
            document.save(temporary, garbage=4, deflate=True)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        return RenderResult(page_count=len(document))
