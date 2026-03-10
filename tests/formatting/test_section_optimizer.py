import pytest
from applypilot.formatting.section_optimizer import SectionOrderOptimizer
from applypilot.formatting.templates import ModernTemplate, TemplateEngine
from applypilot.intelligence.models import (
    Gap,
    JobIntelligence,
    MatchAnalysis,
    SeniorityLevel,
)


def _make_job_intel(title: str = "Senior Software Engineer") -> JobIntelligence:
    return JobIntelligence(
        title=title,
        company="Acme Corp",
        seniority=SeniorityLevel.SENIOR,
        requirements=[],
        skills=[],
        key_responsibilities=[],
        red_flags=[],
        company_context={},
    )


def _make_match_analysis(gaps: list[Gap] | None = None) -> MatchAnalysis:
    return MatchAnalysis(
        overall_score=0.85,
        strengths=["Python", "AWS"],
        gaps=gaps or [],
        recommendations=[],
        bullet_priorities={},
    )


class TestSectionOrderOptimizer:
    def setup_method(self):
        self.optimizer = SectionOrderOptimizer()

    def test_default_order_for_generic_title(self):
        job = _make_job_intel("Senior Software Engineer")
        match = _make_match_analysis()
        result = self.optimizer.optimize(job, match)
        assert result == SectionOrderOptimizer.DEFAULT_ORDER

    def test_technical_role_detection(self):
        for title in ["Staff Engineer", "Principal Engineer", "Solutions Architect"]:
            job = _make_job_intel(title)
            role = self.optimizer._detect_role_type(job)
            assert role == "technical", f"Expected 'technical' for '{title}', got '{role}'"

    def test_executive_role_detection(self):
        for title in ["CTO", "VP of Engineering", "Director of Product"]:
            job = _make_job_intel(title)
            role = self.optimizer._detect_role_type(job)
            assert role == "executive", f"Expected 'executive' for '{title}', got '{role}'"

    def test_academic_role_detection(self):
        for title in ["PhD Researcher", "Research Scientist"]:
            job = _make_job_intel(title)
            role = self.optimizer._detect_role_type(job)
            assert role == "academic", f"Expected 'academic' for '{title}', got '{role}'"

    def test_executive_order(self):
        job = _make_job_intel("VP of Engineering")
        match = _make_match_analysis()
        result = self.optimizer.optimize(job, match)
        assert result == ["HEADER", "SUMMARY", "EXPERIENCE", "SKILLS", "EDUCATION"]

    def test_academic_order(self):
        job = _make_job_intel("Research Scientist")
        match = _make_match_analysis()
        result = self.optimizer.optimize(job, match)
        assert result == ["HEADER", "EDUCATION", "RESEARCH", "PUBLICATIONS", "EXPERIENCE"]

    def test_education_gap_moves_education_up(self):
        gaps = [
            Gap(
                requirement="Bachelor's degree in CS or education equivalent",
                severity="high",
                suggestion="Highlight relevant coursework",
            )
        ]
        job = _make_job_intel("Senior Software Engineer")
        match = _make_match_analysis(gaps=gaps)
        result = self.optimizer.optimize(job, match)
        edu_idx = result.index("EDUCATION")
        assert edu_idx == 2, f"EDUCATION should be at index 2, got {edu_idx}"

    def test_education_gap_with_no_education_keyword(self):
        gaps = [Gap(requirement="5 years experience", severity="medium", suggestion="Emphasize projects")]
        job = _make_job_intel("Senior Software Engineer")
        match = _make_match_analysis(gaps=gaps)
        result = self.optimizer.optimize(job, match)
        assert result == SectionOrderOptimizer.DEFAULT_ORDER

    def test_move_up_with_missing_section(self):
        order = ["HEADER", "SUMMARY", "SKILLS"]
        result = self.optimizer._move_up(order, "NONEXISTENT")
        assert result == ["HEADER", "SUMMARY", "SKILLS"]

    def test_optimize_returns_copy(self):
        job = _make_job_intel("Senior Software Engineer")
        match = _make_match_analysis()
        result = self.optimizer.optimize(job, match)
        result.append("EXTRA")
        assert "EXTRA" not in SectionOrderOptimizer.ROLE_ORDERS["technical"]


class TestModernTemplate:
    def test_renders_name_uppercase(self):
        template = ModernTemplate()
        result = template.render_txt({"name": "John Doe", "section_order": []})
        assert "JOHN DOE" in result

    def test_renders_contact_info(self):
        template = ModernTemplate()
        data = {"name": "Jane", "email": "j@x.com", "phone": "555-1234", "section_order": []}
        result = template.render_txt(data)
        assert "j@x.com" in result
        assert "555-1234" in result

    def test_renders_summary_section(self):
        template = ModernTemplate()
        data = {"name": "Test", "summary": "Experienced dev", "section_order": ["SUMMARY"]}
        result = template.render_txt(data)
        assert "PROFESSIONAL SUMMARY" in result
        assert "Experienced dev" in result

    def test_renders_skills_section(self):
        template = ModernTemplate()
        data = {"name": "Test", "skills": {"Languages": ["Python", "Go"]}, "section_order": ["SKILLS"]}
        result = template.render_txt(data)
        assert "TECHNICAL SKILLS" in result
        assert "Python, Go" in result

    def test_renders_experience_section(self):
        template = ModernTemplate()
        data = {
            "name": "Test",
            "experience": [{"title": "SWE", "company": "Acme", "dates": "2020-2023", "bullets": ["Built APIs"]}],
            "section_order": ["EXPERIENCE"],
        }
        result = template.render_txt(data)
        assert "SWE | Acme | 2020-2023" in result
        assert "Built APIs" in result


class TestTemplateEngine:
    def test_default_template_is_modern(self):
        engine = TemplateEngine()
        result = engine.render({"name": "Test", "section_order": []})
        assert "TEST" in result

    def test_unknown_template_falls_back_to_modern(self):
        engine = TemplateEngine()
        result = engine.render({"name": "Test", "section_order": []}, template_name="nonexistent")
        assert "TEST" in result
