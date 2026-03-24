"""Variant generator — creates role-specific resume variants from segments.

SRP: Only generates variants by selecting/rewriting segments via LLM.
Persists results via injected VariantsRepo. Does not handle review flow.

Flow:
    1. Read segments from SegmentsRepo
    2. For each target role, ask LLM to select + rewrite relevant bullets
    3. Assemble into plain text via assembler
    4. Save as Variant with status=pending_review
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from applypilot.db.segments_repo import Segment, SegmentsRepo
from applypilot.db.variants_repo import Variant, VariantsRepo
from applypilot.tailoring.assembler import assemble

log = logging.getLogger(__name__)


class VariantGenerator:
    """Generates role-specific resume variants from atomic segments."""

    def __init__(
        self,
        segments_repo: SegmentsRepo,
        variants_repo: VariantsRepo,
        llm_fn: Any,  # callable(messages, max_tokens) -> str
        profile: dict,
    ) -> None:
        self._segments = segments_repo
        self._variants = variants_repo
        self._llm = llm_fn
        self._profile = profile

    def generate(self, role_name: str, role_tags: list[str], max_bullets: int = 4) -> Variant:
        """Generate a single variant for a target role.

        Args:
            role_name: Human-readable role name (e.g. "backend_engineer").
            role_tags: Tags to match segments (e.g. ["backend", "java", "aws"]).
            max_bullets: Max bullets per experience section (one-page constraint).

        Returns:
            Variant with status=pending_review.
        """
        roots = self._segments.get_roots()
        if not roots:
            raise ValueError("No segments found. Run decompose first.")

        root = roots[0]
        all_segments = self._segments.get_tree(root.id)

        # Separate by type
        by_type: dict[str, list[Segment]] = {}
        for seg in all_segments:
            by_type.setdefault(seg.type, []).append(seg)

        # Rewrite summary for this role
        original_summary = by_type.get("summary", [None])[0]
        new_summary = self._rewrite_summary(original_summary, role_name, role_tags)

        # Select and rewrite bullets per experience
        experiences = by_type.get("experience", [])
        bullet_map: dict[str, list[Segment]] = {}
        for seg in by_type.get("bullet", []):
            bullet_map.setdefault(seg.parent_id or "", []).append(seg)

        rewritten_bullets: dict[str, list[Segment]] = {}
        for exp in experiences:
            bullets = bullet_map.get(exp.id, [])
            rewritten = self._select_and_rewrite_bullets(
                exp, bullets, role_name, role_tags, max_bullets,
            )
            rewritten_bullets[exp.id] = rewritten

        # Assemble variant segments
        variant_segments = self._build_variant_segments(
            root, new_summary, experiences, rewritten_bullets,
            by_type.get("skill_group", []),
            by_type.get("education", []),
            by_type.get("project", []),
        )

        # Assemble text
        assembled = assemble(variant_segments, self._profile)

        variant = Variant(
            id=uuid.uuid4().hex[:12],
            name=role_name,
            role_tags=role_tags,
            segment_ids=[s.id for s in variant_segments],
            assembled_text=assembled,
            status="pending_review",
            metadata={"max_bullets": max_bullets},
        )
        self._variants.save(variant)
        log.info("Generated variant '%s' (%d segments, %d chars)",
                 role_name, len(variant_segments), len(assembled))
        return variant

    def generate_batch(
        self, roles: list[dict[str, Any]], max_bullets: int = 4,
    ) -> list[Variant]:
        """Generate variants for multiple roles.

        Args:
            roles: List of {"name": str, "tags": list[str]}.
            max_bullets: Max bullets per experience section.

        Returns:
            List of generated Variants.
        """
        return [
            self.generate(r["name"], r["tags"], max_bullets)
            for r in roles
        ]

    # ── LLM interactions (small, focused prompts) ────────────────────

    def _rewrite_summary(
        self, original: Segment | None, role_name: str, role_tags: list[str],
    ) -> Segment:
        """Rewrite summary for target role. Small prompt, few tokens."""
        original_text = original.content if original else ""
        prompt = (
            f"Rewrite this resume summary for a {role_name.replace('_', ' ')} role. "
            f"Emphasize: {', '.join(role_tags)}. "
            f"2-3 sentences, first person implied. No fluff.\n\n"
            f"Original: {original_text}\n\n"
            f"Return ONLY the rewritten summary, nothing else."
        )
        result = self._llm(
            [{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return Segment(
            id=uuid.uuid4().hex[:12], type="summary", parent_id=None,
            content=result.strip(), sort_order=0,
        )

    def _select_and_rewrite_bullets(
        self,
        experience: Segment,
        bullets: list[Segment],
        role_name: str,
        role_tags: list[str],
        max_bullets: int,
    ) -> list[Segment]:
        """Select top bullets and rewrite for target role. Small prompt per experience."""
        if not bullets:
            return []

        bullet_texts = "\n".join(f"{i+1}. {b.content}" for i, b in enumerate(bullets))
        prompt = (
            f"From these bullets for '{experience.content}', "
            f"select the top {max_bullets} most relevant for a {role_name.replace('_', ' ')} role "
            f"(keywords: {', '.join(role_tags)}).\n\n"
            f"{bullet_texts}\n\n"
            f"Rewrite each selected bullet: strong verb + what was built + quantified impact. "
            f"Return JSON array of strings. ONLY the JSON array, nothing else."
        )
        result = self._llm(
            [{"role": "user", "content": prompt}],
            max_tokens=500,
        )

        try:
            rewritten = json.loads(result.strip())
        except json.JSONDecodeError:
            log.warning("Failed to parse bullet rewrite for %s, using originals", experience.content)
            rewritten = [b.content for b in bullets[:max_bullets]]

        return [
            Segment(
                id=uuid.uuid4().hex[:12], type="bullet",
                parent_id=experience.id, content=text, sort_order=i,
            )
            for i, text in enumerate(rewritten[:max_bullets])
        ]

    # ── Assembly helper ──────────────────────────────────────────────

    def _build_variant_segments(
        self,
        root: Segment,
        summary: Segment,
        experiences: list[Segment],
        bullet_map: dict[str, list[Segment]],
        skills: list[Segment],
        education: list[Segment],
        projects: list[Segment],
    ) -> list[Segment]:
        """Combine all pieces into an ordered segment list for assembly."""
        result = [root, summary]
        for skill in skills:
            result.append(skill)
        for exp in experiences:
            result.append(exp)
            result.extend(bullet_map.get(exp.id, []))
        for proj in projects:
            result.append(proj)
        for edu in education:
            result.append(edu)
        return result
