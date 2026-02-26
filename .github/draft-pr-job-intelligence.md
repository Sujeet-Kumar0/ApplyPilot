## Draft PR: Job Intelligence Module

**Status:** Draft - Pending Multi-Backend Merge  
**Branch:** `feature/job-intelligence` → `dev` (then to `main` after v2.0 foundation)  
**Depends on:** #XX (Multi-Backend PR)

### Summary
Introduces structured job description parsing and resume matching capabilities to enable data-driven resume tailoring decisions.

### Changes
- **New:** `src/applypilot/intelligence/` package
  - `models.py` - Data classes: `SeniorityLevel`, `JobIntelligence`, `MatchAnalysis`, `Gap`
  - `jd_parser.py` - LLM-powered job description extraction
  - `resume_matcher.py` - Gap analysis and bullet prioritization

- **New:** Test suite
  - `tests/intelligence/test_jd_parser.py` (17 tests)
  - Covers parsing, markdown JSON handling, error cases

### Key Features
1. **Job Parsing**: Extracts structured data from unstructured JDs
   - Seniority level detection (junior → principal)
   - Requirement categorization (must-have vs nice-to-have)
   - Skill extraction with proficiency levels
   - Company context (industry, stage)

2. **Resume Matching**: Analyzes fit between candidate and job
   - Overall fit score (0-10)
   - Strength identification
   - Gap analysis with severity
   - Bullet point prioritization for tailoring

### Usage Example
```python
from applypilot.intelligence.jd_parser import JobDescriptionParser
from applypilot.intelligence.resume_matcher import ResumeMatcher

parser = JobDescriptionParser()
job_intel = parser.parse({
    'title': 'Senior Python Developer',
    'company': 'TechCorp',
    'description': '...'
})

matcher = ResumeMatcher()
analysis = matcher.analyze(resume_text, job_intel)

print(f"Match score: {analysis.overall_score}")
print(f"Gaps: {[g.requirement for g in analysis.gaps]}")
```

### Testing
```bash
pytest tests/intelligence/ -v  # 17 tests
```

### Architecture
```
Job Description → JD Parser → JobIntelligence
                                     ↓
Resume Text → Resume Matcher → MatchAnalysis
                                     ↓
                            Bullet Priorities
```

### Checklist
- [x] Module implemented
- [x] Tests passing
- [x] Type hints throughout
- [x] Error handling for LLM failures
- [ ] Integration with Smart Tailoring (follow-up PR)
- [ ] Real-world testing with diverse JDs

### Notes
- Requires LLM backend (Gemini/OpenAI/Gateway) for parsing
- Graceful degradation if LLM returns malformed JSON
- Uses mocking in tests - no API calls during CI
