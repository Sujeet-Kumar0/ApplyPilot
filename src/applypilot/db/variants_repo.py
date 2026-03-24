"""Variants DAO — CRUD for pre-generated resume variants.

SRP: Only persists/retrieves variants. No LLM calls, no assembly logic.
All queries are user_id-scoped for multi-tenant safety.

A variant is a named combination of segments assembled into a role-specific
resume. Variants are generated once, reviewed by human, then reused across
matching jobs in the apply pipeline.

Lifecycle: generated → pending_review → approved | rejected
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


# ── DTO ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Variant:
    """Pre-generated resume variant. Pure data, no behavior."""

    id: str
    name: str                          # e.g. "backend_engineer", "android_sde"
    role_tags: list[str]               # e.g. ["backend", "java", "distributed"]
    segment_ids: list[str]             # ordered list of segment IDs composing this variant
    assembled_text: str                # final plain-text resume (cached)
    status: str = "pending_review"     # pending_review | approved | rejected
    metadata: dict[str, Any] = field(default_factory=dict)


# ── DAO ──────────────────────────────────────────────────────────────────

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS variants (
    id              TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    role_tags       TEXT DEFAULT '[]',
    segment_ids     TEXT DEFAULT '[]',
    assembled_text  TEXT NOT NULL,
    status          TEXT DEFAULT 'pending_review',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     TEXT,
    PRIMARY KEY (id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_var_user   ON variants(user_id);
CREATE INDEX IF NOT EXISTS idx_var_status ON variants(user_id, status);
CREATE INDEX IF NOT EXISTS idx_var_name   ON variants(user_id, name);
"""


class VariantsRepo:
    """User-scoped CRUD for resume variants."""

    def __init__(self, conn: sqlite3.Connection, user_id: str) -> None:
        self._conn = conn
        self._uid = user_id
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(_SCHEMA)

    # ── Write ────────────────────────────────────────────────────────

    def save(self, variant: Variant) -> None:
        """Insert or replace a variant."""
        self._conn.execute(
            "INSERT OR REPLACE INTO variants "
            "(id, user_id, name, role_tags, segment_ids, assembled_text, status, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (variant.id, self._uid, variant.name,
             json.dumps(variant.role_tags), json.dumps(variant.segment_ids),
             variant.assembled_text, variant.status, json.dumps(variant.metadata)),
        )
        self._conn.commit()

    def set_status(self, variant_id: str, status: str) -> bool:
        """Update variant status. Returns True if row was found."""
        cur = self._conn.execute(
            "UPDATE variants SET status = ?, reviewed_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND user_id = ?",
            (status, variant_id, self._uid),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, variant_id: str) -> bool:
        """Delete a variant. Returns True if row was found."""
        cur = self._conn.execute(
            "DELETE FROM variants WHERE id = ? AND user_id = ?",
            (variant_id, self._uid),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ── Read ─────────────────────────────────────────────────────────

    def get(self, variant_id: str) -> Variant | None:
        """Retrieve a single variant by ID."""
        row = self._conn.execute(
            "SELECT * FROM variants WHERE id = ? AND user_id = ?",
            (variant_id, self._uid),
        ).fetchone()
        return _to_dto(row) if row else None

    def get_by_name(self, name: str) -> Variant | None:
        """Retrieve the latest variant by name."""
        row = self._conn.execute(
            "SELECT * FROM variants WHERE name = ? AND user_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (name, self._uid),
        ).fetchone()
        return _to_dto(row) if row else None

    def get_approved(self) -> list[Variant]:
        """Retrieve all approved variants."""
        rows = self._conn.execute(
            "SELECT * FROM variants WHERE status = 'approved' AND user_id = ? "
            "ORDER BY name",
            (self._uid,),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def get_pending(self) -> list[Variant]:
        """Retrieve all variants awaiting review."""
        rows = self._conn.execute(
            "SELECT * FROM variants WHERE status = 'pending_review' AND user_id = ? "
            "ORDER BY created_at",
            (self._uid,),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def get_all(self) -> list[Variant]:
        """Retrieve all variants for this user."""
        rows = self._conn.execute(
            "SELECT * FROM variants WHERE user_id = ? ORDER BY name, created_at DESC",
            (self._uid,),
        ).fetchall()
        return [_to_dto(r) for r in rows]

    def find_by_tags(self, tags: list[str]) -> list[Variant]:
        """Find approved variants matching ANY of the given role tags.

        Returns variants sorted by match count (best match first).
        """
        approved = self.get_approved()
        scored: list[tuple[int, Variant]] = []
        tag_set = {t.lower() for t in tags}
        for v in approved:
            overlap = len(tag_set & {t.lower() for t in v.role_tags})
            if overlap > 0:
                scored.append((overlap, v))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [v for _, v in scored]


# ── Mapping ──────────────────────────────────────────────────────────────

def _to_dto(row: sqlite3.Row) -> Variant:
    return Variant(
        id=row["id"],
        name=row["name"],
        role_tags=json.loads(row["role_tags"]) if row["role_tags"] else [],
        segment_ids=json.loads(row["segment_ids"]) if row["segment_ids"] else [],
        assembled_text=row["assembled_text"],
        status=row["status"] or "pending_review",
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )
