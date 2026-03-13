from __future__ import annotations

from typer.testing import CliRunner

import applypilot.cli as cli


def test_run_command_forwards_default_limit(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr("applypilot.config.check_tier", lambda *_args, **_kwargs: None)

    def _fake_run_pipeline(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr("applypilot.pipeline.run_pipeline", _fake_run_pipeline)

    result = runner.invoke(cli.app, ["run", "tailor"])

    assert result.exit_code == 0
    assert captured["limit"] == 0


def test_run_command_forwards_explicit_limit(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "_bootstrap", lambda: None)
    monkeypatch.setattr("applypilot.config.check_tier", lambda *_args, **_kwargs: None)

    def _fake_run_pipeline(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr("applypilot.pipeline.run_pipeline", _fake_run_pipeline)

    result = runner.invoke(cli.app, ["run", "tailor", "--limit", "15"])

    assert result.exit_code == 0
    assert captured["limit"] == 15
