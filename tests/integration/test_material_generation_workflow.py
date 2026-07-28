from datetime import UTC, datetime
from pathlib import Path

from src.adapters.checkpoint_io import CheckpointStore
from src.domain.material import MaterialMode, MaterialTaskStatus
from tests.unit.test_generate_materials import (
    _evaluation,
    _profile,
    _service,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _valid_result(task, cover: Path) -> dict:
    text = " ".join(["word"] * 120)
    result = {
        "task_id": task.task_id,
        "integration_id": task.integration_id,
        "integration_commit": task.integration_commit,
        "contract_version": task.contract_version,
        "job_id": task.job_id,
        "snapshot_id": task.snapshot_id,
        "snapshot_hash": task.snapshot_hash,
        "profile_id": task.profile_id,
        "profile_version": task.profile_version,
        "profile_hash": task.profile_hash,
        "evaluation_id": task.evaluation_id,
        "material_version": task.material_version,
        "material_mode": task.material_mode,
        "source_cv_hash": task.source_cv_hash,
        "tailored_sections": {
            "professional_summary": "AI leader",
            "career_highlights": ["One", "Two", "Three", "Four"],
            "core_competencies": ["Leadership", "Platforms", "Governance"],
        },
        "cover_letter_path": str(cover),
        "cover_letter_text": text,
        "cover_letter_word_count": 120,
        "change_summary": ["强化企业级 AI 领导经验"],
        "check_order": ["reviewer", "ats", "facts"],
        "reviewer": {"passed": True, "findings": []},
        "ats": {"passed": False, "findings": ["建议增加关键词"]},
        "facts": {"passed": True, "findings": []},
        "engine_provenance": {"engine": "Codex"},
        "prompt_provenance": {"version": "v1"},
    }
    if task.material_mode is MaterialMode.COVER_LETTER_ONLY:
        result.pop("tailored_sections")
    return result


def test_submit_restart_and_regenerate_preserve_immutable_versions(
    tmp_path: Path,
) -> None:
    service, repository, checkpoints, snapshots = _service(tmp_path)
    plan = service.plan_batch(
        batch_id="batch-1",
        profile=_profile(),
        snapshots=snapshots[:1],
        evaluations=[_evaluation(snapshots[0])],
        created_at=NOW,
    )
    pending = plan.pending[0]
    staging = checkpoints.staging_dir(pending.task.task_id)
    cover = staging / "cover-letter.txt"
    cover.write_text(" ".join(["word"] * 120), encoding="utf-8")

    package = service.submit(
        pending,
        _valid_result(pending.task, cover),
        completed_at=NOW,
    )

    assert package.version == 1
    assert Path(package.resume.path).is_file()
    assert package.layout.passed
    assert repository.list_batch("batch-1")[0].status is (
        MaterialTaskStatus.GENERATED
    )
    restored = service.load_pending(pending.task.task_id)
    assert restored.task == pending.task

    regenerated = service.plan_regeneration(
        batch_id="batch-2",
        previous_task_id=pending.task.task_id,
        feedback="Emphasise team leadership",
        created_at=NOW,
    )
    assert regenerated.task.material_version == 2
    assert regenerated.task.feedback == "Emphasise team leadership"
    assert repository.latest_for_job("job-1").version == 1
    assert len(repository.list_versions("job-1")) == 1
    assert CheckpointStore(tmp_path / "tasks").read_task(
        regenerated.task.task_id
    )["material_version"] == 2


def test_cover_letter_only_skips_resume_rendering_and_preserves_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, _repository, checkpoints, snapshots = _service(tmp_path)
    plan = service.plan_batch(
        batch_id="batch-cover",
        profile=_profile(),
        snapshots=snapshots[:1],
        evaluations=[_evaluation(snapshots[0])],
        material_mode=MaterialMode.COVER_LETTER_ONLY,
        created_at=NOW,
    )
    pending = plan.pending[0]
    cover = checkpoints.staging_dir(
        pending.task.task_id
    ) / "cover-letter.txt"
    cover.write_text(" ".join(["word"] * 120), encoding="utf-8")
    monkeypatch.setattr(
        "src.application.generate_materials.render_tailored_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("resume renderer must not run")
        ),
    )

    package = service.submit(
        pending,
        _valid_result(pending.task, cover),
        completed_at=NOW,
    )
    regenerated = service.plan_regeneration(
        batch_id="batch-cover-regenerated",
        previous_task_id=pending.task.task_id,
        feedback="Make the opening more specific",
        created_at=NOW,
    )

    assert package.material_mode is MaterialMode.COVER_LETTER_ONLY
    assert package.resume is None
    assert Path(package.cover_letter.path).is_file()
    assert regenerated.task.material_mode is MaterialMode.COVER_LETTER_ONLY
