"""HTTP routes for the local review Dashboard."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.dashboard.application_service import (
    DirectApplyRequest,
    NotQuickApplyError,
)
from src.dashboard.schemas import DashboardFilters
from src.domain.job import ApplyType
from src.storage.dashboard_application_repository import (
    ApplicationBusyError,
)

_TEMPLATES = Jinja2Templates(
    directory=Path(__file__).with_name("templates")
)


def register_routes(app: FastAPI, dependencies) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="index.html",
            context={},
        )

    @app.get("/materials/{package_id}", response_class=HTMLResponse)
    async def material_preview(request: Request, package_id: str):
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="material.html",
            context={"package_id": package_id},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            with dependencies.database._connect() as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            ) from exc
        return {
            "status": "ok",
            "database": "ready",
            "dashboard_version": "0.5.0",
        }

    @app.get("/api/jobs")
    async def list_jobs(
        show: Annotated[str, Query()] = "evaluated",
        score_min: Annotated[float | None, Query()] = None,
        apply_type: Annotated[ApplyType | None, Query()] = None,
        selected: Annotated[bool | None, Query()] = None,
        query: Annotated[str | None, Query()] = None,
    ):
        filters = DashboardFilters(
            show=show,
            score_min=score_min,
            apply_type=apply_type,
            selected=selected,
            query=query,
        )
        return dependencies.query_service.list_jobs(filters)

    @app.get("/api/evaluation-progress")
    async def evaluation_progress():
        if dependencies.evaluation_progress is None:
            return {
                "status": "idle",
                "total": 0,
                "queued": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
            }
        return dependencies.evaluation_progress.get()

    @app.put("/api/selections/{job_id}")
    async def select(job_id: str):
        try:
            return dependencies.selection_repository.select(
                job_id,
                selected_at=datetime.now(UTC),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            ) from exc

    @app.delete(
        "/api/selections/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def deselect(job_id: str) -> Response:
        dependencies.selection_repository.deselect(job_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/jobs/{job_id}/quick-apply",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def quick_apply(job_id: str, payload: DirectApplyRequest):
        try:
            task = await dependencies.application_service.start(
                job_id,
                payload,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            ) from exc
        except NotQuickApplyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Apply jobs require manual submission",
            ) from exc
        except ApplicationBusyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="another application is already running",
            ) from exc

        if task.status.value == "applying":
            background = asyncio.create_task(
                dependencies.application_service.execute(task.id)
            )
            app.state.dashboard_tasks.add(background)
            background.add_done_callback(
                app.state.dashboard_tasks.discard
            )
        return task

    @app.get("/api/applications/{task_id}")
    async def application_status(task_id: str):
        task = dependencies.application_service.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="application task not found",
            )
        return task

    @app.post(
        "/api/jobs/{job_id}/applications/prepare",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def prepare_approved_application(job_id: str):
        service = dependencies.approved_application_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="approved application worker is unavailable",
            )
        try:
            return service.queue(
                job_id,
                account_alias=dependencies.account_alias,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/approved-applications/{execution_id}/confirm",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def confirm_approved_application(execution_id: str):
        service = dependencies.approved_application_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="approved application worker is unavailable",
            )
        try:
            return service.confirm_submission(execution_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="application execution not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    @app.get("/api/approved-applications/{execution_id}")
    async def approved_application_status(execution_id: str):
        service = dependencies.approved_application_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="approved application worker is unavailable",
            )
        execution = service.get(execution_id)
        if execution is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="application execution not found",
            )
        return execution

    @app.post("/api/jobs/{job_id}/applications/manual-handoff")
    async def manual_application_handoff(job_id: str):
        service = dependencies.approved_application_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="approved application worker is unavailable",
            )
        try:
            handoff = service.manual_handoff(
                job_id,
                account_alias=dependencies.account_alias,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return {
            "execution_id": handoff.execution_id,
            "job_url": handoff.job_url,
            "resume_url": f"/api/jobs/{job_id}/approved-resume",
            "cover_letter_text": handoff.cover_letter_text,
        }

    @app.get("/api/jobs/{job_id}/approved-resume")
    async def approved_resume(job_id: str):
        service = dependencies.material_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="material service is unavailable",
            )
        try:
            path = service.approved_pdf_for_job(job_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="job not found",
            ) from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=f"tailored-resume-{job_id}.pdf",
        )
