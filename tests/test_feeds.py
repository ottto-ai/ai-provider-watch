from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.core.feeds import _rss_pub_date, build_artifacts

ROOT = Path(__file__).resolve().parents[1]


def test_build_artifacts_for_reviewed_seed_feed() -> None:
    artifacts = build_artifacts(ROOT)
    assert Path("data/feeds/events.json") in artifacts
    assert Path("data/feeds/events.ndjson") in artifacts
    assert Path("data/feeds/latest.json") in artifacts
    assert Path("data/feeds/freshness.json") in artifacts
    assert Path("data/releases/dev/manifest.json") in artifacts
    events = json.loads(artifacts[Path("data/feeds/events.json")])
    event_ids = {event["id"] for event in events}
    assert {
        "2024-01-04-openai-gpt3-completions-retirement",
        "2024-06-14-azure-openai-legacy-gpt3-retirement",
        "2024-12-04-aws-bedrock-prompt-caching-preview",
        "2025-02-24-anthropic-claude-3-7-sonnet-launch",
        "2026-06-01-google-vertex-gemini-2-0-flash-retirement",
    } <= event_ids
    latest = json.loads(artifacts[Path("data/feeds/latest.json")])
    assert "2026-06-05-aws-bedrock-agentcore-runtime-interactive-shells" in {
        event["id"] for event in latest
    }
    rss = artifacts[Path("data/feeds/rss.xml")]
    assert '<guid isPermaLink="false">2026-06-01-google-vertex-gemini-2-0-flash-retirement</guid>' in rss
    assert "<pubDate>Mon, 01 Jun 2026 10:36:49 GMT</pubDate>" in rss
    manifest = json.loads(artifacts[Path("data/releases/dev/manifest.json")])
    assert manifest["release_id"] == "dev"
    assert manifest["schema_versions"]["event"] == "apw.provider_event.v0"
    assert manifest["schema_versions"]["feed_freshness"] == "apw.feed_freshness.v0"
    assert "data/feeds/freshness.json" in manifest["checksums"]
    freshness = json.loads(artifacts[Path("data/feeds/freshness.json")])
    assert freshness["schema_version"] == "apw.feed_freshness.v0"
    assert freshness["release_id"] == "dev"
    assert freshness["data_tag"] is None
    assert freshness["event_count"] == len(events)
    assert freshness["latest_event_date"] == "2026-06-05"
    assert freshness["source_state"]["path"] == "data/source-state/fingerprints.json"
    assert freshness["source_state"]["source_count"] == 10
    assert freshness["release_artifacts"]["checksums_path"] == "data/releases/dev/checksums.txt"
    assert any(artifact["path"] == "data/feeds/events.json" for artifact in freshness["feed_artifacts"])
    assert "no raw provider content" in freshness["freshness_policy"]


def test_rss_pub_date_accepts_lowercase_rfc3339() -> None:
    assert _rss_pub_date("2026-06-01t10:36:49z") == "Mon, 01 Jun 2026 10:36:49 GMT"
