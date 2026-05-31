from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.core.feeds import build_artifacts

ROOT = Path(__file__).resolve().parents[1]


def test_build_artifacts_for_empty_reviewed_feed() -> None:
    artifacts = build_artifacts(ROOT)
    assert Path("data/feeds/events.json") in artifacts
    assert Path("data/feeds/events.ndjson") in artifacts
    assert Path("data/feeds/latest.json") in artifacts
    assert Path("data/releases/dev/manifest.json") in artifacts
    assert json.loads(artifacts[Path("data/feeds/events.json")]) == []
    manifest = json.loads(artifacts[Path("data/releases/dev/manifest.json")])
    assert manifest["release_id"] == "dev"
    assert manifest["schema_versions"]["event"] == "apw.provider_event.v0"
