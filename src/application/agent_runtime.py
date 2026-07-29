"""Construct the production unified Agent-work coordinator."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from config.settings import get_config
from src.application.agent_work_coordinator import AgentWorkCoordinator
from src.application.runtime import (
    build_material_generation_service,
    build_workflow,
)
from src.dashboard.evaluation_progress import (
    EvaluationProgressStore,
    EvaluationTaskStatus,
)
from src.storage.agent_work_repository import AgentWorkRepository
from src.storage.database import Database
from src.storage.job_batch_repository import JobBatchRepository
from src.storage.material_repository import MaterialRepository


class RuntimeAgentWorkSources:
    def __init__(
        self,
        *,
        progress: EvaluationProgressStore,
        materials: MaterialRepository,
    ) -> None:
        self.progress = progress
        self.materials = materials

    def current_evaluation_task_ids(self) -> tuple[str, ...]:
        return self.progress.pending_task_ids()

    def pending_material_task_ids(self) -> tuple[str, ...]:
        return tuple(task.id for task in self.materials.list_pending())


class RuntimeAgentWorkDispatcher:
    def __init__(
        self,
        *,
        database: Database,
        progress: EvaluationProgressStore,
        workflow,
        materials,
    ) -> None:
        self.database = database
        self.progress = progress
        self.workflow = workflow
        self.materials = materials

    def submit_evaluation(self, task_id: str, payload: dict) -> object:
        evaluation = self.workflow.submit_evaluation_result(task_id, payload)
        with suppress(KeyError):
            self.progress.mark(task_id, EvaluationTaskStatus.COMPLETED)
            if self.progress.get().status == "completed":
                current = JobBatchRepository(self.database).current()
                if current is not None:
                    JobBatchRepository(self.database).mark_scored(current.id)
        return evaluation

    def submit_material(self, task_id: str, payload: dict) -> object:
        return self.materials.submit(
            self.materials.load_pending(task_id),
            payload,
            completed_at=datetime.now(UTC),
        )


def build_agent_work_coordinator(
    project_root: Path | None = None,
) -> AgentWorkCoordinator:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    database = Database(get_config().storage.database_path)
    progress = EvaluationProgressStore(
        root / "workspace" / "dashboard" / "evaluation-progress.json"
    )
    materials = build_material_generation_service(root)
    return AgentWorkCoordinator(
        work=AgentWorkRepository(database),
        sources=RuntimeAgentWorkSources(
            progress=progress,
            materials=MaterialRepository(database),
        ),
        dispatcher=RuntimeAgentWorkDispatcher(
            database=database,
            progress=progress,
            workflow=build_workflow(root),
            materials=materials,
        ),
        tasks_root=root / "workspace" / "ai-tasks",
    )
