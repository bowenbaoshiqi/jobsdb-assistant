"""Private-safe readiness checks for the unified Agent protocol."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from config.settings import get_config
from src.agent.dashboard import _dashboard_healthy
from src.dashboard.cli import _port_available
from src.integrations.manager import IntegrationManager
from src.integrations.manifest import load_manifest
from src.privacy import scan_tracked_files
from src.storage.database import Database


@dataclass(frozen=True)
class AgentCheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str


def run_agent_doctor(
    port: int,
    *,
    project_root: Path | None = None,
) -> tuple[dict[str, str], ...]:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    checks: list[AgentCheck] = [
        AgentCheck(
            "python",
            "pass" if sys.version_info >= (3, 11) else "fail",
            f"{sys.version_info.major}.{sys.version_info.minor}",
        )
    ]
    try:
        database = Database(get_config().storage.database_path)
        with database._connect() as conn:
            version = conn.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        checks.append(
            AgentCheck(
                "database",
                "pass" if version == 8 else "fail",
                f"schema {version} ready",
            )
        )
    except Exception:
        checks.append(AgentCheck("database", "fail", "unavailable"))

    try:
        manifest = load_manifest(root / "integrations" / "manifest.json")
        manager = IntegrationManager(root / "integrations", manifest)
        for integration_id in sorted(manifest.integrations):
            state = manager.check(integration_id)
            status: Literal["pass", "warn", "fail"] = (
                "pass"
                if state.status == "ready"
                else "warn"
                if state.status == "missing"
                else "fail"
            )
            detail = (
                "locked revision ready"
                if state.status == "ready"
                else "will install locked revision on first profile run"
                if state.status == "missing"
                else f"locked checkout is {state.status}"
            )
            checks.append(
                AgentCheck(
                    f"integration:{integration_id}",
                    status,
                    detail,
                )
            )
    except Exception:
        checks.append(
            AgentCheck("integrations", "fail", "manifest unavailable")
        )

    try:
        findings = scan_tracked_files(root)
        checks.append(
            AgentCheck(
                "privacy",
                "pass" if not findings else "fail",
                (
                    "tracked files are public-safe"
                    if not findings
                    else f"{len(findings)} private tracked file(s)"
                ),
            )
        )
    except Exception:
        checks.append(AgentCheck("privacy", "fail", "scan unavailable"))

    url = f"http://127.0.0.1:{port}"
    if _dashboard_healthy(url):
        checks.append(AgentCheck("dashboard", "pass", "already running"))
    elif _port_available("127.0.0.1", port):
        checks.append(AgentCheck("dashboard", "pass", "port available"))
    else:
        checks.append(
            AgentCheck("dashboard", "fail", f"port {port} is occupied")
        )
    return tuple(asdict(check) for check in checks)
