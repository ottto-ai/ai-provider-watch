# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_provider_watch import api
from ai_provider_watch.core import io, remote

ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "2026-06-01-google-vertex-gemini-2-0-flash-retirement"


def _write_minimal_data_root(root: Path) -> None:
    (root / "schemas").mkdir(parents=True)
    (root / "data" / "events").mkdir(parents=True)
    (root / "data" / "feeds").mkdir(parents=True)
    (root / "registries").mkdir(parents=True)
    (root / "sources").mkdir(parents=True)
    (root / "sources" / "registry.json").write_text('{"sources": []}\n', encoding="utf-8")
    (root / "schemas" / "event.schema.json").write_text(
        '{"$id": "https://example.test/event.schema.json"}\n',
        encoding="utf-8",
    )
    event = {
        "id": "2026-06-10-example-provider-change",
        "title": "Example Provider Change",
        "event_date": "2026-06-10",
        "observed_at": "2026-06-10T00:00:00Z",
        "severity": "high",
        "provider_refs": ["provider:example"],
    }
    (root / "data" / "events" / f"{event['id']}.json").write_text(
        json.dumps(event, sort_keys=True),
        encoding="utf-8",
    )
    (root / "data" / "feeds" / "latest.json").write_text(
        json.dumps([event], sort_keys=True),
        encoding="utf-8",
    )
    (root / "data" / "feeds" / "events.json").write_text(
        json.dumps([event], sort_keys=True),
        encoding="utf-8",
    )
    (root / "data" / "feeds" / "events.ndjson").write_text(
        json.dumps(event, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "data" / "feeds" / "rss.xml").write_text(
        "<?xml version=\"1.0\"?><rss></rss>\n",
        encoding="utf-8",
    )


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def test_consumer_api_loads_checkout_data() -> None:
    events = api.load_events(root=ROOT, provider="google", min_severity="medium", limit=5)

    assert any(event["id"] == EVENT_ID for event in events)
    assert api.load_event(EVENT_ID, root=ROOT)["event_kind"] == "model_retirement"
    assert api.load_json_feed("latest", root=ROOT)[0]["id"].startswith("2026-")
    assert api.load_json_feed("json-feed", root=ROOT)["version"] == "https://jsonfeed.org/version/1.1"
    assert EVENT_ID in api.load_text_feed("events.ndjson", root=ROOT)
    assert api.load_schema("json-feed", root=ROOT)["$id"].endswith("json-feed.schema.json")


def test_consumer_api_falls_back_to_bundled_package_data(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "_data"
    outside = tmp_path / "outside"
    outside.mkdir()
    _write_minimal_data_root(bundled)

    monkeypatch.chdir(outside)
    monkeypatch.setattr(io, "package_data_root", lambda: bundled)

    assert api.data_root() == bundled
    assert api.load_events()[0]["id"] == "2026-06-10-example-provider-change"
    assert api.load_event("2026-06-10-example-provider-change")["title"] == "Example Provider Change"
    assert api.load_json_feed("latest")[0]["provider_refs"] == ["provider:example"]
    assert "provider:example" in api.load_text_feed("events.ndjson")
    assert api.load_schema("event")["$id"] == "https://example.test/event.schema.json"


def test_consumer_api_rejects_unknown_aliases() -> None:
    with pytest.raises(ValueError, match="unknown min_severity"):
        api.load_events(root=ROOT, min_severity="urgent")
    with pytest.raises(ValueError, match="limit must be greater than zero"):
        api.load_events(root=ROOT, limit=0)
    with pytest.raises(ValueError, match="unknown JSON feed"):
        api.load_json_feed("candidates", root=ROOT)
    with pytest.raises(ValueError, match="unknown text feed"):
        api.load_text_feed("html", root=ROOT)
    with pytest.raises(ValueError, match="unknown schema"):
        api.load_schema("private", root=ROOT)


def test_consumer_api_loads_remote_feed_helpers(monkeypatch) -> None:
    requested: list[tuple[str, float]] = []
    events = [
        {
            "id": "high-openai",
            "provider_refs": ["provider:openai"],
            "severity": "high",
            "event_date": "2026-06-10",
            "title": "High OpenAI",
        },
        {
            "id": "low-google",
            "provider_refs": ["provider:google"],
            "severity": "low",
            "event_date": "2026-06-09",
            "title": "Low Google",
        },
    ]
    freshness = {
        "release_id": "data-2026.06.10",
        "event_count": 2,
        "latest_event_date": "2026-06-10",
    }

    def fake_urlopen(request, timeout):  # noqa: ANN001
        requested.append((request.full_url, timeout))
        if request.full_url.endswith("/data/feeds/events.json"):
            return _FakeResponse(json.dumps(events).encode("utf-8"))
        if request.full_url.endswith("/data/feeds/freshness.json"):
            return _FakeResponse(json.dumps(freshness).encode("utf-8"))
        if request.full_url.endswith("/data/feeds/events.ndjson"):
            payload = "\n".join(json.dumps(item, sort_keys=True) for item in events) + "\n"
            return _FakeResponse(payload.encode("utf-8"))
        raise AssertionError(request.full_url)

    monkeypatch.setattr(remote, "urlopen", fake_urlopen)

    assert api.remote_feed_url("events.ndjson", ref="data-2026.06.10") == (
        "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/"
        "data-2026.06.10/data/feeds/events.ndjson"
    )
    assert [
        event["id"]
        for event in api.load_remote_events(
            ref="data-2026.06.10",
            provider="openai",
            min_severity="medium",
            limit=5,
            timeout=3.0,
            limit_bytes=10_000,
        )
    ] == ["high-openai"]
    assert api.load_remote_json_feed("freshness", ref="data-2026.06.10") == freshness
    assert "high-openai" in api.load_remote_text_feed(
        "events.ndjson",
        ref="data-2026.06.10",
    )
    assert requested[0] == (
        "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/"
        "data-2026.06.10/data/feeds/events.json",
        3.0,
    )


def test_consumer_api_remote_helpers_validate_inputs() -> None:
    with pytest.raises(ValueError, match="unknown min_severity"):
        api.load_remote_events(min_severity="urgent")
    with pytest.raises(ValueError, match="limit must be greater than zero"):
        api.load_remote_events(limit=0)
    with pytest.raises(ValueError, match="unknown remote JSON feed"):
        api.load_remote_json_feed("rss")


def test_consumer_api_contract_is_documented() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "README.md",
            ROOT / "docs/consumer-api.md",
            ROOT / "docs/operations/v1-governance.md",
        ]
    )

    for phrase in [
        "ai_provider_watch.api",
        "load_events",
        "load_event",
        "load_json_feed",
        "load_text_feed",
        "load_schema",
        "load_remote_events",
        "load_remote_json_feed",
        "load_remote_text_feed",
        "remote_feed_url",
        "no-checkout",
        "ignore unknown fields",
        "TypeScript package",
    ]:
        assert phrase in docs
