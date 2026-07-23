"""Redacting local environment diagnostics."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


@dataclass(frozen=True)
class DoctorPaths:
    root: Path
    database: Path
    browser_profile: Path


def _one_of(
    name: str,
    commands: tuple[str, ...],
    required: bool,
    which: Callable[[str], str | None],
) -> CheckResult:
    found = next((command for command in commands if which(command)), None)
    if found:
        return CheckResult(name, CheckStatus.PASS, found)
    status = CheckStatus.FAIL if required else CheckStatus.WARN
    return CheckResult(name, status, "missing")


def run_checks(
    which: Callable[[str], str | None] = shutil.which,
    paths: DoctorPaths | None = None,
) -> list[CheckResult]:
    root = Path.cwd() if paths is None else paths.root
    resolved = paths or DoctorPaths(
        root=root,
        database=root / "data/jobsdb.db",
        browser_profile=root / "data/browser_profile",
    )
    return [
        CheckResult(
            "python",
            (
                CheckStatus.PASS
                if sys.version_info >= (3, 11) and which("python")
                else CheckStatus.FAIL
            ),
            f"{sys.version_info.major}.{sys.version_info.minor}",
        ),
        _one_of("uv", ("uv",), True, which),
        _one_of("node-or-bun", ("node", "bun"), False, which),
        _one_of("claude-or-codex", ("claude", "codex"), False, which),
        _one_of("latex", ("lualatex", "xelatex"), False, which),
        CheckResult(
            "database",
            CheckStatus.PASS if resolved.database.exists() else CheckStatus.WARN,
            "present" if resolved.database.exists() else "not-created",
        ),
        CheckResult(
            "browser-profile",
            (
                CheckStatus.PASS
                if resolved.browser_profile.exists()
                else CheckStatus.WARN
            ),
            "present" if resolved.browser_profile.exists() else "not-created",
        ),
    ]
