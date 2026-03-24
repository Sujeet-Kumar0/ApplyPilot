"""Segments DAO — CRUD for atomic resume segments.

SRP: Only persists/retrieves segments. No LLM calls, no business logic.
All queries are user_id-scoped for multi-tenant safety.

Tree structure:
    root
    ├── summary
    ├── experience (per company)
    │   └── bullet (per highlight)
    ├── skill_group (per skill category)
    ├── education (per institution)
    └── project (per project)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


# ── DTO ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Segment:
    """Atomic resume segment. Pure data, no behavior."""

    id: str
    type: str  # root | summary | experience | bullet | skill_group | education | project
    parent_id: str | None
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    sort_order: int = 0


# ── DAO ──────────────────────────────────────────────────────────────────

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS segments (
    id          TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL,
    parent_id   TEXT,
    content     TEXT NOT NULL,
    tags        TEXT DEFAULT '[]',
    metadata    TEXT DEFAULT '{}',
    sort_order  INTEGER DEFAULT 0,
    PRIMARY KEY (id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_seg_user    ON segments(user_id);
CREATE INDEX IF NOT EXISTS idx_seg_parent  ON segments(user_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_seg_type    ON segments(user_id, type);
"""

_TREE_SQL = """\
WITH RECURSIVE tree AS (
    SELECT id, type, parent_id, content, tags, metadata, sort_order, 0 AS depth
    FROM segments WHERE id = ? AND user_id = ?
    UNION ALL
    SELECT s.id, s.type, s.parent_id, s.content, s.tags, s.metadata, s.sort_order, t.depth + 1
    FROM segments s JOIN tree t ON s.parent_id = t.id
    WHERE s.user_id = ?
)
SELECT * FROM tree ORDER BY depth, sort_order;
"""


class SegmentsRepo:
    """User-scoped CRUD for resume segments."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._uid = user_id
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA)

    # ── Write ────────────────────────────────────────────────────────

    def save(self, segment: Segment) -> None:
        """Insert or replace a single segment."""
        self._conn.execute(
            "INSERT OR REPLACE INTO segments "
            "(id, user_id, type, parent_id, content, tags, metadata, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (segment.id, self._uid, segment.type, segment.parent_id,
             segment.content, json.dumps(segment.tags),
             json.dumps(segment.metadata), segment.sort_order),
        )
        self._conn.commit()

    def save_many(self, segments: list[Segment]) -> None:
        """Batch insert/replace segments."""
        self._conn.executemany(
            "INSERT OR REPLACE INTO segments "
            "(id, user_id, type, parent_id, content, tags, metadata, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(s.id, self._uid, s.type, s.parent_id, s.content,
              json.dumps(s.tags), json.dumps(s.metadata), s.sort_order)
             for s in segments],
        )
        self._conn.commit()

    def delete_tree(self, root_id: str) -> int:
        """Delete a segment and all descendants. Returns count deleted."""
        tree = self.get_tree(root_id)
        if not tree:
            return 0
        ids = [s.id for s in tree]
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"DELETE FROM segments WHERE user_id = ? AND id IN ({placeholders})",
            [self._uid, *ids],
        )
        self._conn.commit()
        return len(ids)

    def delete_all(self) -> int:
        """Delete all segments for this user. Returns count deleted."""
        cur = self._conn.execute(
            "DELETE FROM segments WHERE user_id = ?", (self._uid,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── Read ─────────────────────────────────────────────────────────

    def get(self, segment_id: str) -> Segment | None:
        """Retrieve a single segment by ID."""
        row = self._conn.execute(
            "SELECT * FROM segments WHERE id = ? AND user_id = ?",
            (segment_id, self._uid),
        ).fetchone()
        return _to_dto(row) if row else None

    def get_tree(self, root_id: str) -> list[Segment]:
        """Retrieve full segment tree from root (recursive CTE)."""
        rows = self._conn.execute(
            _TREE_SQL, (root_id, self._uid, self._uid),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def get_children(self, parent_id: str) -> list[Segment]:
        """Retrieve direct children of a segment."""
        rows = self._conn.execute(
            "SELECT * FROM segments WHERE parent_id = ? AND user_id = ? ORDER BY sort_order",
            (parent_id, self._uid),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def get_by_type(self, seg_type: str) -> list[Segment]:
        """Retrieve all segments of a given type."""
        rows = self._conn.execute(
            "SELECT * FROM segments WHERE type = ? AND user_id = ? ORDER BY sort_order",
            (seg_type, self._uid),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def get_by_tags(self, tags: list[str]) -> list[Segment]:
        """Retrieve segments matching ANY of the given tags."""
        rows = self._conn.execute(
            "SELECT * FROM segments WHERE user_id = ? ORDER BY sort_order",
            (self._uid,),
        ).fetchall()
        # Filter in Python — SQLite JSON functions vary by version
        result = []
        for r in rows:
            seg = _to_dto(r)
            if any(t in seg.tags for t in tags):
                result.append(seg)
        return result

    def get_roots(self) -> list[Segment]:
        """Retrieve all root segments (parent_id IS NULL)."""
        rows = self._conn.execute(
            "SELECT * FROM segments WHERE parent_id IS NULL AND user_id = ? ORDER BY sort_order",
            (self._uid,),
        ).fetchall()
        return [_to_dto(r) for r in rows]


# ── Mapping ──────────────────────────────────────────────────────────────

def _to_dto(row: sqlite3.Row) -> Segment:
    return Segment(
        id=row["id"],
        type=row["type"],
        parent_id=row["parent_id"],
        content=row["content"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        sort_order=row["sort_order"] or 0,
    )
