from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.adapters.candidate_profile import CandidateProfileAdapter
from src.adapters.career_ops_profile import CareerOpsProfileAdapter
from src.adapters.checkpoint_io import CheckpointStore
from src.adapters.job_evaluation import JobEvaluationAdapter
from src.application.candidate_onboarding import CandidateOnboarding
from src.application.evaluate_jobs import EvaluationService
from src.application.workflow import CandidateEvaluationWorkflow
from src.domain.candidate import CandidateProfileProposal, FactEvidence
from src.integrations.manager import IntegrationState
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository

NOW = datetime(2026, 7, 24, tzinfo=UTC)


class FakeIntegrationManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.ready_ids: set[str] = set()
        self.install_calls: list[str] = []

    @property
    def ready(self) -> bool:
        return len(self.ready_ids) == 2

    @ready.setter
    def ready(self, value: bool) -> None:
        self.ready_ids = (
            {"candidate-profile", "job-evaluation"} if value else set()
        )

    def check(self, integration_id: str) -> IntegrationState:
        return IntegrationState(
            id=integration_id,
            path=self.root / integration_id,
            commit="a" * 40,
            status=(
                "ready"
                if integration_id in self.ready_ids
                else "missing"
            ),
        )

    def install_missing(self, integration_id: str) -> IntegrationState:
        self.install_calls.append(integration_id)
        self.ready_ids.add(integration_id)
        return self.check(integration_id)


def workflow(tmp_path: Path):
    database = Database(str(tmp_path / "jobs.db"))
    profiles = CandidateRepository(database)
    checkpoints = CheckpointStore(tmp_path / "workspace" / "ai-tasks")
    integrations = FakeIntegrationManager(tmp_path / "integrations")
    onboarding = CandidateOnboarding(
        profiles,
        CandidateProfileAdapter("a" * 40, "candidate-profile.v2"),
        checkpoints,
    )
    evaluation_service = EvaluationService(
        EvaluationRepository(database),
        JobEvaluationAdapter("a" * 40, "career-ops-native-af.v1"),
        checkpoints,
        CareerOpsProfileAdapter(
            workspace_root=(
                tmp_path / "workspace" / "career-ops-profiles"
            ),
            candidate_integration_commit="a" * 40,
            career_ops_integration_commit="a" * 40,
            forbidden_roots=(tmp_path / "integrations",),
        ),
    )
    return (
        CandidateEvaluationWorkflow(
            database=database,
            profiles=profiles,
            onboarding=onboarding,
            evaluations=evaluation_service,
            evaluation_repository=EvaluationRepository(database),
            integrations=integrations,
        ),
        profiles,
        integrations,
    )


def proposal() -> CandidateProfileProposal:
    return CandidateProfileProposal(
        id="proposal-1",
        verified_facts={"skills": ["Python"]},
        fact_evidence={
            "Python": [FactEvidence(source="cv.md", locator="skills")]
        },
        target_roles=["AI Architect"],
        created_at=NOW,
    )


def test_first_profile_run_installs_locked_integrations(
    tmp_path: Path,
) -> None:
    app, _profiles, integrations = workflow(tmp_path)

    outcome = app.prepare_profile("run-1", [], update=False)

    assert outcome.task_id is not None
    assert integrations.install_calls == [
        "candidate-profile",
        "job-evaluation",
    ]


def test_later_profile_run_reuses_profile_without_install(
    tmp_path: Path,
) -> None:
    app, profiles, integrations = workflow(tmp_path)
    integrations.ready = True
    profiles.create_proposal("run-1", proposal())
    profiles.confirm("proposal-1", confirmed_at=NOW)

    outcome = app.prepare_profile("run-2", [], update=False)

    assert outcome.profile_version == 1
    assert integrations.install_calls == []


def test_evaluation_requires_confirmed_profile(tmp_path: Path) -> None:
    app, _profiles, integrations = workflow(tmp_path)
    integrations.ready = True

    with pytest.raises(ValueError, match="confirmed candidate profile"):
        app.prepare_evaluations("run-1")


def test_evaluation_requires_explicit_update_for_legacy_profile(
    tmp_path: Path,
) -> None:
    app, profiles, integrations = workflow(tmp_path)
    integrations.ready = True
    profiles.create_proposal("run-1", proposal())
    profiles.confirm("proposal-1", confirmed_at=NOW)

    with pytest.raises(
        ValueError,
        match="requires explicit update before career-ops evaluation",
    ):
        app.prepare_evaluations("run-2")
