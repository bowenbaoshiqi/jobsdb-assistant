"""FastAPI construction for the local review Dashboard."""

from dataclasses import dataclass

from fastapi import FastAPI

from src.dashboard.application_service import DashboardApplicationService
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
    register_routes(app, dependencies)
    return app
