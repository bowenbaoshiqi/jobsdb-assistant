import json
from pathlib import Path

import pytest

from src.integrations.manifest import load_manifest


def test_manifest_locks_approved_forks_and_required_capabilities() -> None:
    manifest = load_manifest(Path("integrations/manifest.json"))

    candidate = manifest.integrations["candidate-profile"]
    assert candidate.url == (
        "https://github.com/bowenbaoshiqi/ai-job-search.git"
    )
    assert candidate.commit == "aa7c7073990492c9111fbdda48f6adde24a1d91b"
    assert candidate.contract_version == "candidate-profile.v3"
    assert ".claude/commands/setup.md" in candidate.required_paths

    evaluation = manifest.integrations["job-evaluation"]
    assert evaluation.url == (
        "https://github.com/bowenbaoshiqi/career-ops.git"
    )
    assert evaluation.commit == "01bf8b469ad5177a9c30230bc00509ead8e006c2"
    assert (
        evaluation.contract_version
        == "career-ops-native-profile-bundle.v3"
    )
    assert (
        ".agents/skills/career-ops/SKILL.md" in evaluation.required_paths
    )
    assert "modes/_shared.md" in evaluation.required_paths
    assert "modes/oferta.md" in evaluation.required_paths

    materials = manifest.integrations["application-material"]
    assert materials.url == candidate.url
    assert materials.commit == candidate.commit
    assert materials.contract_version == "application-material.v1"
    assert (
        ".claude/skills/job-application-assistant/05-cv-templates.md"
        in materials.required_paths
    )
    assert (
        ".claude/skills/job-application-assistant/06-cover-letter-templates.md"
        in materials.required_paths
    )


def test_manifest_rejects_unapproved_owner(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "integrations": {
                    "candidate-profile": {
                        "url": "https://example.invalid/repo.git",
                        "commit": "a" * 40,
                        "license": "MIT",
                        "contract_version": "candidate-profile.v1",
                        "required_paths": ["README.md"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unapproved integration URL"):
        load_manifest(path)


@pytest.mark.parametrize(
    "commit",
    ["main", "abc123", "A" * 40, "a" * 39, "a" * 41],
)
def test_manifest_requires_exact_lowercase_commit_sha(
    tmp_path: Path,
    commit: str,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "integrations": {
                    "candidate-profile": {
                        "url": (
                            "https://github.com/bowenbaoshiqi/"
                            "ai-job-search.git"
                        ),
                        "commit": commit,
                        "license": "MIT",
                        "contract_version": "candidate-profile.v1",
                        "required_paths": ["README.md"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_manifest(path)
