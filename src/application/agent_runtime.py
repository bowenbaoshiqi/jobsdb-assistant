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
from src.domain.agent_work import AgentWorkKind
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

    def mark_claimed(
        self,
        kind: AgentWorkKind,
        task_id: str,
        *,
        now: datetime,
    ) -> None:
        if kind is AgentWorkKind.JOB_EVALUATION:
            self.progress.mark(task_id, EvaluationTaskStatus.RUNNING)
        elif kind is AgentWorkKind.APPLICATION_MATERIAL:
            self.materials.repository.start_task(
                task_id,
                started_at=now,
            )

    def mark_failed(
        self,
        kind: AgentWorkKind,
        task_id: str,
        *,
        error_message: str,
        now: datetime,
    ) -> None:
        if kind is AgentWorkKind.JOB_EVALUATION:
            self.progress.mark(task_id, EvaluationTaskStatus.FAILED)
            if self.progress.get().status == "completed":
                current = JobBatchRepository(self.database).current()
                if current is not None:
                    JobBatchRepository(self.database).mark_scored(current.id)
        elif kind is AgentWorkKind.APPLICATION_MATERIAL:
            self.materials.repository.fail_task(
                task_id,
                error_message=error_message,
                completed_at=now,
            )

    def prepare_profile(
        self,
        run_id: str,
        source_documents: list[str],
        *,
        update: bool,
    ) -> object:
        return self.workflow.prepare_profile(
            run_id,
            source_documents,
            update=update,
        )

    def submit_profile_result(
        self,
        run_id: str,
        task_id: str,
        payload: dict,
    ) -> object:
        return self.workflow.submit_profile_result(
            run_id,
            task_id,
            payload,
        )

    def submit_profile_answers(
        self,
        run_id: str,
        source_documents: list[str],
        answers: dict,
    ) -> object:
        return self.workflow.submit_profile_answers(
            run_id,
            source_documents,
            answers,
        )

    def confirm_profile(self, proposal_id: str) -> object:
        return self.workflow.confirm_profile(
            proposal_id,
            confirmed_at=datetime.now(UTC),
        )

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
