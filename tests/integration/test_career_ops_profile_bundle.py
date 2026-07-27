import json
from pathlib import Path

from tests.unit.test_career_ops_profile_adapter import (
    complete_profile,
    projector,
)


def test_projector_is_deterministic_and_verifies_existing_bundle(
    tmp_path: Path,
) -> None:
    first = projector(tmp_path).project(complete_profile())
    first_manifest = first.manifest_path.read_bytes()
    second = projector(tmp_path).project(complete_profile())

    assert first.bundle_hash == second.bundle_hash
    assert second.manifest_path.read_bytes() == first_manifest
    assert json.loads(first_manifest)["bundle_hash"] == first.bundle_hash


def test_manifest_maps_outputs_to_canonical_sources(tmp_path: Path) -> None:
    bundle = projector(tmp_path).project(complete_profile())
    manifest = bundle.manifest

    assert manifest["profile"]["id"] == "profile-2"
    assert manifest["files"]["cv.md"]["sha256"]
    assert (
        manifest["field_sources"]["target_roles.primary"]
        == "candidate.target_roles"
    )
    assert manifest["intent_sources"]["must_haves"]["answer_hash"]
    assert all(
        path.is_relative_to(bundle.root)
        for path in (
            bundle.cv_path,
            bundle.profile_yml_path,
            bundle.profile_md_path,
            bundle.manifest_path,
        )
    )
