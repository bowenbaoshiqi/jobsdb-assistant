"""HTTP routes for local material generation and human review."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.dashboard.material_schemas import (
    MaterialApprovalRequest,
    MaterialFeedbackRequest,
)
from src.dashboard.material_service import DashboardMaterialService


def material_router(service: DashboardMaterialService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/material-batches", status_code=202)
    def create_batch():
        try:
            plan = service.create_batch()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "batch_id": plan.batch_id,
            "tasks": [
                {
                    "task_id": item.task.task_id,
                    "job_id": item.task.job_id,
                    "material_version": item.task.material_version,
                    "status": "waiting_for_agent",
                }
                for item in plan.pending
            ],
        }

    @router.get("/materials/{package_id}")
    def detail(package_id: str):
        try:
            return service.detail(package_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="material not found") from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/materials/{package_id}/pdf")
    def pdf(package_id: str):
        try:
            path = service.pdf_path(package_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="material not found") from exc
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="application/pdf",
            filename="tailored-cv.pdf",
        )

    @router.post("/materials/{package_id}/approve")
    def approve(package_id: str, request: MaterialApprovalRequest):
        try:
            return service.approve(
                package_id,
                fact_warning_overridden=request.fact_warning_overridden,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="material not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/materials/{package_id}/reject")
    def reject(package_id: str, request: MaterialFeedbackRequest):
        try:
            return service.reject(package_id, feedback=request.feedback)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="material not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/materials/{package_id}/regenerate", status_code=202)
    def regenerate(package_id: str, request: MaterialFeedbackRequest):
        try:
            pending = service.regenerate(
                package_id,
                feedback=request.feedback,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="material not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "task_id": pending.task.task_id,
            "job_id": pending.task.job_id,
            "material_version": pending.task.material_version,
            "status": "waiting_for_agent",
        }

    return router

