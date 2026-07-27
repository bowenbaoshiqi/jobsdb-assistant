"""Deterministic projection of a confirmed profile to career-ops inputs."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from src.domain.candidate import CandidateProfile
from src.domain.candidate_cv import (
    CandidateCv,
    IntentSynthesis,
    validate_intent_syntheses,
)
from src.domain.candidate_interview import (
    InterviewAnswerStatus,
    InterviewDimension,
)

_PROJECTION_VERSION = "career-ops-profile-bundle.v1"
_PLACEHOLDER = re.compile(
    r"(\{\{[^}]+\}\}|\[(?:YOUR|INSERT|TODO)[^\]]*\]|<YOUR[_ ][^>]+>)",
    re.IGNORECASE,
)


class CareerOpsProfileBundle(BaseModel):
    """Verified immutable native career-ops input paths."""

    model_config = ConfigDict(frozen=True)

    root: Path
    profile_id: str
    profile_version: int
    profile_hash: str
    projection_version: str
    bundle_hash: str
    cv_path: Path
    profile_yml_path: Path
    profile_md_path: Path
    manifest_path: Path
    manifest: dict[str, Any]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class CareerOpsProfileAdapter:
    """Render and atomically persist a private career-ops profile bundle."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        candidate_integration_commit: str,
        career_ops_integration_commit: str,
        forbidden_roots: tuple[Path, ...] = (),
        projection_version: str = _PROJECTION_VERSION,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.candidate_integration_commit = candidate_integration_commit
        self.career_ops_integration_commit = career_ops_integration_commit
        self.forbidden_roots = tuple(
            root.resolve() for root in forbidden_roots
        )
        self.projection_version = projection_version

    def project(self, profile: CandidateProfile) -> CareerOpsProfileBundle:
        self._validate_profile(profile)
        self._validate_workspace()
        assert profile.canonical_cv is not None
        assert profile.content_hash is not None

        target = (self.workspace_root / profile.content_hash).resolve()
        if not target.is_relative_to(self.workspace_root):
            raise ValueError("bundle target escapes private workspace")

        rendered, sources, omitted = self._render(profile)
        for name, payload in rendered.items():
            if _PLACEHOLDER.search(payload):
                raise ValueError(
                    f"unresolved placeholder in projected file: {name}"
                )

        file_hashes = {
            name: _sha256(payload.encode("utf-8"))
            for name, payload in rendered.items()
        }
        bundle_hash = _sha256(
            json.dumps(
                file_hashes,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        manifest = self._manifest(
            profile,
            file_hashes,
            bundle_hash,
            sources,
            omitted,
        )

        if target.exists():
            return self._reuse_verified(
                target,
                profile,
                manifest,
                rendered,
            )

        self.workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{profile.content_hash}.",
                dir=self.workspace_root,
            )
        )
        try:
            for relative, payload in rendered.items():
                path = temporary / relative
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
                path.chmod(0o600)
            manifest_path = temporary / "projection-manifest.json"
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest_path.chmod(0o600)
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return self._bundle(target, manifest)

    def _validate_profile(self, profile: CandidateProfile) -> None:
        if (
            profile.confirmed_at is None
            or profile.canonical_cv is None
            or profile.content_hash is None
            or not profile.interview_answers
            or len(profile.intent_syntheses)
            != len(profile.interview_answers)
        ):
            raise ValueError(
                "projection requires a confirmed canonical candidate profile"
            )
        dimensions = {
            synthesis.dimension for synthesis in profile.intent_syntheses
        }
        if dimensions != set(profile.interview_answers):
            raise ValueError(
                "projection requires a confirmed canonical candidate profile"
            )
        validate_intent_syntheses(
            profile.interview_answers,
            profile.intent_syntheses,
        )

    def _validate_workspace(self) -> None:
        for forbidden in self.forbidden_roots:
            if (
                self.workspace_root == forbidden
                or self.workspace_root.is_relative_to(forbidden)
            ):
                raise ValueError(
                    "private workspace must be outside integration checkouts"
                )

    def _render(
        self,
        profile: CandidateProfile,
    ) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
        cv = profile.canonical_cv
        assert cv is not None
        syntheses = {
            item.dimension: item for item in profile.intent_syntheses
        }
        profile_data, sources, omitted = self._profile_yml(
            profile,
            cv,
            syntheses,
        )
        rendered = {
            "cv.md": self._cv_markdown(cv),
            "config/profile.yml": yaml.safe_dump(
                profile_data,
                sort_keys=False,
                allow_unicode=True,
            ),
            "modes/_profile.md": self._profile_markdown(
                profile,
                cv,
                syntheses,
            ),
        }
        return rendered, sources, omitted

    def _profile_yml(
        self,
        profile: CandidateProfile,
        cv: CandidateCv,
        syntheses: dict[InterviewDimension, IntentSynthesis],
    ) -> tuple[dict[str, Any], dict[str, str], list[dict[str, str]]]:
        candidate_fields = {
            "full_name": cv.full_name,
            "email": cv.email,
            "phone": cv.phone,
            "location": cv.location,
            "linkedin": cv.linkedin,
            "github": cv.github,
        }
        candidate = {
            key: sourced.value
            for key, sourced in candidate_fields.items()
            if sourced is not None
        }
        archetypes = _unique(
            [
                value
                for synthesis in syntheses.values()
                for value in synthesis.role_archetypes
            ]
        )
        data: dict[str, Any] = {
            "candidate": candidate,
            "target_roles": {
                "primary": profile.target_roles,
                "archetypes": [
                    {"name": name, "fit": "primary"}
                    for name in archetypes
                ],
            },
            "narrative": {
                **(
                    {"headline": cv.headline.value}
                    if cv.headline is not None
                    else {}
                ),
                "superpowers": [
                    item.value
                    for items in cv.skills.values()
                    for item in items
                ],
                "proof_points": [
                    {"name": f"Proof point {index}", "hero_metric": item.value}
                    for index, item in enumerate(cv.proof_points, start=1)
                ],
            },
            "language": {
                "output": profile.writing_style.get("language", "en")
            },
        }
        culture = _unique(
            [
                value
                for synthesis in syntheses.values()
                for value in synthesis.culture_requirements
            ]
        )
        if culture:
            data["culture_screen"] = {"require": culture}
        if cv.location is not None:
            data["location"] = {"city": cv.location.value}

        omitted: list[dict[str, str]] = []
        compensation_answer = profile.interview_answers.get(
            InterviewDimension.SALARY_EXPECTATIONS
        )
        compensation = syntheses.get(
            InterviewDimension.SALARY_EXPECTATIONS
        )
        if (
            compensation_answer is not None
            and compensation_answer.status
            is InterviewAnswerStatus.ANSWERED
            and compensation is not None
        ):
            values = {
                "target_range": compensation.compensation_target,
                "minimum": compensation.compensation_minimum,
                "currency": compensation.compensation_currency,
            }
            data["compensation"] = {
                key: value for key, value in values.items() if value
            }
        else:
            omitted.append(
                {
                    "field": "compensation",
                    "reason": (
                        compensation_answer.status.value
                        if compensation_answer is not None
                        else "missing"
                    ),
                }
            )
        references = profile.interview_answers.get(
            InterviewDimension.REFERENCES
        )
        if (
            references is None
            or references.status is not InterviewAnswerStatus.ANSWERED
        ):
            omitted.append(
                {
                    "field": "references",
                    "reason": (
                        references.status.value
                        if references is not None
                        else "missing"
                    ),
                }
            )
        sources = {
            "candidate": "candidate.canonical_cv",
            "target_roles.primary": "candidate.target_roles",
            "target_roles.archetypes": "candidate.intent_syntheses",
            "narrative": "candidate.canonical_cv",
            "culture_screen.require": "candidate.intent_syntheses",
            "location.city": "candidate.canonical_cv.location",
            "language.output": "candidate.writing_style.language",
        }
        return data, sources, omitted

    @staticmethod
    def _cv_markdown(cv: CandidateCv) -> str:
        name = cv.full_name.value if cv.full_name else "Candidate"
        lines = [f"# {name}", ""]
        if cv.headline:
            lines.extend([cv.headline.value, ""])
        if cv.summary:
            lines.extend(["## Summary", "", cv.summary.value, ""])
        if cv.experience:
            lines.extend(["## Experience", ""])
            for item in cv.experience:
                lines.extend(
                    [
                        f"### {item.role.value} — {item.company.value}",
                        "",
                        item.period.value,
                        "",
                    ]
                )
                lines.extend(f"- {bullet.value}" for bullet in item.bullets)
                lines.append("")
        if cv.education:
            lines.extend(["## Education", ""])
            for item in cv.education:
                lines.append(
                    f"- {item.degree.value}, {item.institution.value}"
                )
            lines.append("")
        if cv.skills:
            lines.extend(["## Skills", ""])
            for category, items in cv.skills.items():
                lines.append(
                    f"- **{category.title()}:** "
                    + ", ".join(item.value for item in items)
                )
            lines.append("")
        sections = (
            ("Projects", cv.projects),
            ("Certifications", cv.certifications),
            ("Publications", cv.publications),
            ("Awards", cv.awards),
            ("Languages", cv.languages),
        )
        for heading, items in sections:
            if items:
                lines.extend(
                    [f"## {heading}", ""]
                    + [f"- {item.value}" for item in items]
                    + [""]
                )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _profile_markdown(
        profile: CandidateProfile,
        cv: CandidateCv,
        syntheses: dict[InterviewDimension, IntentSynthesis],
    ) -> str:
        def summary(dimension: InterviewDimension) -> str:
            synthesis = syntheses[dimension]
            answer = profile.interview_answers[dimension]
            if answer.status is InterviewAnswerStatus.ANSWERED:
                return synthesis.summary or ""
            return answer.status.value.replace("_", " ")

        archetypes = _unique(
            [
                value
                for synthesis in syntheses.values()
                for value in synthesis.role_archetypes
            ]
        )
        lines = [
            "# Candidate Profile Context",
            "",
            "## North Star Roles",
            "",
            *[f"- {role}" for role in profile.target_roles],
            *[f"- Archetype: {item}" for item in archetypes],
            "",
            "## Career Goals",
            "",
            summary(InterviewDimension.CAREER_GOALS),
            "",
            "## Next-role Motivators",
            "",
            summary(InterviewDimension.NEXT_ROLE_MOTIVATORS),
            "",
            "## Professional Narrative",
            "",
            cv.summary.value if cv.summary else "",
            "",
            "## Behavioral and Collaboration Style",
            "",
            summary(InterviewDimension.BEHAVIORAL_STYLE),
            "",
            "## Must-haves",
            "",
            summary(InterviewDimension.MUST_HAVES),
            "",
            "## Deal-breakers",
            "",
            summary(InterviewDimension.DEAL_BREAKERS),
            "",
            "## Compensation Expectations",
            "",
            summary(InterviewDimension.SALARY_EXPECTATIONS),
            "",
            "## Proof Points",
            "",
            *[f"- {item.value}" for item in cv.proof_points],
            "",
            "## References Policy",
            "",
            "References: "
            + summary(InterviewDimension.REFERENCES),
            "",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _manifest(
        self,
        profile: CandidateProfile,
        file_hashes: dict[str, str],
        bundle_hash: str,
        sources: dict[str, str],
        omitted: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "projection_version": self.projection_version,
            "profile": {
                "id": profile.id,
                "version": profile.version,
                "content_hash": profile.content_hash,
            },
            "integrations": {
                "candidate_profile": self.candidate_integration_commit,
                "career_ops": self.career_ops_integration_commit,
            },
            "bundle_hash": bundle_hash,
            "files": {
                name: {"path": name, "sha256": digest}
                for name, digest in file_hashes.items()
            },
            "field_sources": sources,
            "intent_sources": {
                synthesis.dimension.value: {
                    "answer_hash": synthesis.answer_hash,
                    "target_field": synthesis.target_field.value,
                }
                for synthesis in profile.intent_syntheses
            },
            "omitted_fields": omitted,
        }

    def _reuse_verified(
        self,
        target: Path,
        profile: CandidateProfile,
        expected_manifest: dict[str, Any],
        rendered: dict[str, str],
    ) -> CareerOpsProfileBundle:
        manifest_path = target / "projection-manifest.json"
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ValueError("existing profile bundle is not verifiable") from error
        if existing != expected_manifest:
            raise ValueError("existing profile bundle manifest mismatch")
        for relative, payload in rendered.items():
            path = target / relative
            if not path.is_file() or _sha256(path.read_bytes()) != _sha256(
                payload.encode("utf-8")
            ):
                raise ValueError(
                    f"existing profile bundle file mismatch: {relative}"
                )
        return self._bundle(target, expected_manifest)

    def _bundle(
        self,
        root: Path,
        manifest: dict[str, Any],
    ) -> CareerOpsProfileBundle:
        profile = manifest["profile"]
        return CareerOpsProfileBundle(
            root=root,
            profile_id=profile["id"],
            profile_version=profile["version"],
            profile_hash=profile["content_hash"],
            projection_version=manifest["projection_version"],
            bundle_hash=manifest["bundle_hash"],
            cv_path=root / "cv.md",
            profile_yml_path=root / "config" / "profile.yml",
            profile_md_path=root / "modes" / "_profile.md",
            manifest_path=root / "projection-manifest.json",
            manifest=manifest,
        )
