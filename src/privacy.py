"""Privacy checks for files intended to be published."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class PrivacyFinding:
    """A tracked file that should not be published."""

    path: str
    reason: str


_PRIVATE_ROOTS = {"data", "workspace", "logs"}
_PRIVATE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pdf",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
}
_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [path.decode() for path in result.stdout.split(b"\0") if path]


def _private_path_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = PurePosixPath(normalized).parts
    if not parts:
        return None

    if parts[0] in _PRIVATE_ROOTS:
        return "private runtime path"
    if parts[:2] == ("playwright", ".auth"):
        return "private runtime path"
    if parts[0] == "accounts" and normalized not in {
        "accounts/.gitkeep",
        "accounts/example.json",
    }:
        return "private account path"
    if parts[0] == ".env" and normalized != ".env.example":
        return "private environment file"
    if normalized in {
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".codex/config.toml",
    }:
        return "local agent settings"
    if PurePosixPath(normalized).suffix.lower() in _PRIVATE_SUFFIXES:
        return "sensitive generated file"
    return None


def _contains_secret(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return any(pattern.search(content) for pattern in _SECRET_PATTERNS)


def scan_tracked_files(
    root: Path,
    *,
    tracked: Iterable[str] | None = None,
) -> list[PrivacyFinding]:
    """Return privacy findings for tracked or explicitly supplied paths."""

    root = root.resolve()
    paths = list(tracked) if tracked is not None else _tracked_files(root)
    findings: list[PrivacyFinding] = []

    for path in paths:
        normalized = path.replace("\\", "/")
        reason = _private_path_reason(normalized)
        if reason is None and _contains_secret(root / normalized):
            reason = "secret-like content"
        if reason is not None:
            findings.append(PrivacyFinding(normalized, reason))

    return findings
