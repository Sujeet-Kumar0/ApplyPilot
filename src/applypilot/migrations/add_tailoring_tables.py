"""Migration: add_tailoring_tables

Creates two new tables to support the config-driven tailoring system:

- tailoring_history: stores historical tailoring attempts (JSON columns stored as TEXT)
- role_notes: cumulative notes and lessons learned per role_type

This migration follows the connection and error-handling patterns used in
applypilot.database.get_connection() and friends. It provides a single
function `run_migration()` that can be imported and executed by any migration
runner or called manually from tests.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from applypilot.database import get_connection
from applypilot.config import DB_PATH


def _create_tables(conn: sqlite3.Connection) -> None:
    """Execute the CREATE TABLE statements for the new tailoring tables.

    Args:
        conn: Active sqlite3.Connection. Caller is responsible for commit on
              success.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tailoring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_url TEXT,
            role_type TEXT,
            variant_used TEXT,
            step_outputs TEXT,
            gate_results TEXT,
            agent_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS role_notes (
            role_type TEXT PRIMARY KEY,
            notes TEXT,
            lessons_learned TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def run_migration(db_path: Optional[Path | str] = None) -> None:
    """Run the tailoring tables migration.

    Uses the same connection handling as applypilot.database.get_connection()
    so that thread-local connections and PRAGMAs are applied.

    Args:
        db_path: Optional path to the sqlite database file. If omitted, uses
                 applypilot.config.DB_PATH.

    Raises:
        sqlite3.DatabaseError: on SQL execution errors (propagated after
                               rollback)
    """
    path = db_path or DB_PATH

    # Ensure parent directory exists to match init_db behaviour
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path)
    try:
        _create_tables(conn)
        conn.commit()
    except sqlite3.DatabaseError:
        # Rollback to leave DB in a consistent state then re-raise so callers
        # can surface the failure.
        try:
            conn.rollback()
        except Exception:
            # Best-effort rollback; ignore secondary errors but re-raise
            pass
        raise


if __name__ == "__main__":
    # Allow running as a script for convenience during development and tests
    run_migration()
