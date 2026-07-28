from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.dashboard.app import DashboardDependencies, create_dashboard_app
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.evaluation_progress import EvaluationProgressStore
from src.dashboard.query_service import DashboardQueryService
from src.domain.job import ApplyType, JobDetailCapture
from src.domain.application_execution import (
    ApplicationExecution,
    ApplicationExecutionStatus,
    ApplicationIdentity,
)
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


def _save_job(
    database: Database,
    job_id: str,
    apply_type: ApplyType,
) -> None:
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
            title=f"Role {job_id}",
            company="Example Corporation",
            location="Hong Kong",
            jd_text=f"Full JD for {job_id}",
            apply_type=apply_type,
        ),
        captured_at=NOW,
    )


@pytest.fixture
def dashboard_api(tmp_path) -> tuple[TestClient, AsyncMock]:
    database = Database(":memory:")
    _save_job(database, "quick-1", ApplyType.QUICK_APPLY)
    _save_job(database, "apply-1", ApplyType.APPLY)
    runner = AsyncMock(return_value={"success": 1, "session_id": "session-1"})
    application_service = DashboardApplicationService(
        database,
        runner=runner,
        now=lambda: NOW,
    )
    approved = MagicMock()
    approved.queue.return_value = ApplicationExecution(
        id="approved-1",
        identity=ApplicationIdentity(
            job_id="quick-1",
            snapshot_id="1",
            snapshot_hash="a" * 64,
            account_alias="default",
            package_id="package-1",
            material_version=1,
            resume_sha256="b" * 64,
            cover_letter_sha256="c" * 64,
            apply_type=ApplyType.QUICK_APPLY,
        ),
        status=ApplicationExecutionStatus.QUEUED,
        remote_resume_filename="JBA_quick-1_v1_bbbbbbbb.pdf",
        created_at=NOW,
        updated_at=NOW,
    )
    approved.confirm_submission.return_value = (
        approved.queue.return_value.model_copy(
            update={"status": ApplicationExecutionStatus.SUBMITTING}
        )
    )
    approved.manual_handoff.return_value = SimpleNamespace(
        execution_id="manual-1",
        job_url="https://hk.jobsdb.com/job/apply-1",
        resume_path=Path("/private/cv.pdf"),
        cover_letter_text="Approved cover letter.",
    )
    app = create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(database),
            selection_repository=SelectionRepository(database),
            application_service=application_service,
            approved_application_service=approved,
            evaluation_progress=EvaluationProgressStore(
                tmp_path / "evaluation-progress.json"
            ),
        )
    )
    return TestClient(app), runner


def test_health_is_ready(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    assert client.get("/health").json() == {
        "status": "ok",
        "database": "ready",
        "dashboard_version": "0.5.0",
    }


def test_jobs_endpoint_supports_all_mode(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.get("/api/jobs", params={"show": "all"})

    assert response.status_code == 200
    assert {job["job_id"] for job in response.json()["jobs"]} == {
        "quick-1",
        "apply-1",
    }


def test_evaluation_progress_endpoint_reports_current_batch(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api
    store = client.app.state.dashboard_dependencies.evaluation_progress
    store.start(["task-1", "task-2"], now=NOW)

    response = client.get("/api/evaluation-progress")

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert response.json()["total"] == 2
    assert response.json()["queued"] == 2


def test_selection_lifecycle(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    selected = client.put("/api/selections/quick-1")

    assert selected.status_code == 200
    assert selected.json()["status"] == "waiting_for_materials"
    assert client.delete("/api/selections/quick-1").status_code == 204


def test_unknown_selection_returns_not_found(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    assert client.put("/api/selections/missing").status_code == 404


def test_quick_apply_requires_exact_modes(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.post(
        "/api/jobs/quick-1/quick-apply",
        json={"resume_mode": "uploaded", "cover_letter_mode": "generated"},
    )

    assert response.status_code == 422


def test_apply_job_is_rejected_without_execution(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, runner = dashboard_api

    response = client.post(
        "/api/jobs/apply-1/quick-apply",
        json={
            "resume_mode": "jobsdb_default",
            "cover_letter_mode": "none",
        },
    )

    assert response.status_code == 409
    runner.assert_not_awaited()


def test_quick_apply_returns_durable_task(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, runner = dashboard_api

    response = client.post(
        "/api/jobs/quick-1/quick-apply",
        json={
            "resume_mode": "jobsdb_default",
            "cover_letter_mode": "none",
        },
    )

    assert response.status_code == 202
    task_id = response.json()["id"]
    restored = client.get(f"/api/applications/{task_id}")
    assert restored.status_code == 200
    assert restored.json()["status"] in {"applying", "submitted"}
    assert restored.json()["resume_mode"] == "jobsdb_default"
    assert restored.json()["cover_letter_mode"] == "none"
    assert "password" not in restored.text.casefold()
    assert runner.await_count <= 1


def test_prepare_approved_application_queues_worker_task(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api
    service = (
        client.app.state.dashboard_dependencies
        .approved_application_service
    )

    response = client.post(
        "/api/jobs/quick-1/applications/prepare",
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    service.queue.assert_called_once_with(
        "quick-1",
        account_alias="default",
    )


def test_confirm_approved_application_requires_explicit_action(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.post(
        "/api/approved-applications/approved-1/confirm",
    )

    assert response.status_code == 202
    assert response.json()["status"] == "submitting"


def test_apply_manual_handoff_returns_safe_material_links(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.post(
        "/api/jobs/apply-1/applications/manual-handoff",
    )

    assert response.status_code == 200
    assert response.json() == {
        "execution_id": "manual-1",
        "job_url": "https://hk.jobsdb.com/job/apply-1",
        "resume_url": "/api/jobs/apply-1/approved-resume",
        "cover_letter_text": "Approved cover letter.",
    }
    assert "/private/cv.pdf" not in response.text


def test_dashboard_html_loads(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.get("/")

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.text
    assert "JobsDB 求职助手" in response.text


def test_page_contains_review_and_safe_action_controls(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    html = client.get("/").text

    assert 'id="job-list"' in html
    assert 'id="selected-count"' in html
    assert 'id="show-filter"' in html
    assert "使用默认简历直接投递" in html
    assert "打开职位并人工投递" in html
    assert 'id="generate-materials"' in html
    assert "为已选职位生成定制材料" in html
    assert 'id="apply-confirmation"' in html
    assert 'id="evaluation-progress"' in html
    assert 'id="refresh-results"' in html
    assert "刷新评分结果" in html
    assert "使用已批准材料准备申请" in html
    assert "确认并提交申请" in html
    assert "下载定制简历并人工投递" in html


def test_material_preview_page_is_simplified_chinese(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    response = client.get("/materials/package-1")

    assert response.status_code == 200
    assert '<html lang="zh-CN">' in response.text
    assert 'id="resume-preview"' in response.text
    assert 'id="cover-letter-preview"' in response.text
    assert "Reviewer 建议" in response.text
    assert "ATS 建议" in response.text
    assert "事实一致性检查" in response.text
    assert "批准材料" in response.text
    assert "标记不通过" in response.text
    assert "重新生成" in response.text


def test_dashboard_javascript_does_not_schedule_automatic_refresh(
    dashboard_api: tuple[TestClient, AsyncMock],
) -> None:
    client, _runner = dashboard_api

    javascript = client.get("/static/dashboard.js").text

    assert "setInterval" not in javascript
