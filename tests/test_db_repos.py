"""Tests for db/ DAO layer — SegmentsRepo and VariantsRepo."""

import sqlite3
import pytest

from applypilot.db.segments_repo import Segment, SegmentsRepo
from applypilot.db.variants_repo import Variant, VariantsRepo


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def seg_repo(conn):
    return SegmentsRepo(conn, user_id="test-user")


@pytest.fixture
def var_repo(conn):
    return VariantsRepo(conn, user_id="test-user")


# ── SegmentsRepo ─────────────────────────────────────────────────────

class TestSegmentsRepo:
    def test_save_and_get(self, seg_repo):
        s = Segment(id="s1", type="root", parent_id=None, content="Resume")
        seg_repo.save(s)
        got = seg_repo.get("s1")
        assert got is not None
        assert got.content == "Resume"
        assert got.type == "root"

    def test_save_many(self, seg_repo):
        segs = [
            Segment(id="r", type="root", parent_id=None, content="Root"),
            Segment(id="b1", type="bullet", parent_id="r", content="Bullet 1"),
            Segment(id="b2", type="bullet", parent_id="r", content="Bullet 2"),
        ]
        seg_repo.save_many(segs)
        assert len(seg_repo.get_children("r")) == 2

    def test_get_tree(self, seg_repo):
        seg_repo.save_many([
            Segment(id="r", type="root", parent_id=None, content="Root"),
            Segment(id="e1", type="experience", parent_id="r", content="Amazon"),
            Segment(id="b1", type="bullet", parent_id="e1", content="Built X"),
            Segment(id="b2", type="bullet", parent_id="e1", content="Built Y"),
        ])
        tree = seg_repo.get_tree("r")
        assert len(tree) == 4
        assert tree[0].type == "root"

    def test_get_by_type(self, seg_repo):
        seg_repo.save_many([
            Segment(id="r", type="root", parent_id=None, content="Root"),
            Segment(id="b1", type="bullet", parent_id="r", content="A"),
            Segment(id="b2", type="bullet", parent_id="r", content="B"),
            Segment(id="s1", type="skill_group", parent_id="r", content="C"),
        ])
        assert len(seg_repo.get_by_type("bullet")) == 2
        assert len(seg_repo.get_by_type("skill_group")) == 1

    def test_get_roots(self, seg_repo):
        seg_repo.save_many([
            Segment(id="r1", type="root", parent_id=None, content="A"),
            Segment(id="c1", type="bullet", parent_id="r1", content="B"),
        ])
        roots = seg_repo.get_roots()
        assert len(roots) == 1
        assert roots[0].id == "r1"

    def test_delete_tree(self, seg_repo):
        seg_repo.save_many([
            Segment(id="r", type="root", parent_id=None, content="Root"),
            Segment(id="c1", type="bullet", parent_id="r", content="A"),
        ])
        deleted = seg_repo.delete_tree("r")
        assert deleted == 2
        assert seg_repo.get("r") is None

    def test_delete_all(self, seg_repo):
        seg_repo.save_many([
            Segment(id="r", type="root", parent_id=None, content="Root"),
            Segment(id="c", type="bullet", parent_id="r", content="A"),
        ])
        assert seg_repo.delete_all() == 2
        assert seg_repo.get_roots() == []

    def test_user_isolation(self, conn):
        """Different user_ids see different data."""
        repo_a = SegmentsRepo(conn, user_id="alice")
        repo_b = SegmentsRepo(conn, user_id="bob")
        repo_a.save(Segment(id="s1", type="root", parent_id=None, content="Alice"))
        repo_b.save(Segment(id="s1", type="root", parent_id=None, content="Bob"))
        assert repo_a.get("s1").content == "Alice"
        assert repo_b.get("s1").content == "Bob"

    def test_get_by_tags(self, seg_repo):
        seg_repo.save_many([
            Segment(id="b1", type="bullet", parent_id=None, content="A", tags=["java", "aws"]),
            Segment(id="b2", type="bullet", parent_id=None, content="B", tags=["python"]),
        ])
        assert len(seg_repo.get_by_tags(["java"])) == 1
        assert len(seg_repo.get_by_tags(["python", "java"])) == 2


# ── VariantsRepo ─────────────────────────────────────────────────────

class TestVariantsRepo:
    def test_save_and_get(self, var_repo):
        v = Variant(id="v1", name="backend", role_tags=["java"], segment_ids=["s1"],
                    assembled_text="resume text", status="pending_review")
        var_repo.save(v)
        got = var_repo.get("v1")
        assert got is not None
        assert got.name == "backend"
        assert got.status == "pending_review"

    def test_set_status(self, var_repo):
        var_repo.save(Variant(id="v1", name="be", role_tags=[], segment_ids=[],
                              assembled_text="t", status="pending_review"))
        assert var_repo.set_status("v1", "approved")
        assert var_repo.get("v1").status == "approved"

    def test_get_approved_and_pending(self, var_repo):
        var_repo.save(Variant(id="v1", name="a", role_tags=[], segment_ids=[],
                              assembled_text="t", status="approved"))
        var_repo.save(Variant(id="v2", name="b", role_tags=[], segment_ids=[],
                              assembled_text="t", status="pending_review"))
        assert len(var_repo.get_approved()) == 1
        assert len(var_repo.get_pending()) == 1

    def test_find_by_tags(self, var_repo):
        var_repo.save(Variant(id="v1", name="be", role_tags=["java", "aws"],
                              segment_ids=[], assembled_text="t", status="approved"))
        var_repo.save(Variant(id="v2", name="fe", role_tags=["react"],
                              segment_ids=[], assembled_text="t", status="approved"))
        matches = var_repo.find_by_tags(["java"])
        assert len(matches) == 1
        assert matches[0].name == "be"

    def test_delete(self, var_repo):
        var_repo.save(Variant(id="v1", name="x", role_tags=[], segment_ids=[],
                              assembled_text="t"))
        assert var_repo.delete("v1")
        assert var_repo.get("v1") is None

    def test_user_isolation(self, conn):
        repo_a = VariantsRepo(conn, user_id="alice")
        repo_b = VariantsRepo(conn, user_id="bob")
        repo_a.save(Variant(id="v1", name="a", role_tags=[], segment_ids=[],
                            assembled_text="alice"))
        assert repo_b.get("v1") is None
