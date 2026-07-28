"""Safe validation and atomic installation of generated material files."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class InstalledPackageFiles:
    root: Path
    resume_path: Path
    cover_letter_path: Path
    manifest_path: Path
    resume_sha256: str
    cover_letter_sha256: str


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_staged_artifact(
    path: Path,
    staging_root: Path,
    *,
    kind: Literal["pdf", "text"],
) -> Path:
    staging = staging_root.resolve()
    if path.is_symlink():
        raise ValueError("artifact must not be a symlink")
    resolved = path.resolve()
    if not resolved.is_relative_to(staging):
        raise ValueError("artifact must remain inside staging")
    if not resolved.is_file():
        raise ValueError("artifact must be a regular file")
    payload = resolved.read_bytes()
    if not payload:
        label = "PDF" if kind == "pdf" else "text"
        raise ValueError(f"{label} artifact is empty")
    if kind == "pdf":
        if (
            len(payload) < 20
            or not payload.startswith(b"%PDF-")
            or not payload.rstrip().endswith(b"%%EOF")
        ):
            raise ValueError("artifact is not a complete PDF")
    else:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("text artifact must be UTF-8") from exc
        if not text.strip():
            raise ValueError("text artifact is empty")
    return resolved


def count_cover_letter_words(text: str) -> int:
    count = len(text.split())
    if count < 100:
        raise ValueError("cover letter must contain at least 100 words")
    if count > 300:
        raise ValueError("cover letter must contain at most 300 words")
    return count


def safe_material_path(
    materials_root: Path,
    job_id: str,
    version: int,
) -> Path:
    if not _SAFE_JOB_ID.fullmatch(job_id):
        raise ValueError("unsafe job id")
    if version < 1:
        raise ValueError("material version must be positive")
    root = materials_root.resolve()
    target = root / job_id / f"v{version}"
    if not target.is_relative_to(root):
        raise ValueError("material path escapes private root")
    return target


def install_package_files(
    *,
    staging_root: Path,
    resume_path: Path,
    cover_letter_path: Path,
    materials_root: Path,
    job_id: str,
    version: int,
    manifest: dict,
) -> InstalledPackageFiles:
    resume = validate_staged_artifact(
        resume_path,
        staging_root,
        kind="pdf",
    )
    cover = validate_staged_artifact(
        cover_letter_path,
        staging_root,
        kind="text",
    )
    target = safe_material_path(materials_root, job_id, version)
    if target.exists():
        raise ValueError("material version already exists")
    temporary = target.with_name(f".{target.name}-{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        installed_resume = temporary / "cv.pdf"
        installed_cover = temporary / "cover-letter.txt"
        installed_manifest = temporary / "manifest.json"
        shutil.copyfile(resume, installed_resume)
        shutil.copyfile(cover, installed_cover)
        resume_hash = hash_file(installed_resume)
        cover_hash = hash_file(installed_cover)
        payload = {
            **manifest,
            "job_id": job_id,
            "version": version,
            "resume_sha256": resume_hash,
            "cover_letter_sha256": cover_hash,
        }
        installed_manifest.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return InstalledPackageFiles(
        root=target,
        resume_path=target / "cv.pdf",
        cover_letter_path=target / "cover-letter.txt",
        manifest_path=target / "manifest.json",
        resume_sha256=resume_hash,
        cover_letter_sha256=cover_hash,
    )
