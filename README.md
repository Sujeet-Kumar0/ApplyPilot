<!-- logo here -->

> **⚠️ ApplyPilot** is the original open-source project, created by [Pickle-Pixel](https://github.com/Pickle-Pixel) and first published on GitHub on **February 17, 2026**. We are **not affiliated** with applypilot.app, useapplypilot.com, or any other product using the "ApplyPilot" name. These sites are **not associated with this project** and may misrepresent what they offer. If you're looking for the autonomous, open-source job application agent — you're in the right place.

# ApplyPilot

**Applied to 1,000 jobs in 2 days. Fully autonomous. Open source.**

[![PyPI version](https://img.shields.io/pypi/v/applypilot?color=blue)](https://pypi.org/project/applypilot/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ibarrajo/ApplyPilot?style=social)](https://github.com/ibarrajo/ApplyPilot)

> **Forked from [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot)** — this fork adds multi-provider LLM fallback, human-in-the-loop apply, Gmail tracking, HITL CDP badge injection, a Q&A knowledge base, and significant pipeline hardening. Thank you to the original authors for the foundation.




https://github.com/user-attachments/assets/7ee3417f-43d4-4245-9952-35df1e77f2df


---

## What It Does

ApplyPilot is a 6-stage autonomous job application pipeline. It discovers jobs across 5+ boards, scores them against your resume with AI, tailors your resume per job, writes cover letters, and **submits applications for you**. It navigates forms, uploads documents, answers screening questions, all hands-free.

Three commands. That's it.

```bash
pip install applypilot
pip install --no-deps python-jobspy    # separate install (broken numpy pin in metadata)
pip install pydantic tls-client requests markdownify regex  # jobspy runtime deps skipped by --no-deps
applypilot init          # one-time setup: resume, profile, preferences, API keys
applypilot run           # discover > enrich > score > tailor > cover letters
applypilot run -w 4      # same but parallel (4 threads for discovery/enrichment)
applypilot apply         # autonomous browser-driven submission
applypilot apply -w 3    # parallel apply (3 Chrome instances)
applypilot apply --dry-run  # fill forms without submitting
```

---

## Two Paths

### Full Pipeline (recommended)
**Requires:** Python 3.11+, Node.js (for npx), Gemini API key (free), Claude Code CLI, Chrome

Runs all 6 stages, from job discovery to autonomous application submission. This is the full power of ApplyPilot.

### Discovery + Tailoring Only
**Requires:** Python 3.11+, Gemini API key (free)

Runs stages 1-5: discovers jobs, scores them, tailors your resume, generates cover letters. You submit applications manually with the AI-prepared materials.

---

## The Pipeline

| Stage | What Happens |
|-------|-------------|
| **1. Discover** | Scrapes 5 job boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs) + 48 Workday employer portals + 30 direct career sites |
| **2. Enrich** | Fetches full job descriptions via JSON-LD, CSS selectors, or AI-powered extraction |
| **3. Score** | AI rates every job 1-10 based on your resume and preferences. Only high-fit jobs proceed |
| **4. Tailor** | AI rewrites your resume per job: reorganizes, emphasizes relevant experience, adds keywords. Never fabricates |
| **5. Cover Letter** | AI generates a targeted cover letter per job |
| **6. Auto-Apply** | Claude Code navigates application forms, fills fields, uploads documents, answers questions, and submits |

Each stage is independent. Run them all or pick what you need.

---

## ApplyPilot vs The Alternatives

| Feature | ApplyPilot | AIHawk | Manual |
|---------|-----------|--------|--------|
| Job discovery | 5 boards + Workday + direct sites | LinkedIn only | One board at a time |
| AI scoring | 1-10 fit score per job | Basic filtering | Your gut feeling |
| Resume tailoring | Per-job AI rewrite | Template-based | Hours per application |
| Auto-apply | Full form navigation + submission | LinkedIn Easy Apply only | Click, type, repeat |
| Supported sites | Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, 46 Workday portals, 28 direct sites | LinkedIn | Whatever you open |
| License | AGPL-3.0 | MIT | N/A |

---

## New Here? Use Claude Code to Get Started

If you're not comfortable with the terminal or just want a guided experience, the easiest way to run ApplyPilot is to let **Claude Code** operate it for you. Claude Code is Anthropic's CLI tool — think of it as an AI assistant that can read your files, run commands, and fix errors on your behalf.

**Step 1: Install Claude Code**

Go to [claude.ai/code](https://claude.ai/code) and follow the install instructions for your OS. You'll need a Claude account (free tier works for setup; a Max plan is needed for the auto-apply stage).

**Step 2: Open a terminal in the ApplyPilot directory**

On Mac: open Terminal, then type `cd ~/path/to/ApplyPilot`
On Windows: use WSL or PowerShell and navigate to where you cloned the repo.

**Step 3: Start Claude Code**

```bash
claude
```

That's it. You're now in an interactive session with an AI that has full access to the project.

**Step 4: Just tell it what you want**

You don't need to memorize commands. Try prompts like:

```
Help me set up ApplyPilot for the first time — I haven't run init yet.
```
```
Run the pipeline and tell me what's happening at each stage.
```
```
Check the status and tailor resumes for my top matches.
```
```
I got an error. Here's what it said: [paste error]. Can you fix it?
```

Claude will read the code, run the commands, interpret the output, and fix things that break. It won't move on until each stage is healthy. You just watch and approve.

> **Tip:** If you're new to job searching with tools like this, start with `applypilot run discover score` to see what jobs it finds before letting it apply anywhere.

---

## Requirements

| Component | Required For | Details |
|-----------|-------------|---------|
| Python 3.11+ | Everything | Core runtime |
| Node.js 18+ | Auto-apply | Needed for `npx` to run Playwright MCP server |
| Gemini API key | Scoring, tailoring, cover letters | Free tier (15 RPM / 1M tokens/day) is enough |
| Chrome/Chromium | Auto-apply | Auto-detected on most systems |
| Claude Code CLI | Auto-apply | Install from [claude.ai/code](https://claude.ai/code) |

**Gemini API key is free.** Get one at [aistudio.google.com](https://aistudio.google.com). OpenAI and local models (Ollama/llama.cpp) are also supported.

### Optional

| Component | What It Does |
|-----------|-------------|
| CapSolver API key | Solves CAPTCHAs during auto-apply (hCaptcha, reCAPTCHA, Turnstile, FunCaptcha). Without it, CAPTCHA-blocked applications just fail gracefully |

> **Note:** python-jobspy is installed separately with `--no-deps` because it pins an exact numpy version in its metadata that conflicts with pip's resolver. It works fine with modern numpy at runtime.

---

## Configuration

All generated by `applypilot init`:

### `profile.json`
Your personal data in one structured file: contact info, work authorization, compensation, experience, skills, resume facts (preserved during tailoring), and EEO defaults. Powers scoring, tailoring, and form auto-fill.

### `searches.yaml`
Job search queries, target titles, locations, boards. Run multiple searches with different parameters.

### `.env`
API keys and runtime config: `GEMINI_API_KEY`, `LLM_MODEL`, `CAPSOLVER_API_KEY` (optional).

### Package configs (shipped with ApplyPilot)
- `config/employers.yaml` - Workday employer registry (48 preconfigured)
- `config/sites.yaml` - Direct career sites (30+), blocked sites, base URLs, manual ATS domains
- `config/searches.example.yaml` - Example search configuration

---

## How Stages Work

### Discover
Queries Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs via JobSpy. Scrapes 48 Workday employer portals (configurable in `employers.yaml`). Hits 30 direct career sites with custom extractors. Deduplicates by URL.

### Enrich
Visits each job URL and extracts the full description. 3-tier cascade: JSON-LD structured data, then CSS selector patterns, then AI-powered extraction for unknown layouts.

### Score
AI scores every job 1-10 against your profile. 9-10 = strong match, 7-8 = good, 5-6 = moderate, 1-4 = skip. Only jobs above your threshold proceed to tailoring.

### Tailor
Generates a custom resume per job: reorders experience, emphasizes relevant skills, incorporates keywords from the job description. Your `resume_facts` (companies, projects, metrics) are preserved exactly. The AI reorganizes but never fabricates.

### Cover Letter
Writes a targeted cover letter per job referencing the specific company, role, and how your experience maps to their requirements.

### Auto-Apply
Claude Code launches a Chrome instance, navigates to each application page, detects the form type, fills personal information and work history, uploads the tailored resume and cover letter, answers screening questions with AI, and submits. A live dashboard shows progress in real-time.

The Playwright MCP server is configured automatically at runtime per worker. No manual MCP setup needed.

```bash
# Utility modes (no Chrome/Claude needed)
applypilot apply --mark-applied URL    # manually mark a job as applied
applypilot apply --mark-failed URL     # manually mark a job as failed
applypilot apply --reset-failed        # reset all failed jobs for retry
applypilot apply --gen --url URL       # generate prompt file for manual debugging
```

---

## CLI Reference

```
applypilot init                         # First-time setup wizard
applypilot run [stages...]              # Run pipeline stages (or 'all')
applypilot run --workers 4              # Parallel discovery/enrichment
applypilot run --stream                 # Concurrent stages (streaming mode)
applypilot run --min-score 8            # Override score threshold
applypilot run --dry-run                # Preview without executing
applypilot apply                        # Launch auto-apply
applypilot apply --workers 3            # Parallel browser workers
applypilot apply --dry-run              # Fill forms without submitting
applypilot apply --continuous           # Run forever, polling for new jobs
applypilot apply --headless             # Headless browser mode
applypilot apply --url URL              # Apply to a specific job
applypilot status                       # Pipeline statistics
applypilot dashboard                    # Open HTML results dashboard
```

---

## Security & Privacy — Read This Before You Run

ApplyPilot handles sensitive data: your resume, contact info, work history, and optionally credentials for job boards. Before you run anything, you should understand exactly what stays on your machine and what leaves it.

### What stays local

- **`~/.applypilot/applypilot.db`** — a SQLite database with every job discovered, scored, and applied to, plus your application status
- **`~/.applypilot/profile.json`** — your full profile: name, contact info, work history, skills, location preferences, salary expectations, EEO fields, and any stored credentials
- **`~/.applypilot/tailored_resumes/`** and **`~/.applypilot/cover_letters/`** — AI-generated documents per job
- **`~/.applypilot/.env`** — your API keys (Gemini, OpenAI). This file is never committed to git.

None of this is uploaded to any ApplyPilot server. There is no ApplyPilot cloud. The project is fully local.

### What gets sent to external APIs

The scoring, tailoring, and cover letter stages send data to third-party LLM providers:

| What's sent | Where | Why |
|-------------|-------|-----|
| Your resume + job description | Gemini (Google) or OpenAI | Scoring and tailoring |
| Your resume + company info | Gemini or OpenAI | Cover letter generation |
| Form field contents + job URL | Claude (Anthropic) | Auto-apply stage |

This means **your resume content is sent to Google and/or OpenAI** every time a job is scored or tailored. Review the privacy policies of [Google AI Studio](https://aistudio.google.com) and [OpenAI](https://openai.com/policies/privacy-policy) if this concerns you. Both offer API-tier data handling that differs from consumer products.

### Passwords and credentials — be careful

`profile.json` can include account passwords for job boards. These are stored **in plaintext** in a local SQLite database and are included **verbatim in LLM prompts** sent to external providers during the auto-apply stage.

**Recommendations:**

- Do not store your primary password for anything in `profile.json`
- If you use password storage here, create a unique password used only for job applications
- Better yet: rely on browser session auth (log in manually once, let the browser remember it) and leave the password field empty
- Use a dedicated job-search email address, not your primary one
- Review `profile.json` before your first run to make sure you're comfortable with what's in it

### The auto-apply stage (Tier 3)

The auto-apply stage spawns a Claude Code subprocess with `--bypassPermissions`. This means Claude can take autonomous actions in the browser without asking for confirmation on each step. It is intentionally sandboxed with `--strict-mcp-config` to limit which browser tools it can access, but you should understand you are granting meaningful autonomy to an AI agent acting on your behalf.

Dry run first:

```bash
applypilot apply --dry-run --url <job_url>
```

This fills forms without submitting, so you can verify behavior before going live.

---

## A Note from Alex

If you're using this tool — thank you. Genuinely. It means a lot to know something I built during one of the harder chapters of my career is useful to someone else going through the same grind.

This pipeline helped me apply to hundreds of jobs I would never have reached manually, get my materials in front of companies I cared about, and stay sane while doing it. I hope it does the same for you.

If it's been useful, the best way to say thanks is simple: [follow me on GitHub](https://github.com/ibarrajo) and star this repo — or any of my other projects while you're there. It signals to me that this work matters and gives me motivation to keep improving it.

---

**But here's the thing I want to be honest about:** running an automation that blasts every ATS and every job board shouldn't be the goal of your job search — and I say that as someone who built this tool and used it himself.

The signal-to-noise problem in hiring is already catastrophic. ATS inboxes are flooded. Recruiters are overwhelmed. Candidates are invisible. There's an entire industry that exists just to help people game a system that was never designed for humans in the first place. Adding more volume doesn't fix that — it makes it worse for everyone, including you.

I built ApplyPilot as a force multiplier for a *focused* search: high-fit jobs, properly tailored materials, applied efficiently. Not a firehose.

The deeper problem is the matching problem itself — the **n×m problem** of connecting the right job seekers to the right employers at scale. I spent three years at [Jobscan](https://www.jobscan.co) as a lead engineer thinking about exactly this. We built resume optimization tuned per company and ATS, job trackers, job search tools, and coaching tools for career professionals — all trying to close the gap between what candidates bring and what employers can actually see. It's hard. The current system is structurally broken.

That's why, at a recent [Venture Mechanics](https://venturemechanics.com) AI Scalathon in Seattle, my team and I explored what I think is the natural next step: **agent-to-agent matching**. Instead of humans gaming systems built for computers, imagine employer agents and candidate agents negotiating directly — structured, transparent, and actually aligned with what both sides want. A distributed future where AI closes the gap rather than adding to the noise.

ApplyPilot is a tool for today's broken system. The agent-to-agent future is what I'm working toward next — and it's apparently been a running joke in VC and AI startup circles for years. Ask anyone building in the recruiting tech space and they'll tell you: "yeah, the real solution is obviously a2a, someone just needs to actually build it." A punchline that kept coming up in founder conversations, investor pitches, and hackathon hallways. My team and I are building that something. It's called **Pursit**.

Good luck out there. Reach me at [elninja.com](https://elninja.com) if you want to talk.

Oh, and — if you're a recruiter or hiring manager who ended up here: hi. I'm the one looking for a job. You just found me without a job board, a keyword filter, or an ATS — so maybe we can skip all that. [LinkedIn](https://www.linkedin.com/in/elninja) or [my resume](https://elninja.com/resume) work just fine.

— Alex Ibarra

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

---

## License

ApplyPilot is licensed under the [GNU Affero General Public License v3.0](LICENSE).

You are free to use, modify, and distribute this software. If you deploy a modified version as a service, you must release your source code under the same license.
