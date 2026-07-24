"""Plain-text report for current native career-ops evaluations."""

from dataclasses import dataclass

from src.domain.evaluation import JobEvaluation
from src.domain.job import ApplyType, CurrentSnapshotRecord


@dataclass(frozen=True)
class EvaluationReportItem:
    snapshot: CurrentSnapshotRecord
    evaluation: JobEvaluation


def _apply_type_label(apply_type: ApplyType) -> str:
    if apply_type is ApplyType.QUICK_APPLY:
        return "Quick Apply"
    if apply_type is ApplyType.APPLY:
        return "Apply"
    return "Unknown"


def render_text(items: list[EvaluationReportItem]) -> str:
    """Render concise results without full JDs or candidate facts."""
    ordered = sorted(
        items,
        key=lambda item: (
            -item.evaluation.overall_score,
            item.snapshot.company.casefold(),
            item.snapshot.title.casefold(),
            item.snapshot.job_id,
        ),
    )
    lines = [f"JobsDB Evaluation Report ({len(ordered)} jobs)"]
    for index, item in enumerate(ordered, start=1):
        evaluation = item.evaluation
        dimensions = " · ".join(
            f"{dimension.code}: "
            f"{dimension.score:.1f}"
            if dimension.score is not None
            else f"{dimension.code}: —"
            for dimension in evaluation.dimensions
        )
        lines.extend([
            "",
            (
                f"{index}. {item.snapshot.title} — "
                f"{item.snapshot.company}"
            ),
            (
                f"Score: {evaluation.overall_score:.1f}/5 · "
                f"{_apply_type_label(item.snapshot.apply_type)}"
            ),
            dimensions,
            f"Recommendation: {evaluation.recommendation}",
            f"Strengths: {'; '.join(evaluation.strengths) or '—'}",
            f"Gaps: {'; '.join(evaluation.gaps) or '—'}",
            f"Risks: {'; '.join(evaluation.risks) or '—'}",
            f"Evidence: {'; '.join(evaluation.evidence) or '—'}",
        ])
    return "\n".join(lines)
