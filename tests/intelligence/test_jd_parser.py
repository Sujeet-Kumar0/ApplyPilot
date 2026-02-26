"""Tests for job description parser and intelligence models."""

import json
from unittest.mock import MagicMock, patch

import pytest

from applypilot.intelligence.models import (
    Gap,
    JobIntelligence,
    MatchAnalysis,
    Requirement,
    SeniorityLevel,
    Skill,
)


SAMPLE_JD_LLM_RESPONSE = json.dumps(
    {
        "seniority": "senior",
        "requirements": [
            {
                "text": "5+ years Python experience",
                "type": "must_have",
                "category": "experience",
            },
            {
                "text": "FastAPI experience",
                "type": "must_have",
                "category": "technical",
            },
            {
                "text": "AWS certification",
                "type": "nice_to_have",
                "category": "education",
            },
        ],
        "skills": [
            {"name": "Python", "required": True, "proficiency": "expert"},
            {"name": "FastAPI", "required": True, "proficiency": "proficient"},
            {"name": "Docker", "required": False, "proficiency": "familiar"},
        ],
        "key_responsibilities": [
            "Design and build backend services",
            "Mentor junior developers",
        ],
        "red_flags": [],
        "company_context": {"industry": "fintech", "stage": "growth"},
    }
)

SAMPLE_MATCH_LLM_RESPONSE = json.dumps(
    {
        "overall_score": 8.2,
        "strengths": ["Strong Python background", "Relevant FastAPI experience"],
        "gaps": [
            {
                "requirement": "AWS certification",
                "severity": "minor",
                "suggestion": "Consider obtaining AWS Solutions Architect cert",
            }
        ],
        "recommendations": [
            "Emphasize backend service design experience",
            "Highlight mentoring experience",
        ],
        "bullet_priorities": {"Built microservices": 9, "Led team of 5": 7},
    }
)


class TestSeniorityLevel:
    def test_all_levels_exist(self):
        assert SeniorityLevel.JUNIOR.value == "junior"
        assert SeniorityLevel.MID.value == "mid"
        assert SeniorityLevel.SENIOR.value == "senior"
        assert SeniorityLevel.STAFF.value == "staff"
        assert SeniorityLevel.PRINCIPAL.value == "principal"

    def test_from_string(self):
        assert SeniorityLevel("senior") == SeniorityLevel.SENIOR


class TestModels:
    def test_requirement_creation(self):
        req = Requirement(text="5+ years Python", type="must_have", category="experience")
        assert req.text == "5+ years Python"
        assert req.type == "must_have"
        assert req.category == "experience"

    def test_skill_creation(self):
        skill = Skill(name="Python", required=True, proficiency="expert")
        assert skill.name == "Python"
        assert skill.required is True

    def test_skill_optional_proficiency(self):
        skill = Skill(name="Go", required=False, proficiency=None)
        assert skill.proficiency is None

    def test_job_intelligence_creation(self):
        intel = JobIntelligence(
            title="Senior Python Developer",
            company="TechCorp",
            seniority=SeniorityLevel.SENIOR,
            requirements=[Requirement(text="Python", type="must_have", category="technical")],
            skills=[Skill(name="Python", required=True, proficiency="expert")],
            key_responsibilities=["Build APIs"],
            red_flags=[],
            company_context={"industry": "tech"},
        )
        assert intel.title == "Senior Python Developer"
        assert intel.seniority == SeniorityLevel.SENIOR

    def test_gap_creation(self):
        gap = Gap(requirement="AWS cert", severity="minor", suggestion="Get certified")
        assert gap.severity == "minor"

    def test_match_analysis_defaults(self):
        analysis = MatchAnalysis(
            overall_score=7.5,
            strengths=["Strong Python"],
            gaps=[],
            recommendations=["Add metrics"],
        )
        assert analysis.bullet_priorities == {}

    def test_match_analysis_with_priorities(self):
        analysis = MatchAnalysis(
            overall_score=8.0,
            strengths=[],
            gaps=[],
            recommendations=[],
            bullet_priorities={"bullet1": 10},
        )
        assert analysis.bullet_priorities["bullet1"] == 10


class TestJobDescriptionParser:
    @patch("applypilot.intelligence.jd_parser.get_client")
    def test_parse_senior_python_job(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ask.return_value = SAMPLE_JD_LLM_RESPONSE
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.jd_parser import JobDescriptionParser

        parser = JobDescriptionParser()
        job = {
            "title": "Senior Python Developer",
            "company": "TechCorp",
            "description": "Senior Python Developer. Requirements: 5+ years Python, FastAPI experience",
        }

        intel = parser.parse(job)

        assert intel.title == "Senior Python Developer"
        assert intel.company == "TechCorp"
        assert intel.seniority == SeniorityLevel.SENIOR
        assert len(intel.requirements) == 3
        assert len(intel.skills) == 3
        assert len(intel.key_responsibilities) == 2
        assert intel.company_context["industry"] == "fintech"

    @patch("applypilot.intelligence.jd_parser.get_client")
    def test_parse_handles_markdown_fenced_json(self, mock_get_client):
        fenced_response = f"Here is the analysis:\n```json\n{SAMPLE_JD_LLM_RESPONSE}\n```\n"
        mock_client = MagicMock()
        mock_client.ask.return_value = fenced_response
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.jd_parser import JobDescriptionParser

        parser = JobDescriptionParser()
        job = {
            "title": "Developer",
            "company": "Corp",
            "description": "A job description",
        }

        intel = parser.parse(job)
        assert intel.seniority == SeniorityLevel.SENIOR
        assert len(intel.requirements) == 3

    @patch("applypilot.intelligence.jd_parser.get_client")
    def test_parse_raises_on_empty_description(self, mock_get_client):
        mock_get_client.return_value = MagicMock()

        from applypilot.intelligence.jd_parser import JobDescriptionParser

        parser = JobDescriptionParser()

        with pytest.raises(ValueError, match="non-empty 'description'"):
            parser.parse({"title": "Dev", "company": "Corp", "description": ""})

    @patch("applypilot.intelligence.jd_parser.get_client")
    def test_parse_raises_on_unparseable_response(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ask.return_value = "This is not JSON at all, no braces here."
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.jd_parser import JobDescriptionParser

        parser = JobDescriptionParser()

        with pytest.raises(ValueError, match="Could not parse JSON"):
            parser.parse({"title": "Dev", "company": "Corp", "description": "A job"})

    @patch("applypilot.intelligence.jd_parser.get_client")
    def test_parse_defaults_missing_fields(self, mock_get_client):
        minimal_response = json.dumps({"seniority": "junior"})
        mock_client = MagicMock()
        mock_client.ask.return_value = minimal_response
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.jd_parser import JobDescriptionParser

        parser = JobDescriptionParser()
        intel = parser.parse({"description": "Some job"})

        assert intel.title == "Unknown"
        assert intel.company == "Unknown"
        assert intel.seniority == SeniorityLevel.JUNIOR
        assert intel.requirements == []
        assert intel.skills == []


class TestResumeMatcher:
    @patch("applypilot.intelligence.resume_matcher.get_client")
    def test_analyze_returns_match_analysis(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ask.return_value = SAMPLE_MATCH_LLM_RESPONSE
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.resume_matcher import ResumeMatcher

        matcher = ResumeMatcher()
        job_intel = JobIntelligence(
            title="Senior Python Developer",
            company="TechCorp",
            seniority=SeniorityLevel.SENIOR,
            requirements=[
                Requirement(text="5+ years Python", type="must_have", category="experience"),
                Requirement(text="FastAPI", type="must_have", category="technical"),
            ],
            skills=[],
            key_responsibilities=[],
            red_flags=[],
            company_context={},
        )

        result = matcher.analyze("Experienced Python developer with 7 years...", job_intel)

        assert isinstance(result, MatchAnalysis)
        assert result.overall_score == 8.2
        assert len(result.strengths) == 2
        assert len(result.gaps) == 1
        assert result.gaps[0].severity == "minor"
        assert len(result.recommendations) == 2
        assert result.bullet_priorities["Built microservices"] == 9

    @patch("applypilot.intelligence.resume_matcher.get_client")
    def test_analyze_handles_empty_requirements(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ask.return_value = SAMPLE_MATCH_LLM_RESPONSE
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.resume_matcher import ResumeMatcher

        matcher = ResumeMatcher()
        job_intel = JobIntelligence(
            title="Developer",
            company="Corp",
            seniority=SeniorityLevel.MID,
            requirements=[],
            skills=[],
            key_responsibilities=[],
            red_flags=[],
            company_context={},
        )

        result = matcher.analyze("My resume text", job_intel)
        assert isinstance(result, MatchAnalysis)
        call_args = mock_client.ask.call_args[0][0]
        assert "Title: Developer" in call_args

    @patch("applypilot.intelligence.resume_matcher.get_client")
    def test_analyze_truncates_long_resume(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.ask.return_value = SAMPLE_MATCH_LLM_RESPONSE
        mock_get_client.return_value = mock_client

        from applypilot.intelligence.resume_matcher import ResumeMatcher

        matcher = ResumeMatcher()
        long_resume = "x" * 10000
        job_intel = JobIntelligence(
            title="Dev",
            company="Corp",
            seniority=SeniorityLevel.MID,
            requirements=[Requirement(text="Python", type="must_have", category="technical")],
            skills=[],
            key_responsibilities=[],
            red_flags=[],
            company_context={},
        )

        matcher.analyze(long_resume, job_intel)
        call_args = mock_client.ask.call_args[0][0]
        assert len(call_args) < 10000
