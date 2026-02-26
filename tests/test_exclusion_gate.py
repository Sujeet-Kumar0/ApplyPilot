"""Tests for deterministic pre-score exclusion gate.

@file test_exclusion_gate.py
@description Validates that the exclusion gate correctly blocks jobs before
             LLM scoring, bypasses the LLM call for excluded jobs, and ensures
             excluded jobs cannot satisfy pending-tailor threshold.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from applypilot.scoring.scorer import (
    EXCLUSION_RULES,
    _tokenize,
    evaluate_exclusion,
    run_scoring,
)
from applypilot.database import get_jobs_by_stage, init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_job(
    conn,
    url: str,
    title: str,
    site: str = "testco",
    full_description: str = "Some job description.",
) -> None:
    """Insert a minimal test job into the database."""
    conn.execute(
        "INSERT INTO jobs (url, title, site, full_description, discovered_at) VALUES (?, ?, ?, ?, ?)",
        (url, title, site, full_description, "2026-01-01T00:00:00Z"),
    )
    conn.commit()


@pytest.fixture
def test_db(tmp_path):
    """Fresh test database via init_db."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    return conn


@pytest.fixture
def mock_resume(tmp_path):
    """Fake resume file for scoring."""
    resume = tmp_path / "resume.txt"
    resume.write_text("Experienced software engineer with Python and React skills.")
    return resume


# ---------------------------------------------------------------------------
# Unit: _tokenize
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_basic_words(self):
        assert _tokenize("Senior Engineer") == ["senior", "engineer"]

    def test_punctuation_split(self):
        tokens = _tokenize("full-time, on-site")
        assert "full" in tokens and "time" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_mixed_case_normalized(self):
        assert _tokenize("INTERN at Google") == ["intern", "at", "google"]

    def test_numbers_preserved(self):
        tokens = _tokenize("Python3 or py3.11")
        assert "python3" in tokens
        assert "py3" in tokens


# ---------------------------------------------------------------------------
# Unit: evaluate_exclusion
# ---------------------------------------------------------------------------


class TestEvaluateExclusion:
    """Direct tests of the evaluate_exclusion function."""

    def test_non_excluded_job_returns_none(self):
        job = {
            "title": "Software Engineer",
            "site": "acme_corp",
            "full_description": "Build great software with Python and React.",
        }
        assert evaluate_exclusion(job) is None

    def test_excluded_by_title_keyword_intern(self):
        job = {
            "title": "Summer Intern - Engineering",
            "site": "bigco",
            "full_description": "Great opportunity to learn.",
        }
        result = evaluate_exclusion(job)
        assert result is not None
        assert result["score"] == 0
        assert "EXCLUDED:" in result["reasoning"]
        assert "excluded_keyword" in result["reasoning"]

    def test_excluded_by_title_keyword_internship(self):
        job = {
            "title": "Software Engineering Internship",
            "site": "bigco",
            "full_description": "Great opportunity to learn.",
        }
        result = evaluate_exclusion(job)
        assert result is not None
        assert result["score"] == 0

    def test_excluded_by_description_keyword_clearance(self):
        """Keyword 'clearance' in description triggers exclusion (r-002 scope: title+description)."""
        job = {
            "title": "Systems Administrator",
            "site": "govtech",
            "full_description": "Must hold active TS/SCI clearance to apply.",
        }
        result = evaluate_exclusion(job)
        assert result is not None
        assert result["score"] == 0
        assert "EXCLUDED:" in result["reasoning"]

    def test_case_insensitive_matching(self):
        job = {
            "title": "INTERNSHIP Program",
            "site": "startupco",
            "full_description": "Join our team.",
        }
        result = evaluate_exclusion(job)
        assert result is not None
        assert result["score"] == 0

    def test_partial_word_not_triggered(self):
        """'international' should NOT match 'intern' (exact token match)."""
        job = {
            "title": "International Sales Manager",
            "site": "globocorp",
            "full_description": "Manage international accounts.",
        }
        assert evaluate_exclusion(job) is None

    def test_clearances_plural_not_triggered(self):
        """'clearances' should NOT match 'clearance' (exact token match)."""
        job = {
            "title": "Compliance Officer",
            "site": "bankco",
            "full_description": "Handle various clearances and permits.",
        }
        assert evaluate_exclusion(job) is None

    def test_exclusion_result_format(self):
        job = {"title": "Intern", "site": "co", "full_description": ""}
        result = evaluate_exclusion(job)
        assert result is not None
        assert result["score"] == 0
        assert result["keywords"] == ""
        assert result["reasoning"].startswith("EXCLUDED:")

    def test_none_fields_handled_gracefully(self):
        job = {"title": None, "site": None, "full_description": None}
        assert evaluate_exclusion(job) is None

    def test_missing_fields_handled_gracefully(self):
        job = {}
        assert evaluate_exclusion(job) is None

    def test_exclusion_rules_exist(self):
        """Sanity: at least one exclusion rule is defined."""
        assert len(EXCLUSION_RULES) > 0
        for rule in EXCLUSION_RULES:
            assert "id" in rule
            assert "value" in rule
            assert "reason_code" in rule


# ---------------------------------------------------------------------------
# Integration: exclusion gate in run_scoring bypasses LLM
# ---------------------------------------------------------------------------


class TestExclusionInRunScoring:
    """Prove excluded jobs skip LLM and non-excluded use normal path."""

    def test_non_excluded_job_calls_score_job(self, test_db, mock_resume, monkeypatch):
        """Normal job goes through LLM scoring path."""
        _insert_job(
            test_db,
            "https://example.com/1",
            "Software Engineer",
            full_description="Python developer needed.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 8, "keywords": "python", "reasoning": "Strong match"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            result = run_scoring()

        assert mock_score.call_count == 1
        assert result["scored"] == 1
        assert result["excluded"] == 0

    def test_excluded_job_bypasses_llm(self, test_db, mock_resume, monkeypatch):
        """Excluded job (intern) should NOT call score_job at all."""
        _insert_job(
            test_db,
            "https://example.com/2",
            "Summer Intern - Data Science",
            full_description="Learn ML.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 8, "keywords": "", "reasoning": "test"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            result = run_scoring()

        # LLM was never called
        assert mock_score.call_count == 0
        assert result["scored"] == 1
        assert result["excluded"] == 1

        # Verify DB has score=0 with EXCLUDED marker
        row = test_db.execute(
            "SELECT fit_score, score_reasoning FROM jobs WHERE url = ?",
            ("https://example.com/2",),
        ).fetchone()
        assert row[0] == 0
        assert "EXCLUDED:" in row[1]

    def test_mixed_excluded_and_normal(self, test_db, mock_resume, monkeypatch):
        """Mix of excluded and normal jobs: LLM called only for non-excluded."""
        _insert_job(
            test_db,
            "https://example.com/3",
            "Intern - QA",
            full_description="QA intern role.",
        )
        _insert_job(
            test_db,
            "https://example.com/4",
            "Backend Engineer",
            full_description="Build APIs with Python.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 9, "keywords": "api,python", "reasoning": "Great fit"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            result = run_scoring()

        # LLM called only for the non-excluded job
        assert mock_score.call_count == 1
        assert result["scored"] == 2
        assert result["excluded"] == 1

    def test_excluded_job_by_description_clearance(self, test_db, mock_resume, monkeypatch):
        """Job with 'clearance' in description excluded without LLM call."""
        _insert_job(
            test_db,
            "https://example.com/5",
            "Cloud Engineer",
            full_description="Must have active security clearance.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 7, "keywords": "", "reasoning": "test"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            result = run_scoring()

        assert mock_score.call_count == 0
        assert result["excluded"] == 1


# ---------------------------------------------------------------------------
# Integration: excluded score cannot satisfy pending_tailor threshold
# ---------------------------------------------------------------------------


class TestExclusionBlocksTailoring:
    """Excluded jobs must not appear in pending_tailor stage."""

    def test_excluded_job_not_in_pending_tailor(self, test_db, mock_resume, monkeypatch):
        """Score=0 from exclusion must not satisfy fit_score >= 7 threshold."""
        _insert_job(
            test_db,
            "https://example.com/10",
            "Summer Intern",
            full_description="Great learning experience.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        with patch("applypilot.scoring.scorer.score_job"):
            run_scoring()

        # Query pending_tailor: excluded job should NOT appear
        pending = get_jobs_by_stage(conn=test_db, stage="pending_tailor")
        urls = [j["url"] for j in pending]
        assert "https://example.com/10" not in urls

    def test_normal_high_score_does_appear_in_pending_tailor(self, test_db, mock_resume, monkeypatch):
        """Non-excluded job with score >= 7 appears in pending_tailor."""
        _insert_job(
            test_db,
            "https://example.com/11",
            "Senior Engineer",
            full_description="Build distributed systems.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 9, "keywords": "python", "reasoning": "Perfect fit"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            run_scoring()

        pending = get_jobs_by_stage(conn=test_db, stage="pending_tailor")
        urls = [j["url"] for j in pending]
        assert "https://example.com/11" in urls

    def test_excluded_and_normal_only_normal_in_pending_tailor(self, test_db, mock_resume, monkeypatch):
        """In a mixed batch, only non-excluded high-score jobs reach pending_tailor."""
        _insert_job(
            test_db,
            "https://example.com/20",
            "Intern - Backend",
            full_description="Learn backend development.",
        )
        _insert_job(
            test_db,
            "https://example.com/21",
            "Staff Engineer",
            full_description="Lead architecture decisions.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 8, "keywords": "architecture", "reasoning": "Strong fit"})

        with patch("applypilot.scoring.scorer.score_job", mock_score):
            run_scoring()

        pending = get_jobs_by_stage(conn=test_db, stage="pending_tailor")
        urls = [j["url"] for j in pending]
        assert "https://example.com/20" not in urls  # excluded
        assert "https://example.com/21" in urls  # not excluded, score=8
