"""Job intelligence: structured JD parsing, resume matching, and gap analysis."""

from applypilot.intelligence.models import (
    Gap,
    JobIntelligence,
    MatchAnalysis,
    Requirement,
    SeniorityLevel,
    Skill,
)
from applypilot.intelligence.jd_parser import JobDescriptionParser
from applypilot.intelligence.resume_matcher import ResumeMatcher

__all__ = [
    "Gap",
    "JobDescriptionParser",
    "JobIntelligence",
    "MatchAnalysis",
    "Requirement",
    "ResumeMatcher",
    "SeniorityLevel",
    "Skill",
]
