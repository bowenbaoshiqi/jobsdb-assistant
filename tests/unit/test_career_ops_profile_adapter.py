from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from src.adapters.career_ops_profile import CareerOpsProfileAdapter
from src.domain.candidate import CandidateProfile, FactEvidence
from src.domain.candidate_cv import (
    CandidateCv,
    IntentSynthesis,
    IntentTargetField,
    SourcedText,
    interview_answer_hash,
)
from src.domain.candidate_interview import (
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewAnswer,
    InterviewAnswerStatus,
    InterviewDimension,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def sourced(value: str, locator: str) -> SourcedText:
    return SourcedText(
        value=value,
        evidence=(
            FactEvidence(source="synthetic-cv.pdf", locator=locator),
        ),
    )


def complete_profile(
    *,
    content_hash: str = "b" * 64,
) -> CandidateProfile:
    answers = {
        dimension: InterviewAnswer(
            status=(
                InterviewAnswerStatus.NOT_PROVIDED
                if dimension is InterviewDimension.SALARY_EXPECTATIONS
                else InterviewAnswerStatus.NO_PREFERENCE
                if dimension is InterviewDimension.REFERENCES
                else InterviewAnswerStatus.ANSWERED
            ),
            value=(
                None
                if dimension
                in {
                    InterviewDimension.SALARY_EXPECTATIONS,
                    InterviewDimension.REFERENCES,
                }
                else f"Exact answer for {dimension.value}"
            ),
        )
        for dimension in REQUIRED_INTERVIEW_DIMENSIONS
    }
    syntheses = tuple(
        IntentSynthesis(
            dimension=dimension,
            answer_hash=interview_answer_hash(answer),
            summary=(
                None
                if answer.status is not InterviewAnswerStatus.ANSWERED
                else f"Synthesis for {dimension.value}."
            ),
            target_field=IntentTargetField(dimension.value),
            target_roles=(
                ("AI Architect",)
                if dimension is InterviewDimension.CAREER_GOALS
                else ()
            ),
            role_archetypes=(
                ("Enterprise AI Architect",)
                if dimension is InterviewDimension.CAREER_GOALS
                else ()
            ),
            culture_requirements=(
                ("Mature large organization",)
                if dimension is InterviewDimension.MUST_HAVES
                else ()
            ),
        )
        for dimension, answer in answers.items()
    )
    return CandidateProfile(
        id="profile-2",
        version=2,
        canonical_cv=CandidateCv(
            full_name=sourced("Synthetic Candidate", "name"),
            email=sourced("candidate@example.test", "contact"),
            location=sourced("Hong Kong", "contact"),
            headline=sourced("Enterprise AI Architect", "summary"),
            summary=sourced("Designs reliable enterprise AI systems.", "summary"),
            experience=(
                {
                    "role": sourced("AI Architect", "experience 1 role"),
                    "company": sourced("Example Group", "experience 1 company"),
                    "period": sourced("2022-present", "experience 1 period"),
                    "bullets": (
                        sourced(
                            "Led an AI platform used by 12 teams.",
                            "experience 1 bullet 1",
                        ),
                    ),
                },
            ),
            skills={
                "technical": (
                    sourced("Python", "skills"),
                    sourced("LLM architecture", "skills"),
                )
            },
            proof_points=(
                sourced("Reduced delivery lead time by 40%.", "achievement"),
            ),
        ),
        target_roles=["AI Architect"],
        writing_style={"language": "en"},
        interview_answers=answers,
        intent_syntheses=syntheses,
        created_at=NOW,
        confirmed_at=NOW,
        content_hash=content_hash,
    )


def projector(tmp_path: Path) -> CareerOpsProfileAdapter:
    return CareerOpsProfileAdapter(
        workspace_root=tmp_path / "workspace" / "career-ops-profiles",
        candidate_integration_commit="a" * 40,
        career_ops_integration_commit="c" * 40,
        forbidden_roots=(
            tmp_path / "integrations" / "candidate-profile",
            tmp_path / "integrations" / "job-evaluation",
        ),
    )


def test_projector_writes_native_bundle(tmp_path: Path) -> None:
    bundle = projector(tmp_path).project(complete_profile())

    assert bundle.cv_path.read_text().startswith("# Synthetic Candidate")
    profile_yml = yaml.safe_load(bundle.profile_yml_path.read_text())
    assert profile_yml["target_roles"]["primary"] == ["AI Architect"]
    assert profile_yml["culture_screen"]["require"] == [
        "Mature large organization"
    ]
    assert profile_yml["language"]["output"] == "en"
    profile_md = bundle.profile_md_path.read_text()
    assert "## Must-haves" in profile_md
    assert "Synthesis for must_haves." in profile_md
    assert bundle.root.name == complete_profile().content_hash


def test_projector_rejects_unconfirmed_or_legacy_profile(
    tmp_path: Path,
) -> None:
    profile = complete_profile().model_copy(
        update={"confirmed_at": None, "canonical_cv": None}
    )

    with pytest.raises(
        ValueError,
        match="confirmed canonical candidate profile",
    ):
        projector(tmp_path).project(profile)


def test_projector_rejects_workspace_inside_integration(
    tmp_path: Path,
) -> None:
    integration = tmp_path / "integrations" / "job-evaluation"
    unsafe = CareerOpsProfileAdapter(
        workspace_root=integration / "workspace",
        candidate_integration_commit="a" * 40,
        career_ops_integration_commit="c" * 40,
        forbidden_roots=(integration,),
    )

    with pytest.raises(ValueError, match="private workspace"):
        unsafe.project(complete_profile())


def test_projector_rejects_unresolved_placeholder(
    tmp_path: Path,
) -> None:
    profile = complete_profile()
    cv = profile.canonical_cv.model_copy(
        update={"headline": sourced("[YOUR HEADLINE]", "summary")}
    )

    with pytest.raises(ValueError, match="unresolved placeholder"):
        projector(tmp_path).project(
            profile.model_copy(update={"canonical_cv": cv})
        )


def test_explicit_skips_are_recorded_but_not_invented(
    tmp_path: Path,
) -> None:
    bundle = projector(tmp_path).project(complete_profile())
    profile_yml = yaml.safe_load(bundle.profile_yml_path.read_text())

    assert "compensation" not in profile_yml
    assert "References: no preference" in bundle.profile_md_path.read_text()
    omitted = {
        item["field"]: item["reason"]
        for item in bundle.manifest["omitted_fields"]
    }
    assert omitted["compensation"] == "not_provided"
    assert omitted["references"] == "no_preference"
