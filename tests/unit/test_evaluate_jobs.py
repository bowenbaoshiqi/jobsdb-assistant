from datetime import UTC, datetime
from pathlib import Path

from src.adapters.career_ops_profile import CareerOpsProfileBundle
from src.adapters.checkpoint_io import CheckpointStore
from src.adapters.job_evaluation import JobEvaluationAdapter
from src.application.evaluate_jobs import EvaluationService
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation, NativeDimension
from src.domain.job import ApplyType, CurrentSnapshotRecord

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def profile(version: int = 1, content: str = "a") -> CandidateProfile:
    return CandidateProfile(
        id=f"profile-{version}",
        version=version,
        verified_facts={"skills": ["Python"]},
        target_roles=["AI Architect"],
        created_at=NOW,
        confirmed_at=NOW,
        content_hash=content * 64,
    )


def snapshot(snapshot_id: str, content: str) -> CurrentSnapshotRecord:
    return CurrentSnapshotRecord(
        snapshot_id=snapshot_id,
        job_id=f"job-{snapshot_id}",
        title="AI Architect",
        company="Synthetic Ltd",
        canonical_url=f"https://hk.jobsdb.com/job/job-{snapshot_id}",
        apply_type=ApplyType.QUICK_APPLY,
        jd_text=f"Synthetic JD {snapshot_id}",
        content_hash=content * 64,
    )


def evaluation(item: CurrentSnapshotRecord) -> JobEvaluation:
    return JobEvaluation(
        id=f"evaluation-{item.snapshot_id}",
        job_snapshot_id=item.snapshot_id,
        profile_version=1,
        profile_hash="a" * 64,
        snapshot_hash=item.content_hash,
        engine_version="career-ops@locked",
        engine_commit="c" * 40,
        prompt_version="career-ops-native-af.v1",
        overall_score=4.2,
        dimensions=[
            NativeDimension(
                code=code,
                title=f"Block {code}",
                score=4.0,
                findings=["Synthetic finding"],
                evidence=["JD: evidence"],
            )
            for code in "ABCDEF"
        ],
        recommendation="strong_apply",
        evidence=["JD: evidence"],
        created_at=NOW,
    )


class FakeEvaluationRepository:
    def __init__(self) -> None:
        self.by_key: dict[str, JobEvaluation] = {}

    def find_by_cache_key(self, key):
        return self.by_key.get(key.digest())

    def save(self, result, key) -> None:
        self.by_key[key.digest()] = result


class FakeProjector:
    def project(self, candidate: CandidateProfile) -> CareerOpsProfileBundle:
        root = Path("/private/profiles") / candidate.content_hash
        return CareerOpsProfileBundle(
            root=root,
            profile_id=candidate.id,
            profile_version=candidate.version,
            profile_hash=candidate.content_hash,
            projection_version="career-ops-profile-bundle.v1",
            bundle_hash=(
                "d" * 64 if candidate.version == 1 else "e" * 64
            ),
            cv_path=root / "cv.md",
            profile_yml_path=root / "config" / "profile.yml",
            profile_md_path=root / "modes" / "_profile.md",
            manifest_path=root / "projection-manifest.json",
            manifest={},
        )


def service(tmp_path: Path, repo: FakeEvaluationRepository):
    return EvaluationService(
        evaluations=repo,
        adapter=JobEvaluationAdapter(
            "c" * 40,
            "career-ops-native-af.v1",
        ),
        checkpoints=CheckpointStore(tmp_path / "workspace" / "ai-tasks"),
        profile_projector=FakeProjector(),
    )


def test_plan_reuses_cache_and_tasks_only_new_snapshots(
    tmp_path: Path,
) -> None:
    repo = FakeEvaluationRepository()
    evaluator = service(tmp_path, repo)
    first = snapshot("1", "b")
    second = snapshot("2", "d")
    candidate = profile()
    first_key = evaluator.cache_key(
        candidate,
        FakeProjector().project(candidate),
        first,
    )
    repo.by_key[first_key.digest()] = evaluation(first)

    plan = evaluator.plan("run-1", profile(), [first, second])

    assert [item.job_snapshot_id for item in plan.cached] == ["1"]
    assert [task.snapshot_id for task in plan.pending] == ["2"]
    assert len(plan.pending) == 1


def test_profile_change_invalidates_cache(tmp_path: Path) -> None:
    evaluator = service(tmp_path, FakeEvaluationRepository())
    item = snapshot("1", "b")

    first_profile = profile(1, "a")
    second_profile = profile(2, "e")
    first = evaluator.cache_key(
        first_profile,
        FakeProjector().project(first_profile),
        item,
    )
    second = evaluator.cache_key(
        second_profile,
        FakeProjector().project(second_profile),
        item,
    )

    assert first.digest() != second.digest()


def test_projection_change_invalidates_cache(tmp_path: Path) -> None:
    evaluator = service(tmp_path, FakeEvaluationRepository())
    candidate = profile()
    item = snapshot("1", "b")
    first_bundle = FakeProjector().project(candidate)
    second_bundle = first_bundle.model_copy(
        update={"bundle_hash": "f" * 64}
    )

    assert evaluator.cache_key(
        candidate,
        first_bundle,
        item,
    ).digest() != evaluator.cache_key(
        candidate,
        second_bundle,
        item,
    ).digest()


def test_same_content_in_two_jobs_has_distinct_cache_keys(
    tmp_path: Path,
) -> None:
    evaluator = service(tmp_path, FakeEvaluationRepository())
    candidate = profile()
    first = snapshot("1", "b")
    second = snapshot("2", "b")
    bundle = FakeProjector().project(candidate)

    assert evaluator.cache_key(
        candidate,
        bundle,
        first,
    ).digest() != evaluator.cache_key(
        candidate,
        bundle,
        second,
    ).digest()


def test_submit_persists_one_native_result(tmp_path: Path) -> None:
    repo = FakeEvaluationRepository()
    evaluator = service(tmp_path, repo)
    item = snapshot("1", "b")
    plan = evaluator.plan("run-1", profile(), [item])
    task = plan.pending[0]
    result = evaluation(item)

    saved = evaluator.submit(task, {
        "task_id": task.task.task_id,
        "evaluations": [result.model_dump(mode="json")],
    })

    assert saved == result
    assert repo.find_by_cache_key(task.cache_key) == result


def test_pending_task_can_be_reloaded_after_agent_checkpoint(
    tmp_path: Path,
) -> None:
    evaluator = service(tmp_path, FakeEvaluationRepository())
    plan = evaluator.plan("run-1", profile(), [snapshot("1", "b")])

    loaded = evaluator.load_pending(plan.pending[0].task.task_id)

    assert loaded.snapshot_id == "1"
    assert loaded.cache_key == plan.pending[0].cache_key
