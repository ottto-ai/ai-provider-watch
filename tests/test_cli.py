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


def test_release_dry_run_command(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "dry-run",
                "--release-date",
                "2026-06-01",
                "--source-commit",
                "0123456789abcdef0123456789abcdef01234567",
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["release_id"] == "data-2026.06.01"
    assert output["artifact_count"] > 0
