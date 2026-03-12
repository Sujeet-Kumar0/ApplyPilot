from __future__ import annotations

import applypilot.pipeline as pipeline


def _fake_stats() -> dict:
    return {
        "total": 0,
        "pending_detail": 0,
        "with_description": 0,
        "scored": 0,
        "tailored": 0,
        "with_cover_letter": 0,
        "ready_to_apply": 0,
        "applied": 0,
    }


def _patch_pipeline_bootstrap(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "load_env", lambda: None)
    monkeypatch.setattr(pipeline, "ensure_dirs", lambda: None)
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_stats", lambda: _fake_stats())
    monkeypatch.setattr(pipeline, "_setup_file_logging", lambda _ordered: None)


def test_run_pipeline_defaults_to_unbounded_tailor_cover_limit(monkeypatch) -> None:
    _patch_pipeline_bootstrap(monkeypatch)
    captured: dict[str, int] = {}

    def _fake_run_sequential(  # noqa: ANN001
        ordered,
        min_score,
        limit,
        workers,
        validation_mode,
        sources,
    ):
        captured["limit"] = limit
        return {"stages": [{"stage": "tailor", "status": "ok", "elapsed": 0.0}], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr(pipeline, "_run_sequential", _fake_run_sequential)

    pipeline.run_pipeline(stages=["tailor"], stream=False)
    assert captured["limit"] == 0


def test_run_pipeline_respects_explicit_limit_override(monkeypatch) -> None:
    _patch_pipeline_bootstrap(monkeypatch)
    captured: dict[str, int] = {}

    def _fake_run_sequential(  # noqa: ANN001
        ordered,
        min_score,
        limit,
        workers,
        validation_mode,
        sources,
    ):
        captured["limit"] = limit
        return {"stages": [{"stage": "tailor", "status": "ok", "elapsed": 0.0}], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr(pipeline, "_run_sequential", _fake_run_sequential)

    pipeline.run_pipeline(stages=["tailor"], limit=5, stream=False)
    assert captured["limit"] == 5
