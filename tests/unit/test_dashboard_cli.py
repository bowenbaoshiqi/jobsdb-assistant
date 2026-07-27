from unittest.mock import Mock

from typer.testing import CliRunner

from src.dashboard import cli
from src.dashboard.cli import CheckState, run_dashboard_doctor
from src.main import app
from src.storage.database import Database

runner = CliRunner()


def test_start_binds_only_loopback(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr("src.dashboard.cli.uvicorn.run", run)
    monkeypatch.setattr(
        "src.dashboard.cli.build_production_app",
        lambda: object(),
    )
    monkeypatch.setattr(
        "src.dashboard.cli._port_available",
        lambda _host, _port: True,
    )

    result = runner.invoke(
        app,
        ["dashboard", "start", "--no-browser"],
    )

    assert result.exit_code == 0
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8765


def test_doctor_reports_schema_counts_without_private_values(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.db"
    Database(str(database_path))

    results = run_dashboard_doctor(
        database_path=str(database_path),
        host="127.0.0.1",
        port=8765,
        port_probe=lambda _host, _port: True,
    )
    rendered = " ".join(
        f"{item.name} {item.state.value} {item.detail}"
        for item in results
    ).casefold()

    assert "database" in rendered
    assert "evaluation" in rendered
    assert "job" in rendered
    assert "password" not in rendered
    assert str(tmp_path).casefold() not in rendered
    assert all(item.state is CheckState.PASS for item in results)


def test_doctor_command_fails_for_busy_port(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "_port_available",
        lambda _host, _port: False,
    )

    result = runner.invoke(
        app,
        ["dashboard", "doctor", "--port", "8765"],
    )

    assert result.exit_code == 1
    assert "in use" in result.stdout.casefold()


def test_start_fails_without_switching_busy_port(monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr("src.dashboard.cli.uvicorn.run", run)
    monkeypatch.setattr(
        "src.dashboard.cli._port_available",
        lambda _host, _port: False,
    )

    result = runner.invoke(
        app,
        ["dashboard", "start", "--port", "8765", "--no-browser"],
    )

    assert result.exit_code == 1
    assert "8765" in result.stdout
    run.assert_not_called()
