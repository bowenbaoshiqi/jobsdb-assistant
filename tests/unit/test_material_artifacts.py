import hashlib
from pathlib import Path

import pytest

from src.materials.artifacts import (
    count_cover_letter_words,
    hash_file,
    install_package_files,
    safe_material_path,
    validate_staged_artifact,
)


def _pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    return path


def test_validates_pdf_and_exact_hash(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    pdf = _pdf(staging / "cv.pdf")

    assert validate_staged_artifact(pdf, staging, kind="pdf") == pdf.resolve()
    assert hash_file(pdf) == hashlib.sha256(pdf.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "payload",
    [b"", b"%PDF-", b"plain text", b"%PDF-1.7\ntruncated"],
)
def test_rejects_empty_truncated_or_non_pdf(
    tmp_path: Path,
    payload: bytes,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    path = staging / "cv.pdf"
    path.write_bytes(payload)

    with pytest.raises(ValueError, match="PDF"):
        validate_staged_artifact(path, staging, kind="pdf")


def test_rejects_symlink_traversal_and_file_outside_staging(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    outside = _pdf(tmp_path / "outside.pdf")
    link = staging / "linked.pdf"
    link.symlink_to(outside)

    for path in (link, outside, staging / ".." / "outside.pdf"):
        with pytest.raises(ValueError):
            validate_staged_artifact(path, staging, kind="pdf")


def test_cover_letter_word_boundaries() -> None:
    assert count_cover_letter_words(" ".join(["word"] * 100)) == 100
    assert count_cover_letter_words(" ".join(["word"] * 300)) == 300
    with pytest.raises(ValueError, match="100"):
        count_cover_letter_words(" ".join(["word"] * 99))
    with pytest.raises(ValueError, match="300"):
        count_cover_letter_words(" ".join(["word"] * 301))


def test_safe_material_path_rejects_unsafe_identity(tmp_path: Path) -> None:
    assert safe_material_path(tmp_path, "job-123", 2) == (
        tmp_path.resolve() / "job-123" / "v2"
    )
    for job_id in ("../escape", "/absolute", "job/child", ""):
        with pytest.raises(ValueError, match="job"):
            safe_material_path(tmp_path, job_id, 1)
    with pytest.raises(ValueError, match="version"):
        safe_material_path(tmp_path, "job-1", 0)


def test_atomic_install_writes_manifest_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    resume = _pdf(staging / "generated.pdf")
    cover = staging / "generated.txt"
    cover.write_text(" ".join(["word"] * 120), encoding="utf-8")
    root = tmp_path / "materials"

    installed = install_package_files(
        staging_root=staging,
        resume_path=resume,
        cover_letter_path=cover,
        materials_root=root,
        job_id="job-1",
        version=1,
        manifest={"task_id": "task-1"},
    )

    assert installed.resume_path.read_bytes() == resume.read_bytes()
    assert installed.cover_letter_path.read_text(encoding="utf-8") == (
        cover.read_text(encoding="utf-8")
    )
    assert installed.manifest_path.is_file()
    assert not list((root / "job-1").glob(".*.tmp"))
    with pytest.raises(ValueError, match="already exists"):
        install_package_files(
            staging_root=staging,
            resume_path=resume,
            cover_letter_path=cover,
            materials_root=root,
            job_id="job-1",
            version=1,
            manifest={},
        )
