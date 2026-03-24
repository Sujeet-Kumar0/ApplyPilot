"""SQLite connection management.

SRP: Only manages connections, WAL mode, thread-local caching.
Extracted from database.py for reuse across all DAOs.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from applypilot.config import APP_DIR

DB_PATH = APP_DIR / "applypilot.db"

_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Thread-local cached SQLite connection with WAL mode.

    Args:
        db_path: Override default DB_PATH. Useful for testing.

    Returns:
        Configured sqlite3.Connection with row_factory.
    """
    path = str(db_path or DB_PATH)

    if not hasattr(_local, "connections"):
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
    if hasattr(_local, "connections"):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()
