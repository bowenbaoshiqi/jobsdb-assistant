from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.agent_work import (
    AgentHumanGate,
    AgentNextResult,
    AgentWorkEnvelope,
    AgentWorkKind,
    AgentWorkStatus,
)


def test_claimed_envelope_exposes_only_opaque_work_identity() -> None:
    envelope = AgentWorkEnvelope(
        session="agent-session-token",
        work_id="work-" + "a" * 24,
        kind=AgentWorkKind.JOB_EVALUATION,
        task_path="workspace/ai-tasks/task-a/task.json",
        result_path="workspace/ai-tasks/task-a/agent-result.json",
        capability_paths=(
            "integrations/job-evaluation/.agents/skills/career-ops/SKILL.md",
        ),
        attempt=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    payload = envelope.model_dump(mode="json")

    assert payload["protocol_version"] == 1
    assert payload["work_id"] == "work-" + "a" * 24
    assert "job_id" not in payload
    assert "task_id" not in payload
    assert "batch_id" not in payload


def test_claimed_envelope_requires_paths_and_lease() -> None:
    with pytest.raises(ValidationError):
        AgentWorkEnvelope(
            session="agent-session-token",
            work_id="work-" + "a" * 24,
            kind=AgentWorkKind.JOB_EVALUATION,
            attempt=1,
        )


def test_idle_result_cannot_include_work() -> None:
    envelope = AgentWorkEnvelope(
        session="agent-session-token",
        work_id="work-" + "a" * 24,
        kind=AgentWorkKind.JOB_EVALUATION,
        task_path="task.json",
        result_path="result.json",
        capability_paths=(),
        attempt=1,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    with pytest.raises(ValidationError):
        AgentNextResult(state=AgentWorkStatus.IDLE, work=envelope)


def test_human_required_result_uses_a_human_gate() -> None:
    gate = AgentHumanGate(
        session="agent-session-token",
        work_id="work-" + "b" * 24,
        prompt_path="workspace/agent/prompts/work-b.json",
        response_path="workspace/agent/responses/work-b.json",
    )

    result = AgentNextResult(
        state=AgentWorkStatus.HUMAN_REQUIRED,
        work=gate,
    )

    assert result.work == gate


def test_result_rejects_a_mismatched_work_state() -> None:
    gate = AgentHumanGate(
        session="agent-session-token",
        work_id="work-" + "b" * 24,
        prompt_path="prompt.json",
        response_path="response.json",
    )

    with pytest.raises(ValidationError):
        AgentNextResult(state=AgentWorkStatus.CLAIMED, work=gate)
