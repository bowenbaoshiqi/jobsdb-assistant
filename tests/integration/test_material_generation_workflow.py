from datetime import UTC, datetime
from pathlib import Path

from src.adapters.checkpoint_io import CheckpointStore
from src.domain.material import MaterialTaskStatus
from tests.unit.test_generate_materials import (
    _evaluation,
    _profile,
    _service,
)

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _valid_result(task, resume: Path, cover: Path) -> dict:
    text = " ".join(["word"] * 120)
    return {
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
        "source_cv_hash": task.source_cv_hash,
        "tailored_cv_source": {"summary": "AI leader"},
        "resume_path": str(resume),
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
    resume = staging / "cv.pdf"
    resume.write_bytes(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    cover = staging / "cover-letter.txt"
    cover.write_text(" ".join(["word"] * 120), encoding="utf-8")

    package = service.submit(
        pending,
        _valid_result(pending.task, resume, cover),
        completed_at=NOW,
    )

    assert package.version == 1
    assert Path(package.resume.path).is_file()
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
