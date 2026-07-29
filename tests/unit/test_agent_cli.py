import json
from datetime import UTC, datetime
from unittest.mock import Mock

from typer.testing import CliRunner

from src.agent.dashboard import _dashboard_healthy
from src.domain.agent_work import AgentNextResult, AgentWorkStatus
from src.main import app

runner = CliRunner()


def test_agent_start_prints_session_without_internal_ids(
    monkeypatch,
    tmp_path,
) -> None:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF")
    coordinator = Mock()
    coordinator.start.return_value = Mock(
        id="agent-session-token",
        started_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "src.main._build_agent_work_coordinator",
        lambda: coordinator,
    )
    ensure_dashboard = Mock()
    monkeypatch.setattr(
        "src.main._ensure_agent_dashboard",
        ensure_dashboard,
    )

    result = runner.invoke(
        app,
        [
            "agent",
            "start",
            "--port",
            "8877",
            "--source",
            str(resume),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "dashboard_url": "http://127.0.0.1:8877",
        "protocol_version": 1,
        "session": "agent-session-token",
        "state": "active",
    }
    assert "run_id" not in payload
    coordinator.prepare_profile.assert_called_once()
    assert (
        coordinator.prepare_profile.call_args.kwargs["source_documents"]
        == (str(resume),)
    )
    ensure_dashboard.assert_called_once_with(port=8877)


def test_agent_next_prints_one_machine_readable_result(monkeypatch) -> None:
    coordinator = Mock()
    coordinator.next.return_value = AgentNextResult(
        state=AgentWorkStatus.IDLE
    )
    monkeypatch.setattr(
        "src.main._build_agent_work_coordinator",
        lambda: coordinator,
    )

    result = runner.invoke(
        app,
        [
            "agent",
            "next",
            "--session",
            "agent-session-token",
            "--wait",
            "0",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["state"] == "idle"
    coordinator.next.assert_called_once()


def test_agent_doctor_prints_structured_sanitized_checks(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.main._run_agent_doctor",
        lambda port: (
            {
                "name": "database",
                "status": "pass",
                "detail": "schema 8 ready",
            },
        ),
    )

    result = runner.invoke(app, ["agent", "doctor", "--port", "8877"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["checks"][0]["detail"] == "schema 8 ready"


def test_agent_submit_accepts_only_opaque_work_id(
    monkeypatch,
    tmp_path,
) -> None:
    result_file = tmp_path / "result.json"
    result_file.write_text("{}", encoding="utf-8")
    coordinator = Mock()
    coordinator.submit.return_value = Mock(
        id="work-" + "a" * 24,
        status=AgentWorkStatus.COMPLETED,
        result_hash="a" * 64,
    )
    monkeypatch.setattr(
        "src.main._build_agent_work_coordinator",
        lambda: coordinator,
    )

    result = runner.invoke(
        app,
        [
            "agent",
            "submit",
            "--session",
            "agent-session-token",
            "--work-id",
            "work-" + "a" * 24,
            "--result",
            str(result_file),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "completed"
    assert "task_id" not in payload


def test_agent_submit_rejects_internal_task_id_option(tmp_path) -> None:
    result_file = tmp_path / "result.json"
    result_file.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "agent",
            "submit",
            "--session",
            "agent-session-token",
            "--task-id",
            "evaluation-private",
            "--result",
            str(result_file),
        ],
    )

    assert result.exit_code != 0


def test_agent_next_rejects_wait_above_protocol_limit() -> None:
    result = runner.invoke(
        app,
        [
            "agent",
            "next",
            "--session",
            "agent-session-token",
            "--wait",
            "31",
        ],
    )

    assert result.exit_code != 0


def test_dashboard_health_accepts_the_existing_account_payload(
    monkeypatch,
) -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(
        "src.agent.dashboard.urllib.request.urlopen",
        Mock(return_value=response),
    )
    monkeypatch.setattr(
        "src.agent.dashboard.json.load",
        Mock(return_value={"account_alias": "default"}),
    )

    assert _dashboard_healthy("http://127.0.0.1:8877") is True


def test_dashboard_health_accepts_the_current_status_payload(
    monkeypatch,
) -> None:
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(
        "src.agent.dashboard.urllib.request.urlopen",
        Mock(return_value=response),
    )
    monkeypatch.setattr(
        "src.agent.dashboard.json.load",
        Mock(
            return_value={
                "status": "ok",
                "database": "ready",
                "dashboard_version": "0.6.0",
            }
        ),
    )

    assert _dashboard_healthy("http://127.0.0.1:8877") is True
