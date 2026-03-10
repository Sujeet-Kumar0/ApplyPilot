"""Domain models for job intelligence analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SeniorityLevel(Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"


@dataclass
class Requirement:
    text: str
    type: str  # must_have | nice_to_have
    category: str  # technical | experience | education


@dataclass
class Skill:
    name: str
    required: bool
    proficiency: Optional[str]  # expert | proficient | familiar | None


@dataclass
class JobIntelligence:
    title: str
    company: str
    seniority: SeniorityLevel
    requirements: List[Requirement]
    skills: List[Skill]
    key_responsibilities: List[str]
    red_flags: List[str]
    company_context: Dict[str, str]


@dataclass
class Gap:
    requirement: str
    severity: str  # critical | major | minor
    suggestion: str


@dataclass
class MatchAnalysis:
    overall_score: float
    strengths: List[str]
    gaps: List[Gap]
    recommendations: List[str]
    bullet_priorities: Dict[str, int] = field(default_factory=dict)
