"""Bullet bank: SQLite-backed storage for resume bullet points and their variants."""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from applypilot.tailoring.models import Bullet


class BulletBank:
    """Persistent storage for resume bullets with usage tracking."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bullets (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    context TEXT,
                    tags TEXT,
                    metrics TEXT,
                    created_at TEXT,
                    use_count INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bullet_id TEXT NOT NULL,
                    job_title TEXT,
                    outcome TEXT,
                    created_at TEXT,
                    FOREIGN KEY (bullet_id) REFERENCES bullets(id)
                )
            """)

    def add_bullet(
        self,
        text: str,
        context: Optional[dict] = None,
        tags: Optional[list] = None,
        metrics: Optional[list] = None,
    ) -> Bullet:
        """Add a new bullet to the bank and return it."""
        bullet = Bullet(
            id=str(uuid.uuid4()),
            text=text,
            context=context or {},
            tags=tags or [],
            metrics=metrics or [],
            created_at=datetime.now(),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO bullets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bullet.id,
                    bullet.text,
                    json.dumps(bullet.context),
                    json.dumps(bullet.tags),
                    json.dumps(bullet.metrics),
                    bullet.created_at.isoformat(),
                    bullet.use_count,
                    bullet.success_rate,
                ),
            )
        return bullet

    def get_bullet(self, bullet_id: str) -> Optional[Bullet]:
        """Retrieve a single bullet by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM bullets WHERE id = ?", (bullet_id,)).fetchone()
        if not row:
            return None
        return self._row_to_bullet(row)

    def get_variants(self, tags: Optional[List[str]] = None) -> List[Bullet]:
        """Retrieve bullets, optionally filtered by tags."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM bullets ORDER BY success_rate DESC").fetchall()

        bullets = [self._row_to_bullet(row) for row in rows]
        if tags:
            bullets = [b for b in bullets if any(t in b.tags for t in tags)]
        return bullets

    def record_feedback(self, bullet_id: str, job_title: str, outcome: str) -> None:
        """Record usage feedback for a bullet (e.g. 'selected', 'rejected')."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO feedback (bullet_id, job_title, outcome, created_at) "
                "VALUES (?, ?, ?, ?)",
                (bullet_id, job_title, outcome, datetime.now().isoformat()),
            )
            # Update use_count
            conn.execute(
                "UPDATE bullets SET use_count = use_count + 1 WHERE id = ?",
                (bullet_id,),
            )
            # Recalculate success rate from all feedback
            total = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE bullet_id = ?",
                (bullet_id,),
            ).fetchone()[0]
            successes = conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE bullet_id = ? AND outcome = 'selected'",
                (bullet_id,),
            ).fetchone()[0]
            rate = successes / total if total > 0 else 0.0
            conn.execute(
                "UPDATE bullets SET success_rate = ? WHERE id = ?",
                (rate, bullet_id),
            )

    def _row_to_bullet(self, row: tuple) -> Bullet:
        """Convert a database row to a Bullet dataclass."""
        return Bullet(
            id=row[0],
            text=row[1],
            context=json.loads(row[2]) if row[2] else {},
            tags=json.loads(row[3]) if row[3] else [],
            metrics=json.loads(row[4]) if row[4] else [],
            created_at=datetime.fromisoformat(row[5]) if row[5] else datetime.now(),
            use_count=row[6] or 0,
            success_rate=row[7] or 0.0,
        )
