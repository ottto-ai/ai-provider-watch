from __future__ import annotations

import json

import pytest

from ai_provider_watch.cli import main
from ai_provider_watch.core import remote
from ai_provider_watch.core.io import read_json


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def test_remote_raw_url_pins_repo_and_encodes_ref() -> None:
    assert remote.remote_raw_url("data/feeds/latest.json", ref="data-2026.06.10") == (
        "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/"
        "data-2026.06.10/data/feeds/latest.json"
    )
    assert "%2F" in remote.remote_raw_url("data/feeds/latest.json", ref="feature/feed")


def test_remote_latest_cli_filters_fake_live_feed(monkeypatch, capsys) -> None:
    requested_urls: list[str] = []
    events = [
        {
            "id": "high-openai",
            "provider_refs": ["provider:openai"],
            "severity": "high",
            "event_date": "2026-06-10",
        },
        {
            "id": "low-google",
            "provider_refs": ["provider:google"],
            "severity": "low",
            "event_date": "2026-06-09",
        },
    ]

    def fake_urlopen(request, timeout):  # noqa: ANN001
        requested_urls.append(request.full_url)
        assert timeout == 3.0
        return _FakeResponse(json.dumps(events).encode("utf-8"))

    monkeypatch.setattr(remote, "urlopen", fake_urlopen)

    assert (
        main(
            [
                "remote",
                "latest",
                "--ref",
                "data-2026.06.10",
                "--provider",
                "openai",
                "--risk",
                "medium",
                "--limit",
                "5",
                "--timeout",
                "3",
            ]
        )
        == 0
    )

    assert requested_urls == [
        "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/"
        "data-2026.06.10/data/feeds/events.json"
    ]
    assert [event["id"] for event in json.loads(capsys.readouterr().out)] == ["high-openai"]


def test_remote_feed_cli_writes_json_artifact(monkeypatch, tmp_path, capsys) -> None:
    output = tmp_path / "freshness.json"
    payload = {
        "release_id": "dev",
        "data_tag": None,
        "package_version": "0.1.5",
        "event_count": 32,
        "latest_event_date": "2026-06-10",
    }

    def fake_urlopen(request, timeout):  # noqa: ANN001, ARG001
        assert request.full_url.endswith("/main/data/feeds/freshness.json")
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(remote, "urlopen", fake_urlopen)

    assert main(["remote", "feed", "freshness", "--output", str(output)]) == 0

    assert capsys.readouterr().out == ""
    assert read_json(output) == payload


def test_remote_latest_rejects_malformed_feed_shape(monkeypatch, capsys) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001, ARG001
        return _FakeResponse(json.dumps({"events": []}).encode("utf-8"))

    monkeypatch.setattr(remote, "urlopen", fake_urlopen)

    assert main(["remote", "latest"]) == 1
    assert "remote events feed is not a JSON array" in capsys.readouterr().err


def test_remote_feed_rejects_unknown_artifact(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["remote", "feed", "unknown"])

    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
