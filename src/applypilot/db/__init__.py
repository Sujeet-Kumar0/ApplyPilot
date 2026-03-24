"""Data access package.

Exports connection management and repository classes.
All DAOs are user-scoped via constructor-injected user_id.
"""

from applypilot.db.connection import get_connection, close_connection
from applypilot.db.segments_repo import Segment, SegmentsRepo
from applypilot.db.variants_repo import Variant, VariantsRepo

__all__ = [
    "get_connection",
    "close_connection",
    "Segment",
    "SegmentsRepo",
    "Variant",
    "VariantsRepo",
]
