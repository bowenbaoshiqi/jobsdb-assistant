"""Local Dashboard assembly, diagnostics, and server lifecycle."""

import socket
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import uvicorn

from config.settings import get_config
from src.accounts.registry import AccountRegistry
from src.application.runtime import build_material_generation_service
from src.dashboard.app import DashboardDependencies, create_dashboard_app
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.dashboard.material_service import DashboardMaterialService
from src.dashboard.query_service import DashboardQueryService
from src.orchestrator import Orchestrator
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class CheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DashboardCheck:
    name: str
    state: CheckState
    detail: str


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def run_dashboard_doctor(
    *,
    database_path: str,
    host: str = LOOPBACK_HOST,
    port: int = DEFAULT_PORT,
    port_probe=None,
) -> list[DashboardCheck]:
    """Return private-safe readiness checks."""
    probe = port_probe or _port_available
    results = [
        DashboardCheck(
            "dependencies",
            CheckState.PASS,
            "FastAPI, Uvicorn, and Jinja2 available",
        )
    ]
    try:
        database = Database(database_path)
        with database._connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {
                "jobs",
                "job_evaluations",
                "candidate_profiles",
                "job_selections",
                "dashboard_application_tasks",
                "material_tasks",
                "material_packages",
                "material_review_events",
            }
            missing = sorted(required - tables)
            if missing:
                results.append(
                    DashboardCheck(
                        "database",
                        CheckState.FAIL,
                        f"missing schema: {', '.join(missing)}",
                    )
                )
            else:
                results.append(
                    DashboardCheck(
                        "database",
                        CheckState.PASS,
                        "schema ready",
                    )
                )
            jobs = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE is_active = 1"
            ).fetchone()[0]
            evaluations = conn.execute(
                "SELECT COUNT(*) FROM job_evaluations"
            ).fetchone()[0]
            profiles = conn.execute(
                "SELECT COUNT(*) FROM candidate_profiles "
                "WHERE is_active = 1"
            ).fetchone()[0]
        results.extend([
            DashboardCheck("jobs", CheckState.PASS, f"{jobs} current"),
            DashboardCheck(
                "evaluations",
                CheckState.PASS,
                f"{evaluations} persisted",
            ),
            DashboardCheck(
                "profile",
                CheckState.PASS,
                f"{profiles} active",
            ),
        ])
    except Exception:
        results.append(
            DashboardCheck(
                "database",
                CheckState.FAIL,
                "unavailable",
            )
        )

    if probe(host, port):
        results.append(
            DashboardCheck("port", CheckState.PASS, f"{port} available")
        )
    else:
        results.append(
            DashboardCheck("port", CheckState.FAIL, f"{port} in use")
        )
    return results


def build_production_app():
    """Wire Dashboard services to the existing local runtime."""
    config = get_config()
    database = Database(config.storage.database_path)

    async def run_one(job_id: str) -> dict:
        account = AccountRegistry().resolve_active(
            allow_placeholder=(config.login.mode == "manual"),
        )
        database.set_account(account.alias)
        return await Orchestrator(
            config,
            account=account,
            max_jobs=1,
        ).run(job_ids=[job_id])

    application_service = DashboardApplicationService(
        database,
        runner=run_one,
    )
    material_generation = build_material_generation_service()
    return create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(database),
            selection_repository=SelectionRepository(database),
            application_service=application_service,
            evaluation_progress=EvaluationProgressStore(
                Path("workspace/dashboard/evaluation-progress.json")
            ),
            material_service=DashboardMaterialService(
                database=database,
                repository=material_generation.repository,
                generation=material_generation,
                materials_root=Path("workspace/materials"),
            ),
        )
    )


def _open_after_ready(url: str) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(  # noqa: S310 (fixed loopback URL)
                f"{url}/health",
                timeout=0.5,
            ):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.1)


def start_dashboard(
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> None:
    """Start a predictable local-only Uvicorn service."""
    if not _port_available(LOOPBACK_HOST, port):
        raise RuntimeError(f"Dashboard port {port} is already in use")
    dashboard_app = build_production_app()
    if open_browser:
        threading.Thread(
            target=_open_after_ready,
            args=(f"http://{LOOPBACK_HOST}:{port}",),
            daemon=True,
        ).start()
    uvicorn.run(
        dashboard_app,
        host=LOOPBACK_HOST,
        port=port,
        log_level="info",
    )
