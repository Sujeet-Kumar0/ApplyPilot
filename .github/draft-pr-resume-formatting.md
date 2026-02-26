## Draft PR: Resume Formatting Module

**Status:** Draft - Pending Multi-Backend Merge  
**Branch:** `feature/resume-formatting` → `dev` (then to `main` after v2.0 foundation)  
**Depends on:** #XX (Job Intelligence PR)

### Summary
Adds resume layout optimization and template rendering to present tailored content in job-specific formats.

### Changes
- **New:** `src/applypilot/formatting/` package
  - `section_optimizer.py` - Role-based section ordering
  - `templates.py` - Template engine with ModernTemplate

- **New:** Test suite
  - `tests/formatting/test_section_optimizer.py` (17 tests)
  - Covers role detection, gap handling, template rendering

### Key Features
1. **Section Order Optimization**
   - Detects role type (technical/executive/academic)
   - Reorders sections based on job requirements
   - Elevates education if degree gap identified
   - Default: `HEADER → SUMMARY → SKILLS → EXPERIENCE → PROJECTS → EDUCATION`

2. **Template Engine**
   - Abstract `Template` base class
   - `ModernTemplate` with clean text output
   - Section-aware rendering
   - Skills categorized display

### Role Detection
```python
"Staff Engineer" → technical  → [SKILLS early]
"VP Engineering" → executive  → [EXPERIENCE early]
"PhD Researcher" → academic   → [EDUCATION first]
```

### Usage Example
```python
from applypilot.formatting.section_optimizer import SectionOrderOptimizer
from applypilot.formatting.templates import ModernTemplate

optimizer = SectionOrderOptimizer()
order = optimizer.optimize(job_intel, match_analysis)
# ['HEADER', 'SUMMARY', 'SKILLS', 'EXPERIENCE', ...]

template = ModernTemplate()
resume_text = template.render_txt({
    'name': 'Jane Doe',
    'section_order': order,
    'experience': [...],
    'skills': {...}
})
```

### Testing
```bash
pytest tests/formatting/ -v  # 17 tests
```

### Architecture
```
JobIntel + MatchAnalysis → SectionOrderOptimizer → Section Order
                                                         ↓
Resume Data + Template → ModernTemplate → Formatted Resume
```

### Checklist
- [x] Section optimizer implemented
- [x] Modern template implemented
- [x] Tests passing
- [x] Role detection working
- [ ] Additional templates (minimal, creative)
- [ ] PDF output support (future)

### Integration
Works with Job Intelligence output to make layout decisions based on:
- Job seniority level
- Identified gaps (education boost)
- Role type detection
