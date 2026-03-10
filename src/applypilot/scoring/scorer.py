"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone

from applypilot.config import RESUME_PATH, load_profile
from applypilot.database import get_connection, get_jobs_by_stage
from applypilot.llm import get_client

log = logging.getLogger(__name__)


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT_TEMPLATE = """You are a job fit evaluator. Given a candidate's resume and a job description, score how well the candidate fits the role.

THE CANDIDATE: {candidate_summary}

SCORING CRITERIA:
- 10: Near-perfect IC engineering match. The role is a software/platform/infrastructure engineer position requiring the candidate's exact stack (Go/Kotlin/Python/Java, distributed systems, K8s). Seniority aligns (Senior/Staff/Principal). The candidate would be a top-tier applicant with minimal gaps.
- 9: Excellent engineering match. Strong alignment on tech stack and seniority, with 1-2 gaps in secondary skills or slightly different domain.
- 7-8: Good engineering match. Candidate has most required technical skills. Minor gaps in specific frameworks or domain experience, easily bridged.
- 5-6: Moderate match. The role is engineering but uses a different primary stack, or there's a seniority mismatch (e.g., junior role or executive-only role with no IC component).
- 3-4: Weak match. Engineering role but wrong specialization (frontend-only, mobile, ML research, data science), or a non-engineering role with some technical overlap.
- 1-2: Poor match. Non-engineering role (recruiting, design, marketing, product management, sales) or completely different field.

CRITICAL RULES:
- Non-engineering roles (recruiters, designers, PMs, marketing, sales, executive search) score 1-2 MAX regardless of seniority or domain.
- Roles requiring a specific language the candidate doesn't know (Rust, C++, Ruby, Scala, Clojure) as the PRIMARY requirement score 4-6 max depending on transferability.
- "CTO" or "VP Engineering" roles that are purely management with no IC engineering component score 5-6 max.
- Remote roles are neutral (no bonus or penalty).
- Distinguish REQUIRED skills from NICE-TO-HAVE. Only penalize for missing required skills.
- Value transferable experience: workflow orchestration, distributed systems, microservices, developer platforms transfer across domains.

You MUST include all three lines below. Do not skip REASONING.

SCORE: [1-10]
KEYWORDS: [comma-separated ATS keywords from the job description that match or could match the candidate]
REASONING: [2-3 sentences explaining the score, what matched well, and any gaps]"""


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's score response into structured data.

    Args:
        response: Raw LLM response text.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    score = 0
    keywords = ""
    reasoning = response

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def _build_candidate_summary(profile: dict) -> str:
    """Build a candidate summary string from profile for the scoring prompt."""
    exp = profile.get("experience", {})
    boundary = profile.get("skills_boundary", {})

    years = exp.get("years_of_experience_total", "several")
    target = exp.get("target_role", "Software Engineer")
    current_title = exp.get("current_job_title", "Software Engineer")

    # Collect primary languages/skills from boundary
    languages = boundary.get("languages", [])
    platforms = boundary.get("platforms", [])
    frameworks = boundary.get("frameworks", [])

    parts = [f"{current_title} with {years} years experience."]
    if languages:
        parts.append(f"Primary stack: {', '.join(languages[:8])}.")
    if platforms:
        parts.append(f"Platforms: {', '.join(platforms[:6])}.")
    if frameworks:
        parts.append(f"Frameworks: {', '.join(frameworks[:6])}.")
    parts.append(f"Targets: {target}.")

    return " ".join(parts)


def score_job(resume_text: str, job: dict, profile: dict | None = None) -> dict:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.
        profile: User profile dict. Loaded from config if not provided.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    if profile is None:
        profile = load_profile()

    candidate_summary = _build_candidate_summary(profile)
    score_prompt = SCORE_PROMPT_TEMPLATE.format(candidate_summary=candidate_summary)

    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    messages = [
        {"role": "system", "content": score_prompt},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_client()
        response = client.chat(messages, max_tokens=8192, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    profile = load_profile()
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    conn = get_connection()

    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    log.info("Scoring %d jobs sequentially...", len(jobs))
    t0 = time.time()
    completed = 0
    errors = 0
    batch_size = 25  # Commit every N jobs so downstream stages see results sooner
    batch: list[dict] = []

    for job in jobs:
        result = score_job(resume_text, job, profile=profile)
        result["url"] = job["url"]
        completed += 1

        if result["score"] == 0:
            errors += 1

        batch.append(result)

        log.info(
            "[%d/%d] score=%d  %s",
            completed, len(jobs), result["score"], job.get("title", "?")[:60],
        )

        # Flush batch to DB periodically
        if len(batch) >= batch_size:
            now = datetime.now(timezone.utc).isoformat()
            for r in batch:
                conn.execute(
                    "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
                    (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
                )
            conn.commit()
            log.info("Committed batch of %d scores to DB (%d/%d total)", len(batch), completed, len(jobs))
            batch = []

    # Flush remaining
    if batch:
        now = datetime.now(timezone.utc).isoformat()
        for r in batch:
            conn.execute(
                "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
                (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
            )
        conn.commit()

    elapsed = time.time() - t0
    log.info("Done: %d scored in %.1fs (%.1f jobs/sec)", len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0)

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
