"""Stable public domain contracts."""

from src.domain.application import ApplicationStatus
from src.domain.candidate import (
    CandidateProfile,
    CandidateProfileProposal,
    FactEvidence,
)
from src.domain.candidate_interview import (
    OPTIONAL_INTERVIEW_DIMENSIONS,
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewAnswer,
    InterviewAnswerStatus,
    InterviewAnswers,
    InterviewDimension,
    InterviewQuestion,
)
from src.domain.evaluation import (
    EvaluationCacheKey,
    JobEvaluation,
    NativeDimension,
)
from src.domain.job import ApplyType, Job, JobSnapshot
from src.domain.material import ApplicationPackage, MaterialArtifact

__all__ = [
    "ApplicationPackage",
    "ApplicationStatus",
    "ApplyType",
    "CandidateProfile",
    "CandidateProfileProposal",
    "EvaluationCacheKey",
    "FactEvidence",
    "InterviewAnswer",
    "InterviewAnswerStatus",
    "InterviewAnswers",
    "InterviewDimension",
    "InterviewQuestion",
    "Job",
    "JobEvaluation",
    "JobSnapshot",
    "MaterialArtifact",
    "NativeDimension",
    "OPTIONAL_INTERVIEW_DIMENSIONS",
    "REQUIRED_INTERVIEW_DIMENSIONS",
]
