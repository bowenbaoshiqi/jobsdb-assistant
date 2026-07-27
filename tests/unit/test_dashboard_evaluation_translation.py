from datetime import UTC, datetime

from src.dashboard.evaluation_translation import (
    EvaluationTranslationCatalog,
    translate_evaluation,
)
from src.domain.evaluation import JobEvaluation, NativeDimension


def _evaluation() -> JobEvaluation:
    return JobEvaluation(
        id="evaluation-1",
        job_snapshot_id="1",
        profile_version=2,
        engine_version="career-ops@test",
        prompt_version="career-ops-native-profile-bundle.v2",
        overall_score=4.2,
        dimensions=[
            NativeDimension(
                code=code,
                title=f"Native block {code}",
                score=4.0,
                findings=["Strong technical fit"],
                evidence=["JD: enterprise AI platform"],
            )
            for code in "ABCDEF"
        ],
        recommendation="strong_apply",
        strengths=["Enterprise AI leadership"],
        gaps=["Team size not stated"],
        risks=["Salary not disclosed"],
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
    )


def test_translates_dashboard_copy_without_mutating_native_evaluation() -> None:
    original = _evaluation()
    catalog = EvaluationTranslationCatalog(
        {
            "Strong technical fit": "技术匹配度高",
            "JD: enterprise AI platform": "职位描述：企业级 AI 平台",
            "Enterprise AI leadership": "企业级 AI 领导经验",
            "Team size not stated": "职位未说明团队规模",
            "Salary not disclosed": "薪酬范围未披露",
        }
    )

    translated = translate_evaluation(original, catalog)

    assert translated.overall_score == original.overall_score
    assert [item.code for item in translated.dimensions] == list("ABCDEF")
    assert translated.dimensions[0].title == "职位与求职目标匹配度"
    assert translated.dimensions[0].findings == ["技术匹配度高"]
    assert translated.dimensions[0].evidence == ["职位描述：企业级 AI 平台"]
    assert translated.recommendation == "强烈建议申请"
    assert translated.strengths == ["企业级 AI 领导经验"]
    assert translated.gaps == ["职位未说明团队规模"]
    assert translated.risks == ["薪酬范围未披露"]
    assert original.strengths == ["Enterprise AI leadership"]


def test_unknown_english_text_is_visibly_preserved_as_original() -> None:
    translated = translate_evaluation(
        _evaluation(),
        EvaluationTranslationCatalog({}),
    )

    assert translated.strengths == ["原文：Enterprise AI leadership"]


def test_existing_chinese_text_is_not_prefixed() -> None:
    original = _evaluation().model_copy(
        update={"strengths": ["具备企业级 AI 领导经验"]}
    )

    translated = translate_evaluation(
        original,
        EvaluationTranslationCatalog({}),
    )

    assert translated.strengths == ["具备企业级 AI 领导经验"]
