"""Path constants — all user-specific and package-shipped paths."""

from __future__ import annotations

import os
from pathlib import Path

# User data directory — all user-specific files live here
APP_DIR = Path(os.environ.get("APPLYPILOT_DIR", Path.home() / ".applypilot"))

# Core paths
DB_PATH = APP_DIR / "applypilot.db"
PROFILE_PATH = APP_DIR / "profile.json"
RESUME_JSON_PATH = APP_DIR / "resume.json"
RESUME_PATH = APP_DIR / "resume.txt"
RESUME_PDF_PATH = APP_DIR / "resume.pdf"
SEARCH_CONFIG_PATH = APP_DIR / "searches.yaml"
ENV_PATH = APP_DIR / ".env"

# Generated output
TAILORED_DIR = APP_DIR / "tailored_resumes"
COVER_LETTER_DIR = APP_DIR / "cover_letters"
TRACKING_DIR = APP_DIR / "tracking"
LOG_DIR = APP_DIR / "logs"

# Chrome worker isolation
CHROME_WORKER_DIR = APP_DIR / "chrome-workers"
APPLY_WORKER_DIR = APP_DIR / "apply-workers"
OPENCODE_CONFIG_DIR = APP_DIR / ".opencode"
OPENCODE_CONFIG_PATH = OPENCODE_CONFIG_DIR / "opencode.jsonc"
SESSIONS_DIR = APP_DIR / "chrome-sessions"

# Optional documents (profile photo, certs, ID, etc.)
FILES_DIR = APP_DIR / "files"

# Package-shipped config (YAML registries)
PACKAGE_DIR = Path(__file__).resolve().parent.parent  # applypilot/
CONFIG_DIR = PACKAGE_DIR / "config"


def ensure_dirs():
    """Create all required directories."""
    for d in [
        APP_DIR,
        TAILORED_DIR,
        COVER_LETTER_DIR,
        TRACKING_DIR,
        LOG_DIR,
        CHROME_WORKER_DIR,
        APPLY_WORKER_DIR,
        SESSIONS_DIR,
        FILES_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
