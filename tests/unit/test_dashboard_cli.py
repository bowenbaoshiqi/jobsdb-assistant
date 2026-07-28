import socket
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from typer.testing import CliRunner

from config.settings import AppConfig
from src.dashboard import cli
from src.dashboard.cli import CheckState, run_dashboard_doctor
from src.main import app
from src.storage.database import Database

runner = CliRunner()


def test_discovery_config_is_headless_without_mutating_application_config() -> None:
    config = AppConfig(_env_file=None)
    config.browser.headless = False

    discovery = cli._headless_discovery_config(config)

    assert discovery is not config
    assert discovery.browser is not config.browser
    assert discovery.browser.headless is True
    assert config.browser.headless is False


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


def test_port_probe_detects_an_occupied_loopback_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]

        assert cli._port_available("127.0.0.1", port) is False

    assert cli._port_available("127.0.0.1", port) is True


def test_doctor_reports_database_failure_without_path(monkeypatch) -> None:
    class BrokenDatabase:
        def __init__(self, _path):
            raise RuntimeError("private/path/database")

    monkeypatch.setattr(cli, "Database", BrokenDatabase)

    results = run_dashboard_doctor(
        database_path="/private/path/database",
        port_probe=lambda _host, _port: True,
    )

    database = next(item for item in results if item.name == "database")
    assert database.state is CheckState.FAIL
    assert database.detail == "unavailable"
    assert "/private" not in " ".join(item.detail for item in results)


def test_build_production_app_does_not_require_login(
    monkeypatch,
    tmp_path,
) -> None:
    config = cli.get_config()
    config.storage.database_path = str(tmp_path / "jobs.db")
    config.login.mode = "manual"
    monkeypatch.setattr(cli, "get_config", lambda: config)

    dashboard = cli.build_production_app()

    assert dashboard.title == "JobsDB Assistant"
    dependencies = dashboard.state.dashboard_dependencies
    assert dependencies.approved_application_service is not None
    assert dashboard.state.approved_application_worker is not None


def test_build_production_app_falls_back_to_manual_login_without_account(
    monkeypatch,
    tmp_path,
) -> None:
    config = cli.get_config()
    config.storage.database_path = str(tmp_path / "jobs.db")
    config.login.mode = "auto"
    placeholder = SimpleNamespace(alias="default", email="", password="")
    registry = MagicMock()
    registry.resolve_active.return_value = placeholder
    monkeypatch.setattr(cli, "get_config", lambda: config)
    monkeypatch.setattr(cli, "AccountRegistry", Mock(return_value=registry))

    dashboard = cli.build_production_app()

    assert dashboard.title == "JobsDB Assistant"
    assert config.login.mode == "manual"
    registry.resolve_active.assert_called_once_with(
        allow_placeholder=True,
    )


def test_start_with_browser_launches_readiness_thread(monkeypatch) -> None:
    run = Mock()
    thread = MagicMock()
    thread_type = Mock(return_value=thread)
    monkeypatch.setattr(cli.uvicorn, "run", run)
    monkeypatch.setattr(cli, "build_production_app", lambda: object())
    monkeypatch.setattr(cli, "_port_available", lambda _host, _port: True)
    monkeypatch.setattr(cli.threading, "Thread", thread_type)

    cli.start_dashboard(port=8877, open_browser=True)

    thread_type.assert_called_once()
    assert thread_type.call_args.kwargs["daemon"] is True
    thread.start.assert_called_once_with()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8877


def test_open_after_ready_opens_only_local_url(monkeypatch) -> None:
    response = MagicMock()
    response.__enter__.return_value = response
    opened = Mock()
    monkeypatch.setattr(cli.urllib.request, "urlopen", Mock(return_value=response))
    monkeypatch.setattr(cli.webbrowser, "open", opened)

    cli._open_after_ready("http://127.0.0.1:8765")

    opened.assert_called_once_with("http://127.0.0.1:8765")
