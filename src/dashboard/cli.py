"""Local Dashboard assembly, diagnostics, and server lifecycle."""

import socket
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

import uvicorn

from config.settings import AppConfig, get_config
from src.accounts.registry import AccountRegistry
from src.application.approved_runtime import (
    ApprovedApplicationRuntime,
    LazyMaterialWizard,
    LazyResumeManager,
)
from src.application.approved_worker import ApprovedApplicationWorker
from src.application.execute_application import ApplicationExecutionService
from src.application.job_batch_discovery import JobBatchDiscoveryService
from src.application.job_batch_worker import JobBatchWorker
from src.application.runtime import (
    build_material_generation_service,
    build_workflow,
)
from src.dashboard.app import DashboardDependencies, create_dashboard_app
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.evaluation_progress import (
    EvaluationProgressStore,
    EvaluationTaskStatus,
)
from src.dashboard.material_service import DashboardMaterialService
from src.dashboard.query_service import DashboardQueryService
from src.orchestrator import Orchestrator
from src.storage.application_execution_repository import (
    ApplicationExecutionRepository,
)
from src.storage.database import Database
from src.storage.job_batch_repository import JobBatchRepository
from src.storage.material_repository import MaterialRepository
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


def _headed_discovery_config(config: AppConfig) -> AppConfig:
    discovery = config.model_copy(deep=True)
    discovery.browser.headless = False
    return discovery


def build_production_app():
    """Wire Dashboard services to the existing local runtime."""
    config = get_config()
    database = Database(config.storage.database_path)

    account = AccountRegistry().resolve_active(
        allow_placeholder=True,
    )
    if not account.email:
        config.login.mode = "manual"
    discovery_config = _headed_discovery_config(config)
    database.set_account(account.alias)
    job_batches = JobBatchRepository(database)
    job_batches.purge_expired(
        cutoff=datetime.now(UTC) - timedelta(days=30)
    )

    async def discover_batch(
        keyword: str,
        limit: int,
        excluded_job_ids: set[str],
    ) -> dict:
        database.set_account(account.alias)
        return await Orchestrator(
            discovery_config,
            account=account,
            max_jobs=limit,
        ).discover(
            keyword,
            limit=limit,
            excluded_job_ids=excluded_job_ids,
        )

    progress_store = EvaluationProgressStore(
        Path("workspace/dashboard/evaluation-progress.json")
    )

    async def prepare_batch_scoring(
        batch_id: str,
        job_ids: list[str],
    ) -> None:
        workflow = build_workflow()
        plan = workflow.prepare_evaluations(
            batch_id,
            job_ids=set(job_ids),
        )
        task_ids = [item.task.task_id for item in plan.pending]
        cached_ids = [
            f"cached-{item.id}"
            for item in plan.cached
        ]
        progress_store.start(
            task_ids + cached_ids,
            now=datetime.now(UTC),
        )
        for task_id in cached_ids:
            progress_store.mark(
                task_id,
                EvaluationTaskStatus.COMPLETED,
            )

    job_batch_worker = JobBatchWorker(
        service=JobBatchDiscoveryService(
            job_batches,
            runner=discover_batch,
            scoring_preparer=prepare_batch_scoring,
        )
    )

    async def run_one(job_id: str) -> dict:
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
    if config.login.mode == "manual" and hasattr(config, "browser"):
        config.browser.headless = False
    browser_runtime = ApprovedApplicationRuntime(
        orchestrator=Orchestrator(config, account=account, max_jobs=1),
        job_url=lambda job_id: _job_url(database, job_id),
    )
    approved_service = ApplicationExecutionService(
        database=database,
        materials=MaterialRepository(database),
        executions=ApplicationExecutionRepository(database),
        resume_manager=LazyResumeManager(browser_runtime),
        wizard=LazyMaterialWizard(browser_runtime),
    )
    approved_worker = ApprovedApplicationWorker(
        service=approved_service,
        runtime=browser_runtime,
    )
    material_generation = build_material_generation_service()
    return create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(
                database,
                job_batch_repository=job_batches,
            ),
            selection_repository=SelectionRepository(database),
            application_service=application_service,
            evaluation_progress=progress_store,
            material_service=DashboardMaterialService(
                database=database,
                repository=material_generation.repository,
                generation=material_generation,
                materials_root=Path("workspace/materials"),
            ),
            approved_application_service=approved_service,
            approved_application_worker=approved_worker,
            job_batch_repository=job_batches,
            job_batch_worker=job_batch_worker,
            account_alias=account.alias,
        )
    )


def _job_url(database: Database, job_id: str) -> str:
    snapshot = database.get_current_job_snapshot_record(job_id)
    if snapshot is None:
        raise KeyError(job_id)
    return snapshot.canonical_url


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
