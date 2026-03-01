"""Match incoming emails to applied jobs using multi-signal scoring.

Signals and weights:
  - Sender domain matches company/application_url domain: 40
  - Company name appears in subject or body: 25
  - Job title keyword overlap in subject: 20
  - ATS sender pattern (noreply, greenhouse, lever...): 10
  - Temporal proximity (within 30 days of applied_at): 5

Threshold: 40 points minimum.
"""

import logging
import re
from datetime import datetime
from urllib.parse import urlparse

log = logging.getLogger(__name__)

# Known ATS notification sender patterns
ATS_SENDER_PATTERNS = {
    "greenhouse.io", "lever.co", "icims.com", "myworkdayjobs.com",
    "jobvite.com", "smartrecruiters.com", "workable.com",
    "ashbyhq.com", "breezy.hr", "recruitee.com", "jazz.co",
}

ATS_SENDER_PREFIXES = {"noreply", "no-reply", "notifications", "careers", "jobs", "talent", "recruiting"}


def _extract_domain(address: str) -> str:
    """Extract domain from email address or URL."""
    if "@" in address:
        return address.split("@")[-1].strip().lower()
    try:
        parsed = urlparse(address)
        host = parsed.hostname or ""
        return host.lower()
    except Exception:
        return address.lower()


def _domain_root(domain: str) -> str:
    """Get the root domain (last two parts): mail.kentik.com -> kentik.com."""
    parts = domain.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain


def _extract_company_from_url(url: str | None) -> str | None:
    """Extract company name from an application URL (simplified)."""
    if not url:
        return None
    from applypilot.database import extract_company
    return extract_company(url)


def _title_keywords(title: str | None) -> set[str]:
    """Extract significant keywords from a job title."""
    if not title:
        return set()
    # Remove common stop words and short words
    stops = {"the", "a", "an", "and", "or", "at", "in", "for", "of", "to", "with", "is", "are", "we"}
    words = re.findall(r'[a-z]+', title.lower())
    return {w for w in words if len(w) > 2 and w not in stops}


def match_email_to_job(email: dict, applied_jobs: list[dict]) -> dict | None:
    """Match a single email to the best applied job.

    Args:
        email: Normalized email dict with keys: sender, subject, body, date.
        applied_jobs: List of job dicts from get_applied_jobs().

    Returns:
        Dict with {job_url, score, signals} if matched, else None.
    """
    sender = email.get("sender", "")
    sender_domain = _extract_domain(sender)
    sender_root = _domain_root(sender_domain)
    sender_local = sender.split("@")[0].lower() if "@" in sender else ""
    subject = (email.get("subject") or "").lower()
    body = (email.get("body") or "").lower()
    email_date_str = email.get("date", "")

    email_dt = None
    if email_date_str:
        try:
            email_dt = datetime.fromisoformat(email_date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    best_match = None
    best_score = 0

    for job in applied_jobs:
        score = 0
        signals = []

        job_url = job["url"]
        app_url = job.get("application_url") or ""
        company = (job.get("company") or "").lower()
        title = job.get("title") or ""

        # --- Signal 1: Sender domain matches company domain (40 pts) ---
        app_domain = _extract_domain(app_url) if app_url else ""
        app_root = _domain_root(app_domain) if app_domain else ""

        # Check if sender domain matches application URL domain
        if sender_root and app_root and sender_root == app_root:
            score += 40
            signals.append(f"domain_match:{sender_root}")
        elif company and sender_root:
            # Check if company name is in sender domain
            if company in sender_root or sender_root.split(".")[0] == company:
                score += 40
                signals.append(f"company_in_domain:{company}")

        # --- Signal 2: Company name in subject/body (25 pts) ---
        if company and len(company) > 2:
            if company in subject:
                score += 25
                signals.append(f"company_in_subject:{company}")
            elif company in body[:2000]:
                score += 15  # Lower weight for body (more noise)
                signals.append(f"company_in_body:{company}")

        # Also check company extracted from application_url
        url_company = _extract_company_from_url(app_url)
        if url_company and url_company != company and len(url_company) > 2:
            if url_company in subject:
                score += 25
                signals.append(f"url_company_in_subject:{url_company}")

        # --- Signal 3: Job title keyword overlap (20 pts) ---
        title_kw = _title_keywords(title)
        if title_kw:
            subject_words = set(re.findall(r'[a-z]+', subject))
            overlap = title_kw & subject_words
            if len(overlap) >= 2:
                score += 20
                signals.append(f"title_overlap:{','.join(overlap)}")
            elif len(overlap) == 1:
                score += 10
                signals.append(f"title_partial:{','.join(overlap)}")

        # --- Signal 4: ATS sender pattern (10 pts) ---
        is_ats = (
            any(ats in sender_domain for ats in ATS_SENDER_PATTERNS)
            or sender_local in ATS_SENDER_PREFIXES
        )
        if is_ats:
            score += 10
            signals.append("ats_sender")

        # --- Signal 5: Temporal proximity (5 pts) ---
        if email_dt and job.get("applied_at"):
            try:
                applied_dt = datetime.fromisoformat(
                    job["applied_at"].replace("Z", "+00:00")
                )
                delta_days = abs((email_dt - applied_dt).days)
                if delta_days <= 30:
                    score += 5
                    signals.append(f"temporal:{delta_days}d")
            except (ValueError, TypeError):
                pass

        # Track best match
        if score >= 40 and score > best_score:
            best_score = score
            best_match = {
                "job_url": job_url,
                "score": score,
                "signals": signals,
            }

    if best_match:
        log.debug("Best match: %s (score: %d, signals: %s)",
                  best_match["job_url"][:60], best_match["score"],
                  ", ".join(best_match["signals"]))
    return best_match
