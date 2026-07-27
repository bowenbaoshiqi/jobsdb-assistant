from datetime import UTC, datetime

import pytest

from src.domain.workflow import (
    AITask,
    RunCondition,
    TaskStatus,
    TaskType,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStage,
    next_stage,
)

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def test_python_accepts_only_declared_workflow_transitions() -> None:
    assert next_stage(
        WorkflowStage.CREATED,
        WorkflowEvent.INTEGRATIONS_CHECKED,
    ) is WorkflowStage.INTEGRATIONS_CHECKED
    assert next_stage(
        WorkflowStage.INTEGRATIONS_CHECKED,
        WorkflowEvent.PROFILE_REUSED,
    ) is WorkflowStage.PROFILE_READY

    with pytest.raises(ValueError, match="illegal workflow transition"):
        next_stage(
            WorkflowStage.CREATED,
            WorkflowEvent.DISCOVERY_COMPLETED,
        )


def test_waiting_is_a_condition_not_a_business_stage() -> None:
    run = WorkflowRun(
        id="run-1",
        keyword="AI Architect",
        stage=WorkflowStage.PROFILE_TASK_READY,
        condition=RunCondition.WAITING_FOR_AGENT,
        created_at=NOW,
        updated_at=NOW,
    )

    assert run.stage is WorkflowStage.PROFILE_TASK_READY
    assert run.condition is RunCondition.WAITING_FOR_AGENT


def test_ai_task_is_bound_to_run_type_attempt_and_contract() -> None:
    task = AITask(
        id="candidate-profile-run-1",
        run_id="run-1",
        type=TaskType.CANDIDATE_PROFILE,
        status=TaskStatus.PENDING,
        contract_version="candidate-profile.v1",
        integration_id="candidate-profile",
        integration_commit="a" * 40,
        input_hash="b" * 64,
        attempt=1,
        created_at=NOW,
    )

    assert task.attempt == 1
    assert task.status is TaskStatus.PENDING
