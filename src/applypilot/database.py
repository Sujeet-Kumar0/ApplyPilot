"""ApplyPilot database layer: schema, migrations, stats, and connection helpers.

Single source of truth for the jobs table schema. All columns from every
pipeline stage are created up front so any stage can run independently
without migration ordering issues.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from applypilot.config import DB_PATH

# Thread-local connection storage — each thread gets its own connection
# (required for SQLite thread safety with parallel workers)
_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get a thread-local cached SQLite connection with WAL mode enabled.

    Each thread gets its own connection (required for SQLite thread safety).
    Connections are cached and reused within the same thread.

    Args:
        db_path: Override the default DB_PATH. Useful for testing.

    Returns:
        sqlite3.Connection configured with WAL mode and row factory.
    """
    path = str(db_path or DB_PATH)

    if not hasattr(_local, 'connections'):
        _local.connections = {}

    conn = _local.connections.get(path)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass

    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    _local.connections[path] = conn
    return conn


def close_connection(db_path: Path | str | None = None) -> None:
    """Close the cached connection for the current thread."""
    path = str(db_path or DB_PATH)
    if hasattr(_local, 'connections'):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the full jobs table with all columns from every pipeline stage.

    This is idempotent -- safe to call on every startup. Uses CREATE TABLE IF NOT EXISTS
    so it won't destroy existing data.

    Schema columns by stage:
      - Discovery:  url, title, salary, description, location, site, strategy, discovered_at
      - Enrichment: full_description, application_url, detail_scraped_at, detail_error
      - Scoring:    fit_score, score_reasoning, scored_at
      - Tailoring:  tailored_resume_path, tailored_at, tailor_attempts
      - Cover:      cover_letter_path, cover_letter_at, cover_attempts
      - Apply:      applied_at, apply_status, apply_error, apply_attempts,
                   agent_id, last_attempted_at, apply_duration_ms, apply_task_id,
                   verification_confidence

    Args:
        db_path: Override the default DB_PATH.

    Returns:
        sqlite3.Connection with the schema initialized.
    """
    path = db_path or DB_PATH

    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            -- Discovery stage (smart_extract / job_search)
            url                   TEXT PRIMARY KEY,
            title                 TEXT,
            salary                TEXT,
            description           TEXT,
            location              TEXT,
            site                  TEXT,
            strategy              TEXT,
            discovered_at         TEXT,

            -- Company (extracted from application_url domain)
            company               TEXT,

            -- Enrichment stage (detail_scraper)
            full_description      TEXT,
            application_url       TEXT,
            detail_scraped_at     TEXT,
            detail_error          TEXT,

            -- Scoring stage (job_scorer)
            fit_score             INTEGER,
            score_reasoning       TEXT,
            scored_at             TEXT,

            -- Tailoring stage (resume tailor)
            tailored_resume_path  TEXT,
            tailored_at           TEXT,
            tailor_attempts       INTEGER DEFAULT 0,

            -- Cover letter stage
            cover_letter_path     TEXT,
            cover_letter_at       TEXT,
            cover_attempts        INTEGER DEFAULT 0,

            -- Application stage
            applied_at            TEXT,
            apply_status          TEXT,
            apply_error           TEXT,
            apply_attempts        INTEGER DEFAULT 0,
            agent_id              TEXT,
            last_attempted_at     TEXT,
            apply_duration_ms     INTEGER,
            apply_task_id         TEXT,
            verification_confidence TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site TEXT NOT NULL,
            domain TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT,
            created_at TEXT NOT NULL,
            job_url TEXT REFERENCES jobs(url),
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_emails (
            email_id       TEXT PRIMARY KEY,
            thread_id      TEXT,
            job_url        TEXT NOT NULL REFERENCES jobs(url),
            sender         TEXT,
            sender_name    TEXT,
            subject        TEXT,
            received_at    TEXT,
            snippet        TEXT,
            body_text      TEXT,
            classification TEXT,
            extracted_data TEXT,
            classified_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_people (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url         TEXT NOT NULL REFERENCES jobs(url),
            name            TEXT,
            title           TEXT,
            email           TEXT,
            source_email_id TEXT REFERENCES tracking_emails(email_id),
            first_seen_at   TEXT,
            UNIQUE(job_url, email)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qa_knowledge (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            question_text   TEXT NOT NULL,
            question_key    TEXT NOT NULL,
            answer_text     TEXT NOT NULL,
            answer_source   TEXT NOT NULL,
            field_type      TEXT,
            options_json    TEXT,
            ats_slug        TEXT,
            job_url         TEXT,
            outcome         TEXT DEFAULT 'unknown',
            created_at      TEXT NOT NULL,
            updated_at      TEXT,
            UNIQUE(question_key, answer_text)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_key ON qa_knowledge(question_key)"
    )
    conn.commit()

    # Run migrations for any columns added after initial schema
    ensure_columns(conn)

    # Backfill apply categories for existing rows
    backfill_categories(conn)

    return conn


# Complete column registry: column_name -> SQL type with optional default.
# This is the single source of truth. Adding a column here is all that's needed
# for it to appear in both new databases and migrated ones.
_ALL_COLUMNS: dict[str, str] = {
    # Discovery
    "url": "TEXT PRIMARY KEY",
    "title": "TEXT",
    "salary": "TEXT",
    "description": "TEXT",
    "location": "TEXT",
    "site": "TEXT",
    "strategy": "TEXT",
    "discovered_at": "TEXT",
    # Company
    "company": "TEXT",
    # Enrichment
    "full_description": "TEXT",
    "application_url": "TEXT",
    "detail_scraped_at": "TEXT",
    "detail_error": "TEXT",
    # Scoring
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    # Tailoring
    "tailored_resume_path": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    # Cover letter
    "cover_letter_path": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    # Application
    "applied_at": "TEXT",
    "apply_status": "TEXT",
    "apply_error": "TEXT",
    "apply_attempts": "INTEGER DEFAULT 0",
    "agent_id": "TEXT",
    "last_attempted_at": "TEXT",
    "apply_duration_ms": "INTEGER",
    "apply_task_id": "TEXT",
    "verification_confidence": "TEXT",
    # Tracking
    "tracking_status": "TEXT",
    "tracking_updated_at": "TEXT",
    "tracking_doc_path": "TEXT",
    "last_email_at": "TEXT",
    "next_action": "TEXT",
    "next_action_due": "TEXT",
    # Human-in-the-Loop (HITL) apply
    "needs_human_reason": "TEXT",
    "needs_human_url": "TEXT",
    "needs_human_instructions": "TEXT",
    # Apply category (semantic classification of apply outcome)
    "apply_category": "TEXT",
}


def ensure_columns(conn: sqlite3.Connection | None = None) -> list[str]:
    """Add any missing columns to the jobs table (forward migration).

    Reads the current table schema via PRAGMA table_info and compares against
    the full column registry. Any missing columns are added with ALTER TABLE.

    This makes it safe to upgrade the database from any previous version --
    columns are only added, never removed or renamed.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of column names that were added (empty if schema was already current).
    """
    if conn is None:
        conn = get_connection()

    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    added = []

    for col, dtype in _ALL_COLUMNS.items():
        if col not in existing:
            # PRIMARY KEY columns can't be added via ALTER TABLE, but url
            # is always created with the table itself so this is safe
            if "PRIMARY KEY" in dtype:
                continue
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype}")
            added.append(col)

    if added:
        conn.commit()

    return added


# ---------------------------------------------------------------------------
# Apply category classification
# ---------------------------------------------------------------------------

# Error → category mapping. Errors not in any set default to "blocked_technical".
_AUTH_ERRORS = {
    "workday_login_required", "login_issue", "login_required",
    "email_verification", "account_required", "sso_required",
    "account_creation_broken",
}

_INELIGIBLE_ERRORS = {
    "not_eligible_location", "not_eligible_salary", "contract_only",
}

_EXPIRED_ERRORS = {
    "expired", "already_applied",
}

_PLATFORM_ERRORS = {
    "not_a_job_application", "unsafe_permissions", "unsafe_verification",
    "site_blocked", "cloudflare_blocked", "blocked_by_cloudflare",
}

_NO_URL_ERRORS = {
    "no_external_url",
}


def categorize_apply_result(apply_status: str | None,
                            apply_error: str | None) -> str:
    """Derive a semantic apply category from status + error.

    Returns one of: pending, in_progress, applied, needs_human, manual_only,
    blocked_auth, blocked_technical, archived_ineligible, archived_expired,
    archived_platform, archived_no_url.
    """
    if apply_status is None:
        return "pending"
    if apply_status == "applied":
        return "applied"
    if apply_status == "in_progress":
        return "in_progress"
    if apply_status == "needs_human":
        return "needs_human"

    error = apply_error or "unknown"

    # Manual status with a specific error gets recategorized
    if apply_status == "manual":
        if error in _AUTH_ERRORS:
            return "blocked_auth"
        if error in _NO_URL_ERRORS:
            return "archived_no_url"
        return "manual_only"

    # Failed status — classify by error reason
    if error in _AUTH_ERRORS:
        return "blocked_auth"
    if error in _INELIGIBLE_ERRORS:
        return "archived_ineligible"
    if error in _EXPIRED_ERRORS:
        return "archived_expired"
    if error in _PLATFORM_ERRORS:
        return "archived_platform"
    if error in _NO_URL_ERRORS:
        return "archived_no_url"

    # Everything else (captcha, page_error, browser_unavailable, etc.)
    return "blocked_technical"


def backfill_categories(conn: sqlite3.Connection | None = None) -> int:
    """Populate apply_category for all rows where it is NULL but determinable.

    Idempotent — safe to call on every startup. Only updates rows that have
    an apply_status or apply_error set but no category yet.

    Returns:
        Number of rows updated.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT url, apply_status, apply_error FROM jobs "
        "WHERE apply_category IS NULL "
        "  AND (apply_status IS NOT NULL OR apply_error IS NOT NULL)"
    ).fetchall()

    updated = 0
    for row in rows:
        category = categorize_apply_result(row["apply_status"], row["apply_error"])
        conn.execute(
            "UPDATE jobs SET apply_category = ? WHERE url = ?",
            (category, row["url"]),
        )
        updated += 1

    if updated:
        conn.commit()
    return updated


def get_jobs_by_category(category: str,
                         conn: sqlite3.Connection | None = None,
                         limit: int = 100) -> list[dict]:
    """Fetch jobs filtered by apply category.

    Args:
        category: One of the apply_category values (e.g., 'blocked_auth').
        conn: Database connection.
        limit: Maximum rows to return.

    Returns:
        List of job dicts ordered by fit_score DESC.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT * FROM jobs WHERE apply_category = ? "
        "ORDER BY fit_score DESC NULLS LAST, last_attempted_at DESC "
        "LIMIT ?",
        (category, limit),
    ).fetchall()

    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def reset_by_category(category: str,
                      conn: sqlite3.Connection | None = None) -> int:
    """Reset all jobs in a given category so they can be retried.

    Clears apply_status, apply_error, apply_attempts, apply_category,
    and any HITL fields.

    Args:
        category: The apply_category to reset (e.g., 'blocked_technical').

    Returns:
        Number of jobs reset.
    """
    if conn is None:
        conn = get_connection()
    cursor = conn.execute("""
        UPDATE jobs SET apply_status = NULL, apply_error = NULL,
                       apply_attempts = 0, agent_id = NULL,
                       apply_category = NULL,
                       needs_human_reason = NULL,
                       needs_human_url = NULL,
                       needs_human_instructions = NULL
        WHERE apply_category = ?
    """, (category,))
    conn.commit()
    return cursor.rowcount


def get_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return job counts by pipeline stage.

    Provides a snapshot of how many jobs are at each stage, useful for
    dashboard display and pipeline progress tracking.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dictionary with keys:
            total, by_site, pending_detail, with_description,
            scored, unscored, tailored, untailored_eligible,
            with_cover_letter, applied, score_distribution
    """
    if conn is None:
        conn = get_connection()

    stats: dict = {}

    # Total jobs
    stats["total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # By site breakdown
    rows = conn.execute(
        "SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC"
    ).fetchall()
    stats["by_site"] = [(row[0], row[1]) for row in rows]

    # Enrichment stage
    stats["pending_detail"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL"
    ).fetchone()[0]

    stats["with_description"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
    ).fetchone()[0]

    stats["detail_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL"
    ).fetchone()[0]

    # Scoring stage
    stats["scored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]

    stats["unscored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL AND fit_score IS NULL"
    ).fetchone()[0]

    # Score distribution
    dist_rows = conn.execute(
        "SELECT fit_score, COUNT(*) as cnt FROM jobs "
        "WHERE fit_score IS NOT NULL "
        "GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    stats["score_distribution"] = [(row[0], row[1]) for row in dist_rows]

    # Tailoring stage
    stats["tailored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
    ).fetchone()[0]

    stats["untailored_eligible"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE fit_score >= 7 AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    stats["tailor_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(tailor_attempts, 0) >= 5 "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    # Cover letter stage
    stats["with_cover_letter"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE cover_letter_path IS NOT NULL"
    ).fetchone()[0]

    stats["cover_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(cover_attempts, 0) >= 5 "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '')"
    ).fetchone()[0]

    # Application stage
    stats["applied"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"
    ).fetchone()[0]

    stats["apply_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_error IS NOT NULL"
    ).fetchone()[0]

    stats["ready_to_apply"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE tailored_resume_path IS NOT NULL "
        "AND applied_at IS NULL "
        "AND application_url IS NOT NULL"
    ).fetchone()[0]

    stats["needs_human"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'needs_human'"
    ).fetchone()[0]

    # Apply category breakdown
    cat_rows = conn.execute(
        "SELECT apply_category, COUNT(*) as cnt FROM jobs "
        "WHERE apply_category IS NOT NULL "
        "GROUP BY apply_category ORDER BY cnt DESC"
    ).fetchall()
    stats["by_category"] = {row[0]: row[1] for row in cat_rows}

    # Per-score funnel: breakdown of pipeline stage at each score level (6-10)
    funnel_rows = conn.execute("""
        SELECT
            fit_score,
            SUM(CASE WHEN applied_at IS NOT NULL THEN 1 ELSE 0 END)            AS applied,
            SUM(CASE WHEN applied_at IS NULL
                      AND cover_letter_path IS NOT NULL
                      AND COALESCE(apply_status,'') NOT IN ('applied','manual','needs_human')
                 THEN 1 ELSE 0 END)                                             AS cover_ready,
            SUM(CASE WHEN applied_at IS NULL
                      AND tailored_resume_path IS NOT NULL
                      AND (cover_letter_path IS NULL OR cover_letter_path = '')
                      AND COALESCE(apply_status,'') NOT IN ('applied','manual','needs_human')
                 THEN 1 ELSE 0 END)                                             AS tailored,
            SUM(CASE WHEN applied_at IS NULL
                      AND tailored_resume_path IS NULL
                      AND full_description IS NOT NULL
                      AND COALESCE(apply_status,'') NOT IN ('applied','manual')
                 THEN 1 ELSE 0 END)                                             AS needs_tailor,
            SUM(CASE WHEN apply_error IS NOT NULL THEN 1 ELSE 0 END)           AS errors
        FROM jobs
        WHERE fit_score >= 6
        GROUP BY fit_score
        ORDER BY fit_score DESC
    """).fetchall()
    stats["score_funnel"] = [
        {"score": row[0], "applied": row[1], "cover_ready": row[2],
         "tailored": row[3], "needs_tailor": row[4], "errors": row[5]}
        for row in funnel_rows
    ]

    return stats


def extract_company(application_url: str | None) -> str | None:
    """Extract a company name from an application URL domain.

    Handles common ATS patterns:
      - Workday:     {company}.wd*.myworkdayjobs.com
      - Greenhouse:  job-boards.greenhouse.io/{company}/...
      - Lever:       jobs.lever.co/{company}/...
      - iCIMS:       careers-{company}.icims.com
      - Jobvite:     jobs.jobvite.com/en/{company}/...
      - Direct:      careers.{company}.com, {company}.com/careers
    """
    if not application_url:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(application_url)
        host = parsed.hostname or ""
        path = parsed.path or ""

        # Workday: workiva.wd503.myworkdayjobs.com → workiva
        if "myworkdayjobs.com" in host:
            return host.split(".")[0].lower()

        # Greenhouse job boards: job-boards.greenhouse.io/hudl/... → hudl
        if "greenhouse.io" in host and "/job_boards/" not in path:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].lower()

        # Lever: jobs.lever.co/LuminDigital/... → lumindigital
        if "lever.co" in host:
            parts = [p for p in path.split("/") if p]
            if parts:
                return parts[0].lower()

        # iCIMS: careers-mercuryinsurance.icims.com → mercuryinsurance
        if "icims.com" in host:
            prefix = host.split(".icims.com")[0]
            prefix = prefix.replace("careers-", "").replace("careers.", "")
            return prefix.lower() if prefix else None

        # Jobvite: jobs.jobvite.com/en/company/... → company
        if "jobvite.com" in host:
            parts = [p for p in path.split("/") if p and p != "en"]
            if parts:
                return parts[0].lower()

        # Oracle Cloud ATS: skip (company not in URL)
        if "oraclecloud.com" in host:
            return None

        # Greenhouse short URLs: grnh.se → skip
        if host == "grnh.se":
            return None

        # Direct company domains: jobs.twilio.com → twilio
        # careers.ascensus.com → ascensus
        # www.kentik.com/careers → kentik
        # Skip major job boards / ATS platforms
        skip_domains = {
            "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
            "dice.com", "simplyhired.com", "monster.com", "careerjet.ca",
            "talent.com", "jobbank.gc.ca", "wellfound.com",
        }
        if any(host.endswith(d) for d in skip_domains):
            return None

        # Strip common subdomains
        parts = host.split(".")
        if len(parts) >= 2:
            # jobs.twilio.com → twilio, careers.foo.com → foo, www.foo.com → foo
            if parts[0] in ("jobs", "careers", "career", "www", "apply", "hire"):
                company = parts[1]
            else:
                # foo.com → foo
                company = parts[-2]
            # Skip generic TLDs as company names
            if company not in ("com", "org", "net", "io", "co", "ca"):
                return company.lower()

        return None
    except Exception:
        return None


def backfill_companies(conn: sqlite3.Connection | None = None) -> int:
    """Populate the company column for all jobs that have an application_url but no company."""
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT url, application_url FROM jobs WHERE company IS NULL AND application_url IS NOT NULL"
    ).fetchall()

    updated = 0
    for row in rows:
        company = extract_company(row[1])
        if company:
            conn.execute("UPDATE jobs SET company = ? WHERE url = ?", (company, row[0]))
            updated += 1

    if updated:
        conn.commit()
    return updated


def _resolve_url(url: str, site: str) -> str | None:
    """Resolve a relative URL to absolute using the site's base URL.

    Returns the absolute URL, or None if it can't be resolved.
    """
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url

    # Lazy-load base URLs to avoid circular imports
    from applypilot.config import load_base_urls
    base = load_base_urls().get(site)
    if base:
        return urljoin(base, url)
    return None


def store_jobs(conn: sqlite3.Connection, jobs: list[dict],
               site: str, strategy: str) -> tuple[int, int]:
    """Store discovered jobs, skipping duplicates by URL.

    Relative URLs are resolved to absolute using base_urls from sites.yaml.
    Jobs with unresolvable relative URLs are skipped.

    Args:
        conn: Database connection.
        jobs: List of job dicts with keys: url, title, salary, description, location.
        site: Source site name (e.g. "RemoteOK", "Dice").
        strategy: Extraction strategy used (e.g. "json_ld", "api_response", "css_selectors").

    Returns:
        Tuple of (new_count, duplicate_count).
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        url = job.get("url")
        if not url:
            continue

        # Normalize relative URLs to absolute
        url = _resolve_url(url, site) or url
        # Skip URLs that are still relative (unresolvable)
        if not url.startswith("http://") and not url.startswith("https://"):
            continue

        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, strategy, discovered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (url, job.get("title"), job.get("salary"), job.get("description"),
                 job.get("location"), site, strategy, now),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing


def store_account(conn: sqlite3.Connection, account: dict,
                  job_url: str | None = None) -> None:
    """Store a newly created account in the accounts table.

    Args:
        conn: Database connection.
        account: Dict with keys: site, domain, email, password.
        job_url: The job URL that triggered this account creation.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO accounts (site, domain, email, password, created_at, job_url, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            account.get("site", "unknown"),
            account.get("domain", "unknown"),
            account.get("email", ""),
            account.get("password", ""),
            now,
            job_url,
            account.get("notes"),
        ),
    )
    conn.commit()


def get_accounts_for_prompt(conn: sqlite3.Connection | None = None) -> dict[str, dict]:
    """Return saved accounts as {domain: {email, password}} for prompt injection.

    Supports subdomain fallback: a query for 'fico.wd1.myworkdayjobs.com'
    first checks for an exact match, then falls back to 'myworkdayjobs.com'.
    """
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT domain, email, password FROM accounts ORDER BY created_at DESC"
    ).fetchall()
    # Build lookup: most recent account per domain wins
    accounts: dict[str, dict] = {}
    for row in rows:
        domain = row["domain"]
        if domain not in accounts:
            accounts[domain] = {"email": row["email"], "password": row["password"] or ""}
    return accounts


def get_jobs_by_stage(conn: sqlite3.Connection | None = None,
                      stage: str = "discovered",
                      min_score: int | None = None,
                      limit: int = 100) -> list[dict]:
    """Fetch jobs filtered by pipeline stage.

    Args:
        conn: Database connection. Uses get_connection() if None.
        stage: One of "discovered", "enriched", "scored", "tailored", "applied".
        min_score: Minimum fit_score filter (only relevant for scored+ stages).
        limit: Maximum number of rows to return.

    Returns:
        List of job dicts.
    """
    if conn is None:
        conn = get_connection()

    conditions = {
        "discovered": "1=1",
        "pending_detail": "detail_scraped_at IS NULL",
        "enriched": "full_description IS NOT NULL",
        "pending_score": "full_description IS NOT NULL AND fit_score IS NULL",
        "scored": "fit_score IS NOT NULL",
        "pending_tailor": (
            "fit_score >= ? AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts, 0) < 5"
        ),
        "tailored": "tailored_resume_path IS NOT NULL",
        "pending_apply": (
            "tailored_resume_path IS NOT NULL AND applied_at IS NULL "
            "AND application_url IS NOT NULL"
        ),
        "applied": "applied_at IS NOT NULL",
    }

    where = conditions.get(stage, "1=1")
    params: list = []

    if "?" in where and min_score is not None:
        params.append(min_score)
    elif "?" in where:
        params.append(7)  # default min_score

    if min_score is not None and "fit_score" not in where and stage in ("scored", "tailored", "applied"):
        where += " AND fit_score >= ?"
        params.append(min_score)

    query = f"""
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(site, 'unknown')
                ORDER BY discovered_at DESC
            ) AS _site_rank
            FROM jobs WHERE {where}
        )
        ORDER BY fit_score DESC NULLS LAST, _site_rank ASC, discovered_at DESC
    """
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()

    # Convert sqlite3.Row objects to dicts
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_needs_human_jobs(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return all jobs parked for human review, ordered by fit_score DESC."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute("""
        SELECT url, title, site, company, application_url, fit_score,
               needs_human_reason, needs_human_url, needs_human_instructions,
               tailored_resume_path, cover_letter_path, last_attempted_at
        FROM jobs
        WHERE apply_status = 'needs_human'
        ORDER BY fit_score DESC NULLS LAST, last_attempted_at DESC
    """).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


# ---------------------------------------------------------------------------
# Tracking helpers
# ---------------------------------------------------------------------------


def get_applied_jobs(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return all applied jobs with columns needed for email matching."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT url, title, company, application_url, applied_at, site, "
        "       tracking_status, last_email_at "
        "FROM jobs WHERE applied_at IS NOT NULL "
        "ORDER BY applied_at DESC"
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def create_stub_job(email: dict, classification: str,
                    conn: sqlite3.Connection | None = None) -> str:
    """Create a minimal job entry from an unmatched application email.

    Used for manually applied jobs that aren't in the pipeline DB.
    The URL is synthesized as 'manual://{sender_domain}/{hash}' to
    serve as a unique key.

    Args:
        email: Normalized email dict with sender, subject, date, etc.
        classification: The LLM classification (confirmation, rejection, etc.)

    Returns:
        The generated job URL (primary key).
    """
    import hashlib

    if conn is None:
        conn = get_connection()

    # Extract company from sender domain
    sender = email.get("sender", "")
    domain = sender.split("@")[-1] if "@" in sender else "unknown"
    company = domain.split(".")[0] if "." in domain else domain

    # Build a stable synthetic URL
    subject = email.get("subject", "")
    raw = f"{sender}:{subject}"
    url_hash = hashlib.md5(raw.encode()).hexdigest()[:12]
    url = f"manual://{domain}/{url_hash}"

    # Check if already exists
    existing = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    if existing:
        return url

    # Infer a title from the subject line
    title = subject
    # Strip common prefixes
    for prefix in ("Thank you for your application to ",
                   "Thank you for applying to ",
                   "Thank you for your interest in ",
                   "Your application to ",
                   "Application received: ",
                   "Re: "):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):]
            break

    now = datetime.now(timezone.utc).isoformat()
    email_date = email.get("date", now)

    conn.execute(
        "INSERT INTO jobs (url, title, company, site, applied_at, apply_status, "
        "                  discovered_at, tracking_status, tracking_updated_at) "
        "VALUES (?, ?, ?, 'manual', ?, 'applied', ?, ?, ?)",
        (url, title.strip() or "Unknown Position", company, email_date, now,
         classification, now),
    )
    conn.commit()
    return url


def email_already_tracked(email_id: str, conn: sqlite3.Connection | None = None) -> bool:
    """Check if a Gmail message ID already exists in tracking_emails."""
    if conn is None:
        conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM tracking_emails WHERE email_id = ?", (email_id,)
    ).fetchone()
    return row is not None


def store_tracking_email(email: dict, conn: sqlite3.Connection | None = None) -> None:
    """Insert a classified email into tracking_emails.

    Args:
        email: Dict with keys matching tracking_emails columns.
    """
    if conn is None:
        conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO tracking_emails "
        "(email_id, thread_id, job_url, sender, sender_name, subject, "
        " received_at, snippet, body_text, classification, extracted_data, classified_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            email["email_id"], email.get("thread_id"), email["job_url"],
            email.get("sender"), email.get("sender_name"), email.get("subject"),
            email.get("received_at"), email.get("snippet"),
            email.get("body_text", "")[:10000],
            email.get("classification"), email.get("extracted_data"),
            email.get("classified_at"),
        ),
    )
    conn.commit()


def store_tracking_person(person: dict, conn: sqlite3.Connection | None = None) -> None:
    """Insert a contact person into tracking_people (ignore duplicates)."""
    if conn is None:
        conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO tracking_people "
        "(job_url, name, title, email, source_email_id, first_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            person["job_url"], person.get("name"), person.get("title"),
            person.get("email"), person.get("source_email_id"),
            person.get("first_seen_at"),
        ),
    )
    conn.commit()


_TRACKING_PRIORITY = {
    "ghosted": 1, "rejection": 2, "confirmation": 3,
    "follow_up": 4, "interview": 5, "offer": 6,
}


def update_tracking_status(job_url: str, new_status: str,
                           conn: sqlite3.Connection | None = None) -> bool:
    """Update a job's tracking_status if the new status has higher priority.

    Returns True if the status was updated.
    """
    if conn is None:
        conn = get_connection()
    row = conn.execute(
        "SELECT tracking_status FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()
    if row is None:
        return False

    current = row["tracking_status"]
    current_pri = _TRACKING_PRIORITY.get(current, 0)
    new_pri = _TRACKING_PRIORITY.get(new_status, 0)

    if new_pri > current_pri:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET tracking_status = ?, tracking_updated_at = ? WHERE url = ?",
            (new_status, now, job_url),
        )
        conn.commit()
        return True
    return False


def update_job_tracking_fields(job_url: str, fields: dict,
                               conn: sqlite3.Connection | None = None) -> None:
    """Update arbitrary tracking fields on a job row."""
    if conn is None:
        conn = get_connection()
    if not fields:
        return
    set_clauses = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_url]
    conn.execute(f"UPDATE jobs SET {set_clauses} WHERE url = ?", values)
    conn.commit()


def get_tracking_emails(job_url: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all tracking emails for a job, ordered by received_at."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tracking_emails WHERE job_url = ? ORDER BY received_at ASC",
        (job_url,),
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_tracking_people(job_url: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all tracking contacts for a job."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tracking_people WHERE job_url = ? ORDER BY first_seen_at ASC",
        (job_url,),
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_action_items(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get all jobs with pending action items, sorted by deadline."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT url, title, company, tracking_status, next_action, next_action_due "
        "FROM jobs WHERE next_action IS NOT NULL "
        "ORDER BY CASE WHEN next_action_due IS NULL THEN 1 ELSE 0 END, next_action_due ASC"
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_tracking_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return tracking status counts for the dashboard."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT tracking_status, COUNT(*) as cnt FROM jobs "
        "WHERE tracking_status IS NOT NULL "
        "GROUP BY tracking_status ORDER BY cnt DESC"
    ).fetchall()
    return {row["tracking_status"]: row["cnt"] for row in rows}


# ---------------------------------------------------------------------------
# Q&A Knowledge Base
# ---------------------------------------------------------------------------

import hashlib
import re as _re


def normalize_question(text: str) -> str:
    """Normalize a screening question for matching.

    Strips whitespace, punctuation, lowercases, collapses whitespace.
    """
    text = text.lower().strip()
    text = _re.sub(r'[^\w\s]', '', text)
    text = _re.sub(r'\s+', ' ', text)
    return text


def question_key(text: str) -> str:
    """Generate a stable hash key for a normalized question."""
    normalized = normalize_question(text)
    return hashlib.md5(normalized.encode()).hexdigest()


def store_qa(question: str, answer: str, source: str = "agent",
             field_type: str | None = None,
             options_json: str | None = None,
             ats_slug: str | None = None,
             job_url: str | None = None,
             conn: sqlite3.Connection | None = None) -> int | None:
    """Store a Q&A pair in the knowledge base (upsert by question_key + answer).

    Returns:
        The row ID of the inserted/existing row, or None on failure.
    """
    if conn is None:
        conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    key = question_key(question)
    try:
        conn.execute(
            "INSERT INTO qa_knowledge "
            "(question_text, question_key, answer_text, answer_source, "
            " field_type, options_json, ats_slug, job_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(question_key, answer_text) DO UPDATE SET "
            "  updated_at = ?, ats_slug = COALESCE(excluded.ats_slug, ats_slug)",
            (question, key, answer, source,
             field_type, options_json, ats_slug, job_url, now,
             now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM qa_knowledge WHERE question_key = ? AND answer_text = ?",
            (key, answer),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def lookup_qa(question: str,
              conn: sqlite3.Connection | None = None) -> list[dict]:
    """Find known answers for a screening question.

    Returns answers sorted by outcome preference: accepted > unknown > rejected.
    """
    if conn is None:
        conn = get_connection()
    key = question_key(question)
    rows = conn.execute(
        "SELECT * FROM qa_knowledge WHERE question_key = ? "
        "ORDER BY CASE outcome "
        "  WHEN 'accepted' THEN 1 "
        "  WHEN 'unknown' THEN 2 "
        "  WHEN 'rejected' THEN 3 "
        "  ELSE 4 END, "
        "updated_at DESC NULLS LAST",
        (key,),
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_qa(question: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Return the best known answer for a question, or None if not found.

    Looks up by normalized question key and returns the answer with the
    best outcome (accepted > unknown > rejected).
    """
    if conn is None:
        conn = get_connection()
    key = question_key(question)
    row = conn.execute(
        "SELECT answer_text FROM qa_knowledge "
        "WHERE question_key = ? "
        "ORDER BY CASE outcome "
        "  WHEN 'accepted' THEN 1 "
        "  WHEN 'unknown' THEN 2 "
        "  WHEN 'rejected' THEN 3 "
        "  ELSE 4 END "
        "LIMIT 1",
        (key,),
    ).fetchone()
    return row[0] if row else None


def get_all_qa(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return all Q&A pairs, grouped by question, best answer first."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM qa_knowledge "
        "ORDER BY question_key, "
        "CASE outcome "
        "  WHEN 'accepted' THEN 1 "
        "  WHEN 'unknown' THEN 2 "
        "  WHEN 'rejected' THEN 3 "
        "  ELSE 4 END"
    ).fetchall()
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def mark_qa_outcome(job_url: str, outcome: str,
                    conn: sqlite3.Connection | None = None) -> int:
    """Bulk update outcome for all Q&A from a specific job.

    Args:
        job_url: The job URL whose Q&A pairs to update.
        outcome: 'accepted', 'rejected', or 'unknown'.

    Returns:
        Number of rows updated.
    """
    if conn is None:
        conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "UPDATE qa_knowledge SET outcome = ?, updated_at = ? WHERE job_url = ?",
        (outcome, now, job_url),
    )
    conn.commit()
    return cursor.rowcount


def get_qa_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return Q&A knowledge base statistics."""
    if conn is None:
        conn = get_connection()
    stats: dict = {}
    stats["total"] = conn.execute("SELECT COUNT(*) FROM qa_knowledge").fetchone()[0]
    stats["unique_questions"] = conn.execute(
        "SELECT COUNT(DISTINCT question_key) FROM qa_knowledge"
    ).fetchone()[0]

    # By outcome
    rows = conn.execute(
        "SELECT outcome, COUNT(*) FROM qa_knowledge GROUP BY outcome"
    ).fetchall()
    stats["by_outcome"] = {row[0]: row[1] for row in rows}

    # By source
    rows = conn.execute(
        "SELECT answer_source, COUNT(*) FROM qa_knowledge GROUP BY answer_source"
    ).fetchall()
    stats["by_source"] = {row[0]: row[1] for row in rows}

    return stats


def export_qa_yaml(conn: sqlite3.Connection | None = None) -> str:
    """Export all Q&A pairs as YAML for user editing.

    Returns:
        YAML string with questions grouped and answers listed.
    """
    qa_list = get_all_qa(conn)
    if not qa_list:
        return "# No Q&A pairs yet.\n"

    lines = ["# ApplyPilot Q&A Knowledge Base", "# Edit answers below, then import with: applypilot qa import <file>", ""]
    current_key = None
    for qa in qa_list:
        if qa["question_key"] != current_key:
            current_key = qa["question_key"]
            lines.append(f"- question: \"{qa['question_text']}\"")
            if qa.get("field_type"):
                lines.append(f"  field_type: {qa['field_type']}")
            if qa.get("options_json"):
                lines.append(f"  options: {qa['options_json']}")
            lines.append("  answers:")
        outcome_tag = f" [{qa['outcome']}]" if qa["outcome"] != "unknown" else ""
        lines.append(f"    - text: \"{qa['answer_text']}\"{outcome_tag}")
    lines.append("")
    return "\n".join(lines)
