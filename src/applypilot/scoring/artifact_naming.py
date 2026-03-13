"""Helpers for collision-resistant scoring artifact filenames."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlparse

_JOB_ID_QUERY_KEYS = ("jk", "jid", "currentJobId", "jobId", "job_id", "gh_jid")


def slugify_for_filename(value: str, max_len: int, fallback: str) -> str:
    """Return a filesystem-safe slug for artifact filenames."""

    safe = re.sub(r"[^\w\s-]", "", value).strip().replace(" ", "_")
    safe = re.sub(r"_+", "_", safe)[:max_len].strip("_")
    return safe or fallback


def extract_job_id(url: str) -> str | None:
    """Extract a likely job identifier from a job URL."""

    if not url:
        return None

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query_lower = {key.lower(): values for key, values in query.items()}

    for key in _JOB_ID_QUERY_KEYS:
        values = query_lower.get(key.lower())
        if not values:
            continue
        value = str(values[0]).strip()
        if value:
            return value

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        last = path_parts[-1].strip()
        if last:
            return last

    return None


def build_artifact_prefix(job: dict) -> str:
    """Build a deterministic, collision-resistant filename prefix for a job."""

    safe_title = slugify_for_filename(str(job.get("title", "")), max_len=50, fallback="untitled")
    safe_site = slugify_for_filename(str(job.get("site", "")), max_len=20, fallback="unknown_site")

    url = str(job.get("url", ""))
    job_id = extract_job_id(url)
    safe_job_id = slugify_for_filename(job_id or "", max_len=40, fallback="")

    if safe_job_id:
        unique_suffix = safe_job_id
    elif url:
        unique_suffix = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    else:
        unique_suffix = "no_url"

    return f"{safe_site}_{safe_title}_{unique_suffix}"
