from __future__ import annotations

from pathlib import Path

from applypilot.scoring import tailor


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.committed = False

    def execute(self, query: str, params: tuple = ()) -> "_FakeConnection":
        self.calls.append((query, params))
        return self

    def commit(self) -> None:
        self.committed = True


def _make_job(url: str = "https://example.com/job/1") -> dict:
    return {
        "url": url,
        "title": "Staff Software Engineer - AI II",
        "site": "Thomson Reuters",
        "location": "Remote",
        "fit_score": 9,
        "full_description": "Build production AI systems.",
    }


def _approved_report() -> dict:
    return {
        "attempts": 1,
        "validator": {"passed": True, "errors": [], "warnings": []},
        "judge": {"passed": True, "verdict": "PASS", "issues": "none"},
        "status": "approved",
    }


def test_build_tailored_prefix_is_deterministic_and_unique_per_url() -> None:
    base = _make_job("https://example.com/job/1")
    same = _make_job("https://example.com/job/1")
    other = _make_job("https://example.com/job/2")

    first = tailor._build_tailored_prefix(base)
    second = tailor._build_tailored_prefix(same)
    third = tailor._build_tailored_prefix(other)

    assert first == second
    assert first != third
    assert first.startswith("Thomson_Reuters_Staff_Software_Engineer_-_AI_II_")


def test_run_tailoring_requires_pdf_for_submission(monkeypatch, tmp_path: Path) -> None:
    conn = _FakeConnection()
    job = _make_job()

    monkeypatch.setattr(tailor, "TAILORED_DIR", tmp_path)
    monkeypatch.setattr(tailor, "load_profile", lambda: {"personal": {}})
    monkeypatch.setattr(tailor, "load_resume_text", lambda: "base resume")
    monkeypatch.setattr(tailor, "get_connection", lambda: conn)
    monkeypatch.setattr(tailor, "get_jobs_by_stage", lambda **_: [job])
    monkeypatch.setattr(tailor, "tailor_resume", lambda *args, **kwargs: ("tailored resume", _approved_report()))

    def _fake_convert_to_pdf(text_path: Path) -> Path:
        out = Path(text_path).with_suffix(".pdf")
        out.write_bytes(b"%PDF-1.4 fake\n")
        return out

    monkeypatch.setattr("applypilot.scoring.pdf.convert_to_pdf", _fake_convert_to_pdf)

    result = tailor.run_tailoring(min_score=7, limit=1, validation_mode="normal")

    assert result["approved"] == 1
    assert result["errors"] == 0
    txts = list(tmp_path.glob("*.txt"))
    pdfs = list(tmp_path.glob("*.pdf"))
    assert any(not p.name.endswith("_JOB.txt") for p in txts)
    assert len(pdfs) == 1
    assert any("tailored_resume_path" in query for query, _ in conn.calls)
    assert conn.committed


def test_run_tailoring_does_not_persist_when_pdf_generation_fails(monkeypatch, tmp_path: Path) -> None:
    conn = _FakeConnection()
    job = _make_job()

    monkeypatch.setattr(tailor, "TAILORED_DIR", tmp_path)
    monkeypatch.setattr(tailor, "load_profile", lambda: {"personal": {}})
    monkeypatch.setattr(tailor, "load_resume_text", lambda: "base resume")
    monkeypatch.setattr(tailor, "get_connection", lambda: conn)
    monkeypatch.setattr(tailor, "get_jobs_by_stage", lambda **_: [job])
    monkeypatch.setattr(tailor, "tailor_resume", lambda *args, **kwargs: ("tailored resume", _approved_report()))
    monkeypatch.setattr("applypilot.scoring.pdf.convert_to_pdf", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))

    result = tailor.run_tailoring(min_score=7, limit=1, validation_mode="normal")

    assert result["approved"] == 0
    assert result["errors"] == 1
    assert any(not p.name.endswith("_JOB.txt") for p in tmp_path.glob("*.txt"))
    assert not any("tailored_resume_path" in query for query, _ in conn.calls)
    assert any("tailor_attempts=COALESCE(tailor_attempts,0)+1" in query for query, _ in conn.calls)
    assert conn.committed
