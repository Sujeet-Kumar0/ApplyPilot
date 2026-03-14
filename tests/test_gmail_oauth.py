from __future__ import annotations

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest


def _load_gmail_oauth_module():
    script_path = Path(__file__).parent.parent / "scripts" / "gmail_oauth.py"
    spec = importlib.util.spec_from_file_location("gmail_oauth_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_write_private_json_sets_private_permissions(tmp_path) -> None:
    module = _load_gmail_oauth_module()
    target = tmp_path / ".gmail-mcp" / "credentials.json"

    module._write_private_json(target, {"token": "abc123"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"token": "abc123"}
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
