from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.agent.dashboard import ensure_agent_dashboard
from src.agent.doctor import run_agent_doctor


def test_dashboard_reuses_a_healthy_local_service(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "src.agent.dashboard._dashboard_healthy",
        Mock(return_value=True),
    )
    port_probe = Mock()
    monkeypatch.setattr(
        "src.agent.dashboard._port_available",
        port_probe,
    )

    url = ensure_agent_dashboard(
        port=8877,
        project_root=tmp_path,
        open_browser=False,
    )

    assert url == "http://127.0.0.1:8877"
    port_probe.assert_not_called()


def test_dashboard_rejects_a_busy_non_jobsdb_port(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "src.agent.dashboard._dashboard_healthy",
        Mock(return_value=False),
    )
    monkeypatch.setattr(
        "src.agent.dashboard._port_available",
        Mock(return_value=False),
    )

    with pytest.raises(RuntimeError, match="non-JobsDB"):
        ensure_agent_dashboard(
            port=8877,
            project_root=tmp_path,
            open_browser=False,
        )


def test_dashboard_starts_one_detached_process_and_opens_when_ready(
    monkeypatch,
    tmp_path,
) -> None:
    health = Mock(side_effect=[False, True])
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    opened = Mock()
    monkeypatch.setattr(
        "src.agent.dashboard._dashboard_healthy",
        health,
    )
    monkeypatch.setattr(
        "src.agent.dashboard._port_available",
        Mock(return_value=True),
    )
    monkeypatch.setattr("src.agent.dashboard.subprocess.Popen", popen)
    monkeypatch.setattr("src.agent.dashboard.webbrowser.open", opened)

    url = ensure_agent_dashboard(
        port=8877,
        project_root=tmp_path,
        timeout_seconds=1,
    )

    assert url == "http://127.0.0.1:8877"
    assert popen.call_count == 1
    assert popen.call_args.kwargs["start_new_session"] is True
    opened.assert_called_once_with(url)


def test_dashboard_reports_early_child_exit(monkeypatch, tmp_path) -> None:
    process = Mock()
    process.poll.return_value = 1
    monkeypatch.setattr(
        "src.agent.dashboard._dashboard_healthy",
        Mock(return_value=False),
    )
    monkeypatch.setattr(
        "src.agent.dashboard._port_available",
        Mock(return_value=True),
    )
    monkeypatch.setattr(
        "src.agent.dashboard.subprocess.Popen",
        Mock(return_value=process),
    )

    with pytest.raises(RuntimeError, match="exited"):
        ensure_agent_dashboard(
            port=8877,
            project_root=tmp_path,
            open_browser=False,
            timeout_seconds=1,
        )


class _Connection:
    def execute(self, _query):
        return SimpleNamespace(fetchone=lambda: (10,))


class _ConnectionContext:
    def __enter__(self):
        return _Connection()

    def __exit__(self, *_args):
        return None


class _Database:
    def __init__(self, _path):
        pass

    def _connect(self):
        return _ConnectionContext()


def test_agent_doctor_reports_ready_and_missing_locked_integrations(
    monkeypatch,
    tmp_path,
) -> None:
    manifest = SimpleNamespace(
        integrations={
            "application-material": SimpleNamespace(
                url="https://example.test/ai-job-search.git",
                commit="a" * 40,
                required_paths=(),
            ),
            "candidate-profile": SimpleNamespace(
                url="https://example.test/ai-job-search.git",
                commit="a" * 40,
                required_paths=(),
            ),
            "job-evaluation": SimpleNamespace(
                url="https://example.test/career-ops.git",
                commit="b" * 40,
                required_paths=(),
            ),
        }
    )

    class Manager:
        def __init__(self, *_args):
            pass

        def check(self, integration_id):
            return SimpleNamespace(
                status=(
                    "ready"
                    if integration_id == "candidate-profile"
                    else "missing"
                )
                ,
                path=tmp_path / "integrations" / integration_id,
                commit="a" * 40,
            )

    monkeypatch.setattr("src.agent.doctor.Database", _Database)
    monkeypatch.setattr(
        "src.agent.doctor.load_manifest",
        Mock(return_value=manifest),
    )
    monkeypatch.setattr("src.agent.doctor.IntegrationManager", Manager)
    monkeypatch.setattr(
        "src.agent.doctor.scan_tracked_files",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "src.agent.doctor._dashboard_healthy",
        Mock(return_value=False),
    )
    monkeypatch.setattr(
        "src.agent.doctor._port_available",
        Mock(return_value=True),
    )

    checks = run_agent_doctor(8877, project_root=tmp_path)
    by_name = {item["name"]: item for item in checks}

    assert by_name["database"]["status"] == "pass"
    assert by_name["integration:candidate-profile"]["status"] == "pass"
    assert by_name["integration:application-material"]["status"] == "pass"
    assert by_name["integration:job-evaluation"]["status"] == "warn"
    assert by_name["privacy"]["status"] == "pass"
    assert by_name["dashboard"]["status"] == "pass"


def test_agent_doctor_sanitizes_broken_runtime_checks(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "src.agent.doctor.Database",
        Mock(side_effect=RuntimeError("/private/database")),
    )
    monkeypatch.setattr(
        "src.agent.doctor.load_manifest",
        Mock(side_effect=ValueError("/private/manifest")),
    )
    monkeypatch.setattr(
        "src.agent.doctor.scan_tracked_files",
        Mock(side_effect=RuntimeError("/private/git")),
    )
    monkeypatch.setattr(
        "src.agent.doctor._dashboard_healthy",
        Mock(return_value=False),
    )
    monkeypatch.setattr(
        "src.agent.doctor._port_available",
        Mock(return_value=False),
    )

    checks = run_agent_doctor(8877, project_root=tmp_path)
    rendered = str(checks)

    assert "/private" not in rendered
    assert {item["status"] for item in checks} >= {"pass", "fail"}
