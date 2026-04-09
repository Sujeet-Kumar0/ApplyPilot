# TODO

## Status: Production Ready + Full RUN Core Redesign

- 930 tests passing, 0 lint errors
- Core pipeline + piece system + analytics fully wired
- Innovation features: A-F evaluation (with story bank + negotiation), track framing, star validator, resume presets
- 232+ employers across 7 ATS platforms (129 Greenhouse + 48 Workday + 30 direct + 13 Ashby + 12 Lever + JobSpy + HN)
- RUN core redesigned: --url, --source, --company, --strict-title, --force flags
- All 5 previously dead innovation modules wired into pipeline
- Discovery filtering: source-level + company-level + shared title filter

## Completed (2026-04-06 to 2026-04-07)

### RUN Core Redesign

- `single` merged into `run --url` (backward compat alias kept)
- `--url URL1 URL2` — skip discover, run enrich→score→tailor→cover on specific URLs
- `--source greenhouse,workday` — filter which discovery runners execute
- `--company apple,walmart` — filter which employers get scraped
- `--strict-title` — require ALL query terms in title (vs ANY)
- `--force` — re-tailor already-tailored jobs
- Mutual exclusion: --url conflicts with --source/--company
- Ashby + Lever runners wired into main discovery pipeline
- Shared `discovery/title_filter.py` used by all sources
- Company registry with multi-field resolution (key, alias, domain, substring)
- Evaluation report generated during batch scoring (stored in DB)
- Cover letter respects `cover_letter.enabled` in profile config
- Prompt security: system/user message separation in smartextract + enrichment

### Architecture Fixes (2026-04-06)

- ResumeBuilder.render_html() — direct HTML from structured sections, no text round-trip
- Unified HTML renderer — pieces renderer uses professional template
- render_resume_from_db() — produces HTML/PDF from DB pieces with auto-decompose
- resume render CLI defaults to DB pieces, --from-file for themed render
- ComprehensiveStorage + state_machine — use get_connection() singleton
- --resume-pdf wired from CLI → ProfileService → wizard

### Innovation Features Wired (2026-04-06)

- story_bank.py → evaluation_report.py Block F (interview STAR+R stories)
- negotiation.py → evaluation_report.py Block D (salary scripts)
- star_validator.py → enrich_cmd.py (validates bullets after enrichment)
- track_framing.py → prompt_builder.py (injects "what employers buy")
- resume_rendering.py → prompt_builder.py (presets: enterprise/startup/eu/academic)
- Deleted superseded scoring/tailor/variant_generator.py

## Remaining TODO

### validate_agent_log test harness (from ANALYSIS_RESULTS.md)

- Post-run validation: no browser_evaluate writes, no HTML ids as refs, iteration count
- Automated regression testing for agent behavior

### Career Page Discovery (design doc exists: docs/CAREER_PAGE_DISCOVERY_DESIGN.md)

- `applypilot run discover --career-url careers.walmart.com`
- Try common paths → ATS detection → auto-add to registry
- Not yet implemented

### Dashboard TUI (terminal)

- Python `textual` library
- Reads directly from SQLite DB

### REST API (prerequisite for Web UI)

- FastAPI over existing services
- Every CLI command maps 1:1 to a service method

### Web UI (separate project)

- Requires REST API layer first

### Test Coverage

- 53 files at 0% coverage (mostly apply/browser, tracking/email, runtime CLI)
- Need integration tests with mocked dependencies

## Known Limitations

- Discover↔Enrich overlap: chunked mode overlaps enrich↔score but discovery runs fully first
- LinkedIn auto-apply: needs authenticated browser session
- Resume render HTML: themed render still needs npx
