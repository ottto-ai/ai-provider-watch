from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_latest_outputs_json(capsys) -> None:
    assert main(["--root", str(ROOT), "latest"]) == 0
    events = json.loads(capsys.readouterr().out)
    event_ids = {event["id"] for event in events}
    assert "2026-06-01-google-vertex-gemini-2-0-flash-retirement" in event_ids


def test_validate_command(capsys) -> None:
    assert main(["--root", str(ROOT), "validate"]) == 0
    assert "ok: validated" in capsys.readouterr().out
