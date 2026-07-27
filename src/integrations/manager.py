"""Install and validate exact integration revisions."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from src.integrations.manifest import IntegrationManifest

IntegrationStatus = Literal["ready", "missing", "mismatch", "damaged"]


class CommandRunner(Protocol):
    """Minimal command boundary used by the integration manager."""

    def run(self, command: tuple[str, ...]) -> str: ...


class SubprocessCommandRunner:
    """Run fixed Git argument vectors without a shell."""

    def run(self, command: tuple[str, ...]) -> str:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


@dataclass(frozen=True)
class IntegrationState:
    """Observed local state for one locked integration."""

    id: str
    path: Path
    commit: str
    status: IntegrationStatus


class IntegrationManager:
    """Manage only integrations declared in the approved manifest."""

    def __init__(
        self,
        root: Path,
        manifest: IntegrationManifest,
        runner: CommandRunner | None = None,
    ) -> None:
        self.root = root
        self.manifest = manifest
        self.runner = runner or SubprocessCommandRunner()

    def check(self, integration_id: str) -> IntegrationState:
        spec = self.manifest.integrations[integration_id]
        path = self.root / integration_id
        if not path.is_dir():
            return IntegrationState(
                id=integration_id,
                path=path,
                commit=spec.commit,
                status="missing",
            )

        head = self.runner.run(
            ("git", "-C", str(path), "rev-parse", "HEAD")
        ).strip()
        if head != spec.commit:
            return IntegrationState(
                id=integration_id,
                path=path,
                commit=head,
                status="mismatch",
            )
        if any(not (path / required).exists()
               for required in spec.required_paths):
            return IntegrationState(
                id=integration_id,
                path=path,
                commit=head,
                status="damaged",
            )
        return IntegrationState(
            id=integration_id,
            path=path,
            commit=head,
            status="ready",
        )

    def install_missing(self, integration_id: str) -> IntegrationState:
        state = self.check(integration_id)
        if state.status != "missing":
            return state

        spec = self.manifest.integrations[integration_id]
        self.root.mkdir(parents=True, exist_ok=True)
        self.runner.run(
            ("git", "clone", "--no-checkout", spec.url, str(state.path))
        )
        self.runner.run(
            (
                "git",
                "-C",
                str(state.path),
                "checkout",
                "--detach",
                spec.commit,
            )
        )
        return self.check(integration_id)

    def repair(self, integration_id: str) -> IntegrationState:
        """Back up one damaged checkout and reinstall its locked revision."""
        state = self.check(integration_id)
        if state.status == "ready":
            return state
        if state.status != "missing":
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            backup = state.path.with_name(
                f"{state.path.name}.backup-{timestamp}"
            )
            if backup.exists():
                raise FileExistsError(backup)
            state.path.replace(backup)
        return self.install_missing(integration_id)
