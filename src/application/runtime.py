"""Construct the real local v0.3 workflow."""

from pathlib import Path

from config.settings import get_config
from src.adapters.candidate_profile import CandidateProfileAdapter
from src.adapters.career_ops_profile import CareerOpsProfileAdapter
from src.adapters.checkpoint_io import CheckpointStore
from src.adapters.job_evaluation import JobEvaluationAdapter
from src.application.candidate_onboarding import CandidateOnboarding
from src.application.evaluate_jobs import EvaluationService
from src.application.workflow import CandidateEvaluationWorkflow
from src.integrations.manager import IntegrationManager
from src.integrations.manifest import load_manifest
from src.storage.candidate_repository import CandidateRepository
from src.storage.database import Database
from src.storage.evaluation_repository import EvaluationRepository


def build_workflow(
    project_root: Path | None = None,
) -> CandidateEvaluationWorkflow:
    root = project_root or Path(__file__).resolve().parents[2]
    manifest = load_manifest(root / "integrations" / "manifest.json")
    database = Database(get_config().storage.database_path)
    profiles = CandidateRepository(database)
    evaluation_repository = EvaluationRepository(database)
    checkpoints = CheckpointStore(root / "workspace" / "ai-tasks")
    candidate_spec = manifest.integrations["candidate-profile"]
    evaluation_spec = manifest.integrations["job-evaluation"]
    return CandidateEvaluationWorkflow(
        database=database,
        profiles=profiles,
        onboarding=CandidateOnboarding(
            profiles,
            CandidateProfileAdapter(
                candidate_spec.commit,
                candidate_spec.contract_version,
            ),
            checkpoints,
        ),
        evaluations=EvaluationService(
            evaluation_repository,
            JobEvaluationAdapter(
                evaluation_spec.commit,
                evaluation_spec.contract_version,
            ),
            checkpoints,
            CareerOpsProfileAdapter(
                workspace_root=(
                    root / "workspace" / "career-ops-profiles"
                ),
                candidate_integration_commit=candidate_spec.commit,
                career_ops_integration_commit=evaluation_spec.commit,
                forbidden_roots=(
                    root / "integrations" / "candidate-profile",
                    root / "integrations" / "job-evaluation",
                ),
            ),
        ),
        evaluation_repository=evaluation_repository,
        integrations=IntegrationManager(
            root / "integrations",
            manifest,
        ),
    )
