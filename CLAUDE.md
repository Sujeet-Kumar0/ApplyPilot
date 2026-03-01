# ApplyPilot — Claude Code Operating Manual

## Mission

Get Alex Ibarra hired. ApplyPilot is an autonomous job application pipeline.
Claude's job is to **operate, monitor, and fix the pipeline** — not to manually do what the pipeline automates.

**The goal**: Discover jobs → Score them → Tailor resumes → Generate cover letters → Auto-apply. All automated.

---

## Claude's Role (READ THIS FIRST)

**Claude is the pipeline engineer and operator. Claude does NOT manually apply to jobs.**

### What Claude Does
1. Run pipeline commands (`applypilot run ...`, `applypilot apply`, `applypilot status`)
2. Monitor logs and output for errors
3. Diagnose root causes when things break
4. Fix the source code (`src/applypilot/`)
5. Re-run and verify fixes work
6. Keep this CLAUDE.md updated with decisions and learnings

### What Claude Does NOT Do
- Open a browser via Playwright and manually fill out application forms
- Act as the "apply agent" — that's what `applypilot apply` spawns Claude Code subprocesses for
- Skip the automation and do things by hand "just this once"

### Daily Operating Loop
```
1. applypilot status              # Where are we? What's the funnel?
2. applypilot run discover        # Find new jobs
3. applypilot run enrich          # Fetch full descriptions
4. applypilot run score           # AI scoring
5. applypilot run tailor          # Tailor resumes for 7+ scores
6. applypilot run cover           # Generate cover letters
7. applypilot apply               # Auto-apply (Tier 3 — uses Claude Code credits)
8. applypilot dashboard           # Generate HTML dashboard for review
```

When a stage fails: stop, read logs, find root cause, fix code, re-run.

---

## Architecture

### Three Tiers
- **Tier 1** (Discovery): No API key. Scrapes job boards.
- **Tier 2** (AI Processing): Gemini/OpenAI API. Score, tailor, cover letters.
- **Tier 3** (Auto-Apply): Claude Code CLI as subprocess. Fills forms via Playwright.

### Two Credit Systems (IMPORTANT)
- **Tier 2**: Gemini API (free tier) + OpenAI fallback. Keys in `~/.applypilot/.env`
- **Tier 3**: Claude Code CLI with Max plan. IMPORTANT: `ANTHROPIC_API_KEY` must be stripped from subprocess env (launcher.py does this) or it overrides Max plan auth with API billing. No Gemini browser agent exists — the Gemini/OpenAI cascade is Tier 2 only. `--strict-mcp-config` is required to prevent Docker MCP's Playwright (which can't access host files) from interfering with resume uploads.

### LLM Client (`src/applypilot/llm.py`)

Multi-provider fallback with two-tier model strategy:
- **Fast** (scoring, HN extraction): `gemini-2.5-flash → gemini-3-flash → gemini-2-flash → gemini-2-flash-lite → gpt-4.1-nano → gpt-4.1-mini → claude-haiku-4-5`
- **Quality** (tailoring, cover letters): `gemini-3.1-pro-preview → gemini-2.5-pro → gemini-3-pro → gemini-2.5-flash → gpt-4.1-mini → gpt-4.1-nano → claude-sonnet-4-5 → claude-haiku-4-5`

Key behaviors:
- `get_client(quality=False)` for fast, `get_client(quality=True)` for quality
- On 429: marks model exhausted for 5 min, falls to next in chain
- `config.load_env()` MUST be called before importing `llm` (env vars read at module import)
- Gemini 2.5+ thinking tokens consume max_tokens budget — set much higher than visible output needs

### Tracking Module (`src/applypilot/tracking/`)

Post-apply pipeline for monitoring application outcomes:
- **Gmail** (`gmail_client.py`): OAuth-based inbox scanning for response emails
- **Classifier** (`classifier.py`): LLM classifies email as rejection/interview/ghosting
- **Ghosting** (`ghosting.py`): Flags jobs with no response after N days
- **Matcher** (`matcher.py`): Matches emails → jobs by company/title heuristics
- **Triage** (`triage.py`): Surfaces action items (reply needed, schedule interview)

Run: `applypilot track`

### HITL Flow (`src/applypilot/apply/human_review.py`)

When the apply agent can't proceed autonomously (CAPTCHA, login wall, unusual form):
1. Agent emits `RESULT:NEEDS_HUMAN:{reason}:{url}` → launcher parks job with `apply_status='needs_human'`
2. `applypilot human-review` → HTTP server at localhost:7373 + CDP banner injected into Chrome (port 9300)
3. User completes the action, clicks Done → agent resumes via `run_job()` at `HITL_CDP_PORT=9300`

### Database (`src/applypilot/database.py`)

SQLite with WAL mode. Thread-local connections.
- `ensure_columns()` auto-adds missing columns via ALTER TABLE
- URL normalization at insert time (resolves relative URLs via `sites.yaml` base_urls)
- `company` column extracted from `application_url` domain (Workday, Greenhouse, Lever, iCIMS patterns)
- `acquire_job()` uses company-aware prioritization to spread applications across employers

### Pipeline Stages

Dashboard stages (used by `view.py` for grouping into active/archive/applied tabs):

| Stage | Condition | Tab |
|-------|-----------|-----|
| `discovered` | no description, no error | active |
| `enrich_error` | has `detail_error` | archive |
| `enriched` | has description, no score | active |
| `scored` | score < 7 | archive |
| `scored_high` | score >= 7, not tailored | active |
| `tailor_failed` | attempts >= 5, no result | archive |
| `tailored` | has resume, no cover letter | active |
| `cover_ready` | has cover letter, not applied | active |
| `applied` | `apply_status = 'applied'` | applied |
| `apply_failed` | permanent apply error | archive |
| `apply_retry` | retryable apply error | active |
| `needs_human` | `apply_status = 'needs_human'` — HITL required | active (purple) |

DB query stages (used by `database.py:get_jobs_by_stage()`): `discovered`, `pending_detail`, `enriched`, `pending_score`, `scored`, `pending_tailor`, `tailored`, `pending_apply`, `applied`.

---

## Dev Setup

```bash
python3 -m venv .venv           # Python 3.11+ required
pip install -e .                # Editable install — source edits take effect immediately
playwright install chromium     # Browser for enrichment + PDF generation
```

- **direnv** auto-activates `.venv` on `cd` (configured via `.envrc`)
- **chezmoi** manages `~/.zshrc` (includes direnv hook)
- API keys go in `~/.applypilot/.env` (never committed)

---

## File Locations

| What | Path |
|------|------|
| Source code | `~/Code/ApplyPilot/src/applypilot/` (editable install) |
| Venv | `~/Code/ApplyPilot/.venv` (auto-activated via direnv) |
| Resume (txt) | `~/.applypilot/resume.txt` |
| Resume (PDF) | `~/.applypilot/resume.pdf` |
| API keys | `~/.applypilot/.env` (Gemini + OpenAI keys. NEVER commit.) |
| Profile | `~/.applypilot/profile.json` |
| Search config | `~/.applypilot/searches.yaml` |
| Database | `~/.applypilot/applypilot.db` |
| Tailored resumes | `~/.applypilot/tailored_resumes/{site}_{title}_{hash}.txt` (+`.pdf`) |
| Cover letters | `~/.applypilot/cover_letters/{site}_{title}_{hash}_CL.txt` (+`.pdf`) |
| Apply logs | `~/.applypilot/logs/claude_{YYYYMMDD_HHMMSS}_w{N}_{site}.txt` |
| Dashboard | `~/.applypilot/dashboard.html` |

---

## Candidate Profile

Full details in `~/.applypilot/profile.json`. Key context for pipeline decisions:

- **Name:** Alex Ibarra | **Email:** alex@elninja.com
- **Experience:** 10+ years — Go, Kotlin, Python, TypeScript, Cadence/Temporal, K8s, AWS/GCP
- **Target:** Senior/Staff/Principal Backend/Platform Engineer (remote OK)
- **Location rules:** In-bounds: Seattle, Bellevue, Kirkland, Redmond. Excluded: Everett, Bothell, Renton, Tacoma.

---

## Key Commands

```bash
# Tier 2 pipeline (safe, uses Gemini/OpenAI)
applypilot run discover                        # Find new jobs
applypilot run enrich                          # Fetch full descriptions
applypilot run score --limit 100               # AI scoring
applypilot run tailor --limit 50               # Tailor resumes (score >= 7)
applypilot run cover                           # Generate cover letters
applypilot run score tailor cover --stream     # All stages concurrently
applypilot status                              # Pipeline funnel stats
applypilot dashboard                           # Generate HTML dashboard

# Tier 3 apply (uses Claude Code credits)
applypilot apply --dry-run --url URL           # Test one job (no submit)
applypilot apply                               # Auto-apply to cover_ready jobs
applypilot human-review                        # HITL server for needs_human jobs

# Post-apply tracking
applypilot track                               # Scan Gmail for responses, triage action items

# Q&A knowledge base (screening questions)
applypilot qa list                             # List known Q&A pairs
applypilot qa stats                            # KB coverage stats
applypilot qa export --output qa.yaml          # Export to YAML
applypilot qa import --file qa.yaml            # Import from YAML
```

---

## Orchestration Strategy

When running the pipeline:
1. **Throughput** — use `--stream` for concurrent stages
2. **Quality** — highest scores get tailored first, company diversity in applications
3. **Error handling** — if > 30% failure rate, stop and fix before continuing
4. **Bottleneck focus** — priority is building the apply-ready queue

Error patterns:
- Gemini 429: automatic fallback, no intervention needed
- Tailor validation failures > 30%: investigate validator settings
- Apply credit exhaustion: alert user, cannot auto-fix
- `hn://` URLs or malformed data: check hackernews.py sanitization

---

## Security Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Never paste API keys in chat | Keys go directly into `~/.applypilot/.env` |
| 2 | Display name "Alex Ibarra" on applications | `preferred_name = "Alex"` in profile.json. Legal name for background checks only. |
| 3 | alex@elninja.com for job search | Cloudflare Email Routing → personal inbox |
| 4 | No real password in profile.json | Embedded in plaintext in LLM prompts |
| 5 | Tier 3 in production (112+ applied) | Auto-apply is active. bypassPermissions risk accepted with `--strict-mcp-config` mitigation. |
| 6 | Review tailored resumes before using | `resume_facts` pins facts but still check |
| 7 | Gemini free tier + OpenAI fallback | Free primary, cheap fallback |
| 8 | Location: Remote + Seattle metro | 25mi search radius captures Bellevue/Redmond/Kirkland |
| 9 | Two-tier model strategy | Flash for speed, Pro for quality writing |
| 10 | High max_tokens for thinking models | Scoring: 8192, Tailoring: 4096 (validation) + 16384 (generation), Cover: 8192 |
| 11 | Skip Gmail MCP / CapSolver | Too much attack surface with bypassPermissions |
| 12 | URL normalization at discovery | Resolves relative URLs via sites.yaml base_urls |
| 13 | Banned words = warnings not errors | "dedicated" matched real resume phrase; LLM judge handles tone |
| 14 | Jobs without application_url = manual | LinkedIn Easy Apply marked `apply_status='manual'` |
| 15 | Company-aware apply prioritization | ROW_NUMBER() PARTITION BY company spreads applications across employers |
| 16 | Apply uses Claude Code CLI, not Gemini | Separate billing system. Spawns `claude` subprocess. |
| 17 | HN URL sanitization | Only stores http(s) URLs, deobfuscates emails, synthetic URLs for contact-only posts |
| 18 | Basic prompt injection defense | LLM prompts instruct to treat input as untrusted. Minimal — not a sandbox. |
| 19 | `--strict-mcp-config` for apply subprocess | Docker MCP Toolkit exposes duplicate Playwright tools that run in containers (can't access host files). Strict mode ensures only our local npx Playwright is available. |
| 20 | Chrome loads uBlock + 1Password via `--load-extension` | uBlock blocks ads/trackers for faster page loads; 1Password auto-fills credentials. Resolved dynamically from user's Chrome profile at launch. |

---

## Current Pipeline State (as of 2026-02-26)

- **1503 jobs** discovered (LinkedIn, Indeed, Dice, SimplyHired, HN, and more)
- **1420 scored**, 543 strong matches (7+)
- **543 resumes tailored**, 0 pending
- **543 cover letters** generated
- **112 jobs applied**
- **587 apply errors**
- **256 ready to apply** in queue

### Active TODO
- [ ] Test `applypilot apply` on a few jobs and fix errors
- [ ] Regenerate SeatGeek cover letter (had fabrication: "Underground Elephant")
- [ ] Gmail "Send mail as" for alex@elninja.com (needs AWS SES, deferred)

---

## Known Technical Gotchas

1. **Gemini thinking tokens**: 2.5+ models use thinking tokens that consume max_tokens budget. A simple response needs 30 tokens, a bullet rewrite needs 1200+.
2. **Agent log timezone**: Log filenames use local time, DB `last_attempted_at` is UTC. Dashboard matcher converts UTC→local.
3. **Singleton LLM client**: `llm.py` reads env vars at module import. Call `config.load_env()` BEFORE importing.
4. **Editable install**: `pip install -e .` means source edits take effect immediately.
5. **Docker MCP Toolkit interference**: If Docker Desktop is installed with MCP Toolkit, it exposes `mcp__MCP_DOCKER__browser_*` tools that shadow the local Playwright MCP. These Docker tools can't access the host filesystem, breaking resume/cover letter uploads. Fix: `--strict-mcp-config` in the claude subprocess command.
6. **Extension version paths**: `chrome.py:_resolve_extension_paths()` picks the latest version dir. If Chrome updates an extension, paths resolve automatically. If an extension is uninstalled from Chrome, it's silently skipped.
