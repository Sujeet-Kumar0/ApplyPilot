"""Domain models for smart resume tailoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Bullet:
    """A resume bullet point stored in the bullet bank."""

    id: str
    text: str
    context: Dict[str, Any]
    tags: List[str]
    metrics: List[str]
    created_at: datetime
    use_count: int = 0
    success_rate: float = 0.0


@dataclass
class BulletVariant:
    """A generated variant of a bullet tailored for a specific job."""

    original_bullet_id: str
    text: str
    strategy: str
    score: Optional[float] = None


@dataclass
class GateResult:
    """Result from a quality gate check."""

    passed: bool
    score: float
    feedback: str
    retry_prompt: Optional[str] = None


@dataclass
class Resume:
    """A resume with raw text and structured sections."""

    text: str
    sections: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TailoringResult:
    """Final result of the smart tailoring process."""

    resume: Resume
    score: float
    iterations: int
    quality_results: List[GateResult] = field(default_factory=list)
