from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_latest_outputs_json(capsys) -> None:
    assert main(["--root", str(ROOT), "latest"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_validate_command(capsys) -> None:
    assert main(["--root", str(ROOT), "validate"]) == 0
    assert "ok: validated" in capsys.readouterr().out
