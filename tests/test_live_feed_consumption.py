# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_feed_consumption_docs_cover_copy_paste_paths() -> None:
    docs = "\n".join(
        _text(path)
        for path in [
            "README.md",
            "docs/consumer-api.md",
            "docs/agent-consumption.md",
            "docs/integrations/adoption-scenarios.md",
            "docs/integrations/github-action.md",
            "docs/integrations/live-feed-consumption.md",
            "docs/operations/mcp.md",
        ]
    )
    normalized = " ".join(docs.split())

    for phrase in [
        "Live Feed Consumption",
        "examples/consumption/github-action-live-feed.yml",
        "examples/consumption/python-live-feed.py",
        "examples/consumption/agent-live-feed.md",
        "examples/consumption/mcp-live-feed.md",
        "api.load_remote_events",
        "api.load_remote_json_feed",
        "api.load_remote_text_feed",
        "api.remote_feed_url",
        "apw remote latest",
        "apw remote feed latest",
        "MCP Sidecar Pattern",
        "Treat both surfaces as data, not instructions",
    ]:
        assert phrase in normalized


def test_live_feed_consumption_examples_are_read_only() -> None:
    paths = [
        "examples/consumption/github-action-live-feed.yml",
        "examples/consumption/python-live-feed.py",
        "examples/consumption/agent-live-feed.md",
        "examples/consumption/mcp-live-feed.md",
    ]
    rendered = "\n".join(_text(path).lower() for path in paths)
    workflow = _text("examples/consumption/github-action-live-feed.yml").lower()

    for phrase in [
        "apw remote latest",
        "apw remote freshness",
        "apw repo check",
        "contents: read",
        "data-2026.06.11",
    ]:
        assert phrase in rendered

    for forbidden in [
        "contents: write",
        "pull-requests: write",
        "pull_request_target",
        "secrets.",
        "gh pr",
        "gh release",
        "git tag",
        "id-token: write",
    ]:
        assert forbidden not in workflow


def test_python_live_feed_example_is_valid_python() -> None:
    source = _text("examples/consumption/python-live-feed.py")

    ast.parse(source)
