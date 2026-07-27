"""FastAPI construction for the local review Dashboard."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.dashboard.material_routes import material_router
from src.dashboard.material_service import DashboardMaterialService
from src.dashboard.query_service import DashboardQueryService
from src.dashboard.routes import register_routes
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository


@dataclass(frozen=True)
class DashboardDependencies:
    database: Database
    query_service: DashboardQueryService
    selection_repository: SelectionRepository
    application_service: DashboardApplicationService
    evaluation_progress: EvaluationProgressStore | None = None
    material_service: DashboardMaterialService | None = None


def create_dashboard_app(
    dependencies: DashboardDependencies,
) -> FastAPI:
    app = FastAPI(
        title="JobsDB Assistant",
        version="0.4.0",
        docs_url=None,
        redoc_url=None,
    )
    app.state.dashboard_dependencies = dependencies
    app.state.dashboard_tasks = set()
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).with_name("static")),
        name="static",
    )
    register_routes(app, dependencies)
    if dependencies.material_service is not None:
        app.include_router(material_router(dependencies.material_service))
    return app
