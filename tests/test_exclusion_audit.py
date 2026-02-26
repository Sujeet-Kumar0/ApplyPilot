"""Tests for exclusion auditability outputs (task-11).

@file test_exclusion_audit.py
@description Validates that excluded jobs persist reason code, rule id, and
             excluded_at timestamp to the DB; that non-excluded jobs have NULL
             audit fields; and that ensure_columns migrates old DBs forward.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from applypilot.database import _ALL_COLUMNS, ensure_columns, init_db
from applypilot.scoring.scorer import (
    _exclusion_result,
    evaluate_exclusion,
    run_scoring,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_job(
    conn: sqlite3.Connection,
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
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Fresh test database via init_db (includes new audit columns)."""
    db_path = tmp_path / "audit_test.db"
    conn = init_db(db_path)
    return conn


@pytest.fixture
def mock_resume(tmp_path: Path) -> Path:
    """Fake resume file for scoring."""
    resume = tmp_path / "resume.txt"
    resume.write_text("Experienced software engineer with Python and React skills.")
    return resume


# ---------------------------------------------------------------------------
# 1. Schema: new columns present in fresh DB
# ---------------------------------------------------------------------------


class TestSchemaAuditColumns:
    """Verify audit columns exist in the schema."""

    def test_audit_columns_in_all_columns_registry(self):
        """_ALL_COLUMNS contains exclusion audit fields."""
        assert "exclusion_reason_code" in _ALL_COLUMNS
        assert "exclusion_rule_id" in _ALL_COLUMNS
        assert "excluded_at" in _ALL_COLUMNS

    def test_fresh_db_has_audit_columns(self, test_db: sqlite3.Connection):
        """A freshly created DB has the audit columns."""
        cols = {row[1] for row in test_db.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "exclusion_reason_code" in cols
        assert "exclusion_rule_id" in cols
        assert "excluded_at" in cols


# ---------------------------------------------------------------------------
# 2. Migration: ensure_columns adds audit columns to old DBs
# ---------------------------------------------------------------------------


class TestMigrationAddsAuditColumns:
    """Simulate an old DB missing audit columns and verify migration."""

    def test_ensure_columns_adds_missing_audit_cols(self, tmp_path: Path):
        """Old DB without audit columns gets them added by ensure_columns."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE jobs ("
            "  url TEXT PRIMARY KEY,"
            "  title TEXT,"
            "  fit_score INTEGER,"
            "  score_reasoning TEXT,"
            "  scored_at TEXT"
            ")"
        )
        conn.commit()

        # Confirm audit columns are missing
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "exclusion_reason_code" not in cols_before

        # Run migration
        added = ensure_columns(conn)

        # Audit columns should be among those added
        assert "exclusion_reason_code" in added
        assert "exclusion_rule_id" in added
        assert "excluded_at" in added

        # Confirm they're now in the schema
        cols_after = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "exclusion_reason_code" in cols_after
        assert "exclusion_rule_id" in cols_after
        assert "excluded_at" in cols_after

        conn.close()


# ---------------------------------------------------------------------------
# 3. Unit: _exclusion_result returns audit metadata
# ---------------------------------------------------------------------------


class TestExclusionResultAuditFields:
    """_exclusion_result dict includes audit keys."""

    def test_result_contains_reason_code(self):
        rule = {"id": "r-001", "reason_code": "excluded_keyword"}
        result = _exclusion_result(rule, "intern")
        assert result["exclusion_reason_code"] == "excluded_keyword"

    def test_result_contains_rule_id(self):
        rule = {"id": "r-042", "reason_code": "excluded_sector"}
        result = _exclusion_result(rule, "finance")
        assert result["exclusion_rule_id"] == "r-042"

    def test_non_excluded_job_has_no_audit_keys(self):
        """evaluate_exclusion returns None => no audit keys to persist."""
        job = {
            "title": "Software Engineer",
            "site": "acme",
            "full_description": "Build APIs.",
        }
        assert evaluate_exclusion(job) is None


# ---------------------------------------------------------------------------
# 4. Integration: excluded job persists audit fields in DB
# ---------------------------------------------------------------------------


class TestExcludedJobPersistsAudit:
    """run_scoring writes audit columns for excluded jobs."""

    def test_excluded_job_has_reason_code_in_db(self, test_db: sqlite3.Connection, mock_resume: Path, monkeypatch):
        """An excluded job (intern) gets exclusion_reason_code written."""
        _insert_job(test_db, "https://ex.com/intern1", "Summer Intern - Engineering")

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        with patch("applypilot.scoring.scorer.score_job"):
            run_scoring()

        row = test_db.execute(
            "SELECT exclusion_reason_code, exclusion_rule_id, excluded_at FROM jobs WHERE url = ?",
            ("https://ex.com/intern1",),
        ).fetchone()

        assert row[0] == "excluded_keyword"
        assert row[1] == "r-001"
        assert row[2] is not None  # excluded_at timestamp set

    def test_excluded_by_clearance_has_audit_fields(self, test_db: sqlite3.Connection, mock_resume: Path, monkeypatch):
        """Clearance exclusion (r-002) writes correct audit fields."""
        _insert_job(
            test_db,
            "https://ex.com/cleared1",
            "Cloud Engineer",
            full_description="Must have active clearance.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        with patch("applypilot.scoring.scorer.score_job"):
            run_scoring()

        row = test_db.execute(
            "SELECT exclusion_reason_code, exclusion_rule_id, excluded_at FROM jobs WHERE url = ?",
            ("https://ex.com/cleared1",),
        ).fetchone()

        assert row[0] == "excluded_keyword"
        assert row[1] == "r-002"
        assert row[2] is not None

    def test_audit_fields_queryable(self, test_db: sqlite3.Connection, mock_resume: Path, monkeypatch):
        """Audit columns are queryable with WHERE clauses."""
        _insert_job(test_db, "https://ex.com/intern2", "Intern - Backend")
        _insert_job(test_db, "https://ex.com/normal1", "Staff Engineer", full_description="Build distributed systems.")

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 9, "keywords": "python", "reasoning": "Great fit"})
        with patch("applypilot.scoring.scorer.score_job", mock_score):
            run_scoring()

        # Query excluded jobs only
        excluded_rows = test_db.execute("SELECT url FROM jobs WHERE exclusion_reason_code IS NOT NULL").fetchall()
        excluded_urls = [r[0] for r in excluded_rows]
        assert "https://ex.com/intern2" in excluded_urls
        assert "https://ex.com/normal1" not in excluded_urls


# ---------------------------------------------------------------------------
# 5. Non-excluded jobs do NOT get false exclusion metadata
# ---------------------------------------------------------------------------


class TestNonExcludedJobNoAudit:
    """Normal (non-excluded) jobs must have NULL audit fields."""

    def test_non_excluded_job_has_null_audit_fields(self, test_db: sqlite3.Connection, mock_resume: Path, monkeypatch):
        """A normal job scored via LLM should have NULL exclusion columns."""
        _insert_job(
            test_db,
            "https://ex.com/normal2",
            "Senior Backend Engineer",
            full_description="Build scalable microservices with Python.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 8, "keywords": "python,api", "reasoning": "Good fit"})
        with patch("applypilot.scoring.scorer.score_job", mock_score):
            run_scoring()

        row = test_db.execute(
            "SELECT exclusion_reason_code, exclusion_rule_id, excluded_at FROM jobs WHERE url = ?",
            ("https://ex.com/normal2",),
        ).fetchone()

        assert row[0] is None  # no reason code
        assert row[1] is None  # no rule id
        assert row[2] is None  # no excluded_at

    def test_mixed_batch_audit_field_correctness(self, test_db: sqlite3.Connection, mock_resume: Path, monkeypatch):
        """In a mixed batch, only excluded jobs have audit fields populated."""
        _insert_job(test_db, "https://ex.com/intern3", "QA Intern")
        _insert_job(
            test_db,
            "https://ex.com/normal3",
            "DevOps Engineer",
            full_description="Manage Kubernetes clusters.",
        )

        monkeypatch.setattr("applypilot.scoring.scorer.RESUME_PATH", mock_resume)
        monkeypatch.setattr("applypilot.scoring.scorer.get_connection", lambda: test_db)

        mock_score = MagicMock(return_value={"score": 7, "keywords": "k8s", "reasoning": "Good fit"})
        with patch("applypilot.scoring.scorer.score_job", mock_score):
            result = run_scoring()

        assert result["excluded"] == 1
        assert result["scored"] == 2

        # Excluded job has audit fields
        intern_row = test_db.execute(
            "SELECT exclusion_reason_code, exclusion_rule_id FROM jobs WHERE url = ?",
            ("https://ex.com/intern3",),
        ).fetchone()
        assert intern_row[0] == "excluded_keyword"
        assert intern_row[1] == "r-001"

        # Normal job has NULL audit fields
        normal_row = test_db.execute(
            "SELECT exclusion_reason_code, exclusion_rule_id, excluded_at FROM jobs WHERE url = ?",
            ("https://ex.com/normal3",),
        ).fetchone()
        assert normal_row[0] is None
        assert normal_row[1] is None
        assert normal_row[2] is None
