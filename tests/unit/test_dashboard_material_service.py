from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dashboard.material_service import DashboardMaterialService
from src.domain.material import (
    MaterialMode,
    MaterialReviewAction,
    MaterialReviewStatus,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


class FakeRepository:
    def __init__(self, package=None) -> None:
        self.package = package
        self.events = []

    def get_package(self, package_id):
        if self.package is None or self.package.id != package_id:
            raise KeyError(package_id)
        return self.package

    def list_versions(self, job_id):
        return [] if self.package is None else [self.package]

    def list_review_events(self, package_id):
        return list(self.events)

    def record_review(self, package_id, action, **kwargs):
        status = (
            MaterialReviewStatus.REJECTED
            if action is MaterialReviewAction.REJECT
            else MaterialReviewStatus.APPROVED
        )
        event = SimpleNamespace(
            id="event-1",
            package_id=package_id,
            action=action,
            resulting_status=status,
            feedback=kwargs.get("feedback"),
            fact_warning_overridden=kwargs.get(
                "fact_warning_overridden",
                False,
            ),
            created_at=kwargs["reviewed_at"],
        )
        self.events.append(event)
        return event

    def task_id_for_package(self, package_id):
        return "task-1"


class FakeGeneration:
    def plan_regeneration(self, **kwargs):
        return SimpleNamespace(
            task=SimpleNamespace(
                task_id="task-2",
                job_id="job-1",
                material_version=2,
                feedback=kwargs["feedback"],
            )
        )


def test_no_selection_rejects_before_generation() -> None:
    database = SimpleNamespace()
    service = DashboardMaterialService(
        database=database,
        repository=FakeRepository(),
        generation=FakeGeneration(),
        materials_root=Path("workspace/materials"),
        now=lambda: NOW,
    )
    service.selections = SimpleNamespace(list_selected=lambda: {})

    with pytest.raises(ValueError, match="selected"):
        service.create_batch()


def test_selected_batch_passes_requested_material_mode() -> None:
    captured = {}

    class Generation(FakeGeneration):
        def plan_batch(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(batch_id=kwargs["batch_id"], pending=())

    database = SimpleNamespace(
        get_current_job_snapshot_record=lambda job_id: SimpleNamespace(
            job_id=job_id
        )
    )
    service = DashboardMaterialService(
        database=database,
        repository=FakeRepository(),
        generation=Generation(),
        materials_root=Path("workspace/materials"),
        now=lambda: NOW,
    )
    service.selections = SimpleNamespace(
        list_selected=lambda: {"job-1": NOW}
    )
    service.profiles = SimpleNamespace(
        get_active=lambda: SimpleNamespace(version=1)
    )
    service.evaluations = SimpleNamespace(list_current=lambda version: [])

    service.create_batch(MaterialMode.COVER_LETTER_ONLY)

    assert captured["material_mode"] is MaterialMode.COVER_LETTER_ONLY


def test_selected_batch_ignores_selections_from_archived_batches() -> None:
    captured = {}

    class Generation(FakeGeneration):
        def plan_batch(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(batch_id=kwargs["batch_id"], pending=())

    database = SimpleNamespace(
        get_current_job_snapshot_record=lambda job_id: SimpleNamespace(
            job_id=job_id
        )
    )
    service = DashboardMaterialService(
        database=database,
        repository=FakeRepository(),
        generation=Generation(),
        materials_root=Path("workspace/materials"),
        job_batch_repository=SimpleNamespace(
            current_job_ids=lambda: ["job-current"]
        ),
        now=lambda: NOW,
    )
    service.selections = SimpleNamespace(
        list_selected=lambda: {"job-current": NOW, "job-archived": NOW}
    )
    service.profiles = SimpleNamespace(
        get_active=lambda: SimpleNamespace(version=1)
    )
    service.evaluations = SimpleNamespace(list_current=lambda version: [])

    service.create_batch(MaterialMode.COVER_LETTER_ONLY)

    assert [item.job_id for item in captured["snapshots"]] == ["job-current"]


def test_review_actions_are_explicit_and_regeneration_keeps_feedback() -> None:
    package = SimpleNamespace(
        id="package-1",
        job_id="job-1",
        version=1,
        review_status=MaterialReviewStatus.PENDING_REVIEW,
        facts=SimpleNamespace(passed=True, findings=[]),
        resume=SimpleNamespace(path="/private/cv.pdf"),
        cover_letter=SimpleNamespace(path="/private/cover.txt"),
    )
    repository = FakeRepository(package)
    service = DashboardMaterialService(
        database=SimpleNamespace(),
        repository=repository,
        generation=FakeGeneration(),
        materials_root=Path("/private"),
        now=lambda: NOW,
    )

    approved = service.approve("package-1", fact_warning_overridden=False)
    rejected = service.reject("package-1", feedback="Not suitable")
    regenerated = service.regenerate(
        "package-1",
        feedback="Emphasise leadership",
    )

    assert approved.action is MaterialReviewAction.APPROVE
    assert rejected.action is MaterialReviewAction.REJECT
    assert regenerated.task.material_version == 2
    assert regenerated.task.feedback == "Emphasise leadership"
