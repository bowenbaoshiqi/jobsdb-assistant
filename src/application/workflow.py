"""Minimal Python-owned v0.3 candidate and evaluation workflow."""

from datetime import datetime
from typing import Protocol

from src.application.candidate_onboarding import (
    CandidateOnboarding,
    OnboardingOutcome,
)
from src.application.evaluate_jobs import (
    EvaluationPlan,
    EvaluationService,
)
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.integrations.manager import IntegrationState
from src.reporting.evaluation_report import (
    EvaluationReportItem,
    render_text,
)
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository

_INTEGRATION_IDS = ("candidate-profile", "job-evaluation")


class IntegrationManagerPort(Protocol):
    def check(self, integration_id: str) -> IntegrationState: ...

    def install_missing(
        self,
        integration_id: str,
    ) -> IntegrationState: ...


class CandidateEvaluationWorkflow:
    """Coordinate v0.3 components without controlling AI reasoning."""

    def __init__(
        self,
        database: Database,
        profiles: CandidateRepository,
        onboarding: CandidateOnboarding,
        evaluations: EvaluationService,
        evaluation_repository: EvaluationRepository,
        integrations: IntegrationManagerPort,
    ) -> None:
        self.database = database
        self.profiles = profiles
        self.onboarding = onboarding
        self.evaluations = evaluations
        self.evaluation_repository = evaluation_repository
        self.integrations = integrations

    def _ensure_integrations(self, *, first_run: bool) -> None:
        for integration_id in _INTEGRATION_IDS:
            state = self.integrations.check(integration_id)
            if state.status == "ready":
                continue
            if first_run and state.status == "missing":
                state = self.integrations.install_missing(integration_id)
            if state.status != "ready":
                raise RuntimeError(
                    f"integration {integration_id} is {state.status}; "
                    "run explicit repair"
                )

    def prepare_profile(
        self,
        run_id: str,
        source_documents: list[str],
        *,
        update: bool,
    ) -> OnboardingOutcome:
        active = self.profiles.get_active()
        self._ensure_integrations(first_run=active is None)
        return self.onboarding.ensure_profile(
            run_id,
            source_documents,
            update=update,
        )

    def submit_profile_result(
        self,
        run_id: str,
        task_id: str,
        payload: dict,
    ) -> OnboardingOutcome:
        return self.onboarding.submit_result(
            run_id,
            task_id,
            payload,
        )

    def submit_profile_answers(
        self,
        run_id: str,
        source_documents: list[str],
        answers: dict,
    ) -> OnboardingOutcome:
        return self.onboarding.submit_answers(
            run_id,
            source_documents,
            answers,
        )

    def confirm_profile(
        self,
        proposal_id: str,
        *,
        confirmed_at: datetime,
    ) -> CandidateProfile:
        return self.onboarding.confirm(
            proposal_id,
            confirmed_at=confirmed_at,
        )

    def prepare_evaluations(self, run_id: str) -> EvaluationPlan:
        self._ensure_integrations(first_run=False)
        profile = self.profiles.get_active()
        if profile is None:
            raise ValueError("confirmed candidate profile is required")
        return self.evaluations.plan(
            run_id,
            profile,
            self.database.list_current_snapshot_records(),
        )

    def submit_evaluation_result(
        self,
        task_id: str,
        payload: dict,
    ) -> JobEvaluation:
        pending = self.evaluations.load_pending(task_id)
        return self.evaluations.submit(pending, payload)

    def report(self) -> str:
        profile = self.profiles.get_active()
        if profile is None:
            raise ValueError("confirmed candidate profile is required")
        snapshots = {
            item.snapshot_id: item
            for item in self.database.list_current_snapshot_records()
        }
        evaluations = self.evaluation_repository.list_current(
            profile.version
        )
        items = [
            EvaluationReportItem(
                snapshot=snapshots[evaluation.job_snapshot_id],
                evaluation=evaluation,
            )
            for evaluation in evaluations
            if evaluation.job_snapshot_id in snapshots
        ]
        return render_text(items)
