"""Stable public domain contracts."""

from src.domain.application import ApplicationStatus
from src.domain.candidate import (
    CandidateProfile,
    CandidateProfileProposal,
    FactEvidence,
)
from src.domain.candidate_cv import (
    CandidateCv,
    CandidateEducation,
    CandidateExperience,
    IntentSynthesis,
    IntentTargetField,
    SourcedText,
)
from src.domain.candidate_interview import (
    OPTIONAL_INTERVIEW_DIMENSIONS,
    REQUIRED_INTERVIEW_DIMENSIONS,
    InterviewAnswer,
    InterviewAnswers,
    InterviewAnswerStatus,
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
    "CandidateCv",
    "CandidateEducation",
    "CandidateExperience",
    "EvaluationCacheKey",
    "FactEvidence",
    "InterviewAnswer",
    "InterviewAnswerStatus",
    "InterviewAnswers",
    "InterviewDimension",
    "InterviewQuestion",
    "IntentSynthesis",
    "IntentTargetField",
    "Job",
    "JobEvaluation",
    "JobSnapshot",
    "MaterialArtifact",
    "NativeDimension",
    "OPTIONAL_INTERVIEW_DIMENSIONS",
    "REQUIRED_INTERVIEW_DIMENSIONS",
    "SourcedText",
]
