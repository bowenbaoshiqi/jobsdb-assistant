"""FastAPI construction for the local review Dashboard."""

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.application.execute_application import ApplicationExecutionService
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.dashboard.material_routes import material_router
from src.dashboard.material_service import DashboardMaterialService
from src.dashboard.query_service import DashboardQueryService
from src.dashboard.routes import register_routes
from src.storage.agent_pool_repository import AgentPoolRepository
from src.storage.database import Database
from src.storage.job_batch_repository import JobBatchRepository
from src.storage.selection_repository import SelectionRepository
from src.version import __version__


class DashboardWorker(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class DashboardDependencies:
    database: Database
    query_service: DashboardQueryService
    selection_repository: SelectionRepository
    application_service: DashboardApplicationService
    evaluation_progress: EvaluationProgressStore | None = None
    material_service: DashboardMaterialService | None = None
    approved_application_service: ApplicationExecutionService | None = None
    approved_application_worker: DashboardWorker | None = None
    job_batch_repository: JobBatchRepository | None = None
    job_batch_worker: DashboardWorker | None = None
    account_alias: str = "default"


def create_dashboard_app(
    dependencies: DashboardDependencies,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watchdog_task = asyncio.create_task(_pool_watchdog(dependencies))
        if dependencies.approved_application_worker is not None:
            await dependencies.approved_application_worker.start()
        if dependencies.job_batch_worker is not None:
            await dependencies.job_batch_worker.start()
        try:
            yield
        finally:
            watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog_task
            if dependencies.job_batch_worker is not None:
                await dependencies.job_batch_worker.close()
            if dependencies.approved_application_worker is not None:
                await dependencies.approved_application_worker.close()

    app = FastAPI(
        title="JobsDB Assistant",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.dashboard_dependencies = dependencies
    app.state.dashboard_tasks = set()
    app.state.approved_application_worker = (
        dependencies.approved_application_worker
    )
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).with_name("static")),
        name="static",
    )
    register_routes(app, dependencies)
    if dependencies.material_service is not None:
        app.include_router(material_router(dependencies.material_service))
    return app


async def _pool_watchdog(dependencies: DashboardDependencies) -> None:
    """Recover stale pool claims independently of Dashboard reads."""
    pools = AgentPoolRepository(dependencies.database)
    while True:
        now = datetime.now(UTC)
        progress = dependencies.evaluation_progress
        for pool_id in pools.active_pool_ids():
            recovered = pools.release_stale(pool_id, now=now)
            if progress is None:
                continue
            for item in recovered:
                with suppress(KeyError):
                    progress.requeue_if_running(item.internal_task_id)
        await asyncio.sleep(30)
