from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.feeds import _rss_pub_date, build_artifacts
from ai_provider_watch.core.validation import load_schemas

ROOT = Path(__file__).resolve().parents[1]


def test_build_artifacts_for_reviewed_seed_feed() -> None:
    artifacts = build_artifacts(ROOT)
    assert Path("data/feeds/events.json") in artifacts
    assert Path("data/feeds/events.ndjson") in artifacts
    assert Path("data/feeds/feed.json") in artifacts
    assert Path("data/feeds/latest.json") in artifacts
    assert Path("data/feeds/coverage.json") in artifacts
    assert Path("data/feeds/freshness.json") in artifacts
    assert Path("data/feeds/operations.json") in artifacts
    assert Path("data/releases/dev/manifest.json") in artifacts
    assert Path("data/releases/dev/evidence-index.json") in artifacts
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
    json_feed = json.loads(artifacts[Path("data/feeds/feed.json")])
    assert not list(
        Draft202012Validator(
            load_schemas(ROOT)["json_feed"],
            format_checker=FormatChecker(),
        ).iter_errors(json_feed)
    )
    assert json_feed["version"] == "https://jsonfeed.org/version/1.1"
    assert json_feed["feed_url"].endswith("/data/feeds/feed.json")
    assert "no raw provider content" in json_feed["user_comment"]
    assert json_feed["items"][0]["id"] == "2026-06-10-google-vertex-gemini-embedding-lifecycle-dates"
    assert json_feed["items"][0]["url"].endswith(
        "/data/events/2026-06-10-google-vertex-gemini-embedding-lifecycle-dates.json"
    )
    assert json_feed["items"][0]["_apw"]["evidence_refs"][0]["content_sha256"]
    manifest = json.loads(artifacts[Path("data/releases/dev/manifest.json")])
    assert manifest["release_id"] == "dev"
    assert manifest["schema_versions"]["event"] == "apw.provider_event.v0"
    assert manifest["schema_versions"]["feed_freshness"] == "apw.feed_freshness.v0"
    assert manifest["schema_versions"]["json_feed"] == "https://jsonfeed.org/version/1.1"
    assert manifest["schema_versions"]["source_coverage"] == "apw.source_coverage.v0"
    assert manifest["schema_versions"]["operations_report"] == "apw.operations_report.v0"
    assert manifest["schema_versions"]["release_evidence_index"] == "apw.release_evidence_index.v0"
    assert "data/feeds/coverage.json" in manifest["checksums"]
    assert "data/feeds/feed.json" in manifest["checksums"]
    assert "data/feeds/freshness.json" in manifest["checksums"]
    assert "data/feeds/operations.json" in manifest["checksums"]
    assert "data/releases/dev/evidence-index.json" in manifest["checksums"]
    evidence_index = json.loads(artifacts[Path("data/releases/dev/evidence-index.json")])
    assert not list(
        Draft202012Validator(
            load_schemas(ROOT)["release_evidence_index"],
            format_checker=FormatChecker(),
        ).iter_errors(evidence_index)
    )
    assert any(item["name"] == "PyPI Trusted Publishing" for item in evidence_index["external_evidence"])
    assert any(item["path"] == ".github/workflows/scorecard.yml" for item in evidence_index["github_workflows"])
    coverage = json.loads(artifacts[Path("data/feeds/coverage.json")])
    assert coverage["schema_version"] == "apw.source_coverage.v0"
    assert coverage["summary"]["source_count"] == 20
    assert coverage["summary"]["missing_enabled_source_count"] == 0
    operations = json.loads(artifacts[Path("data/feeds/operations.json")])
    assert not list(
        Draft202012Validator(
            load_schemas(ROOT)["operations_report"],
            format_checker=FormatChecker(),
        ).iter_errors(operations)
    )
    assert operations["schema_version"] == "apw.operations_report.v0"
    assert operations["summary"]["candidate_backlog_count"] == 0
    freshness = json.loads(artifacts[Path("data/feeds/freshness.json")])
    assert freshness["schema_version"] == "apw.feed_freshness.v0"
    assert freshness["release_id"] == "dev"
    assert freshness["data_tag"] is None
    assert freshness["event_count"] == len(events)
    assert freshness["latest_event_date"] == "2026-06-10"
    assert freshness["source_state"]["path"] == "data/source-state/fingerprints.json"
    assert freshness["source_state"]["source_count"] == 19
    assert freshness["release_artifacts"]["checksums_path"] == "data/releases/dev/checksums.txt"
    assert any(artifact["path"] == "data/feeds/coverage.json" for artifact in freshness["feed_artifacts"])
    assert any(artifact["path"] == "data/feeds/events.json" for artifact in freshness["feed_artifacts"])
    assert any(artifact["path"] == "data/feeds/operations.json" for artifact in freshness["feed_artifacts"])
    assert any(
        artifact["path"] == "data/feeds/feed.json"
        and artifact["media_type"] == "application/feed+json"
        for artifact in freshness["feed_artifacts"]
    )
    assert "no raw provider content" in freshness["freshness_policy"]


def test_rss_pub_date_accepts_lowercase_rfc3339() -> None:
    assert _rss_pub_date("2026-06-01t10:36:49z") == "Mon, 01 Jun 2026 10:36:49 GMT"
