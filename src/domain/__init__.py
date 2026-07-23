"""Stable public domain contracts."""

from src.domain.application import ApplicationStatus
from src.domain.candidate import CandidateProfile
from src.domain.evaluation import JobEvaluation
from src.domain.job import ApplyType, Job, JobSnapshot
from src.domain.material import ApplicationPackage, MaterialArtifact

__all__ = [
    "ApplicationPackage",
    "ApplicationStatus",
    "ApplyType",
    "CandidateProfile",
    "Job",
    "JobEvaluation",
    "JobSnapshot",
    "MaterialArtifact",
]
