from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.dashboard.app import DashboardDependencies, create_dashboard_app
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.material_service import DashboardMaterialService
from src.dashboard.query_service import DashboardQueryService
from src.domain.job import ApplyType, JobDetailCapture
from src.domain.material import (
    ApplicationPackage,
    MaterialArtifact,
    MaterialCheck,
)
from src.storage.database import Database
from src.storage.material_repository import MaterialRepository
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, tzinfo=UTC)


class FakeGeneration:
    def plan_regeneration(self, **kwargs):
        return SimpleNamespace(
            task=SimpleNamespace(
                task_id="task-2",
                job_id="job-1",
                material_version=2,
                feedback=kwargs["feedback"],
                status="waiting_for_agent",
            )
        )


def _client(tmp_path: Path, *, fact_warning: bool = False) -> TestClient:
    database = Database(":memory:")
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="job-1",
            canonical_url="https://hk.jobsdb.com/job/job-1",
            title="Head of AI",
            company="Large Corporation",
            location="Hong Kong",
            jd_text="Lead enterprise AI.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )
    snapshot = database.get_current_job_snapshot_record("job-1")
    assert snapshot is not None
    repository = MaterialRepository(database)
    repository.create_task(
        task_id="task-1",
        batch_id="batch-1",
        job_id="job-1",
        snapshot_id=int(snapshot.snapshot_id),
        profile_version=1,
        evaluation_id="evaluation-1",
        target_version=1,
        payload={},
        created_at=NOW,
    )
    material_root = tmp_path / "materials"
    version_root = material_root / "job-1" / "v1"
    version_root.mkdir(parents=True)
    pdf = version_root / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    cover = version_root / "cover-letter.txt"
    cover.write_text(" ".join(["word"] * 120), encoding="utf-8")
    import hashlib

    repository.save_package(
        task_id="task-1",
        package=ApplicationPackage(
            id="package-1",
            job_id="job-1",
            evaluation_id="evaluation-1",
            profile_version=1,
            version=1,
            resume=MaterialArtifact(
                path=str(pdf),
                sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
            ),
            cover_letter=MaterialArtifact(
                path=str(cover),
                sha256=hashlib.sha256(cover.read_bytes()).hexdigest(),
            ),
            cover_letter_word_count=120,
            reviewer=MaterialCheck(
                passed=False,
                findings=["建议强化开头"],
            ),
            ats=MaterialCheck(
                passed=False,
                findings=["建议增加 LLM 关键词"],
            ),
            facts=MaterialCheck(
                passed=not fact_warning,
                findings=(
                    ["疑似未经证实的团队规模"]
                    if fact_warning
                    else []
                ),
            ),
            created_at=NOW,
        ),
        saved_at=NOW,
    )
    material_service = DashboardMaterialService(
        database=database,
        repository=repository,
        generation=FakeGeneration(),
        materials_root=material_root,
        now=lambda: NOW,
    )
    app = create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(database),
            selection_repository=SelectionRepository(database),
            application_service=DashboardApplicationService(
                database,
                runner=AsyncMock(),
            ),
            material_service=material_service,
        )
    )
    return TestClient(app)


def test_material_detail_pdf_approval_rejection_and_regeneration(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    detail = client.get("/api/materials/package-1")
    assert detail.status_code == 200
    assert detail.json()["cover_letter_word_count"] == 120
    assert detail.json()["reviewer"]["findings"] == ["建议强化开头"]
    assert detail.json()["ats"]["findings"] == ["建议增加 LLM 关键词"]
    assert client.get("/api/materials/package-1/pdf").headers[
        "content-type"
    ].startswith("application/pdf")
    assert client.post(
        "/api/materials/package-1/approve",
        json={"fact_warning_overridden": False},
    ).status_code == 200
    assert client.post(
        "/api/materials/package-1/reject",
        json={"feedback": "Too generic"},
    ).status_code == 200
    regenerated = client.post(
        "/api/materials/package-1/regenerate",
        json={"feedback": "Emphasise leadership"},
    )
    assert regenerated.status_code == 202
    assert regenerated.json()["material_version"] == 2


def test_fact_warning_requires_explicit_override(tmp_path: Path) -> None:
    client = _client(tmp_path, fact_warning=True)

    denied = client.post(
        "/api/materials/package-1/approve",
        json={"fact_warning_overridden": False},
    )
    approved = client.post(
        "/api/materials/package-1/approve",
        json={"fact_warning_overridden": True},
    )

    assert denied.status_code == 409
    assert approved.status_code == 200
    assert approved.json()["resulting_status"] == (
        "approved_with_fact_override"
    )


def test_material_pdf_never_accepts_request_supplied_path(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    assert client.get("/api/materials/../../etc/passwd/pdf").status_code == 404
    assert client.get(
        "/api/materials/package-1/pdf",
        params={"path": "/etc/passwd"},
    ).content.startswith(b"%PDF-")
