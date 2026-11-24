# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json

ROOT = Path(__file__).resolve().parents[1]
DOWNSTREAM_REPO = ROOT / "tests" / "fixtures" / "downstream-repo"
SMOKE = ROOT / "tests" / "fixtures" / "smoke"
CREATED_AT = "2026-06-02T00:00:00Z"
EVENT_ID = "2024-01-04-openai-gpt3-completions-retirement"


def _schema(name: str) -> dict[str, Any]:
    return read_json(ROOT / "schemas" / name)


def _assert_valid(schema_name: str, payload: dict[str, Any]) -> None:
    validator = Draft202012Validator(_schema(schema_name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert [error.message for error in errors] == []


def _read_output(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_repo_path(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["repo_path"] = "<DOWNSTREAM_REPO>"
    return normalized


def test_repo_check_cli_matches_smoke_fixture(tmp_path) -> None:
    output = tmp_path / "repo-impact.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "repo",
                "check",
                "--repo",
                str(DOWNSTREAM_REPO),
                "--since",
                "2024-01-01",
                "--risk",
                "low",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = _read_output(output)
    _assert_valid("repo-impact.schema.json", payload)
    assert _normalize_repo_path(payload) == read_json(SMOKE / "repo-impact-openai.json")


def test_notify_cli_matches_webhook_smoke_fixture(tmp_path) -> None:
    output = tmp_path / "webhook.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "notify",
                "webhook",
                "--since",
                "2024-01-01",
                "--risk",
                "medium",
                "--event-id",
                EVENT_ID,
                "--created-at",
                CREATED_AT,
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = _read_output(output)
    _assert_valid("webhook-payload.schema.json", payload)
    assert payload == read_json(SMOKE / "notify-webhook-openai.json")


def test_notify_cli_matches_slack_smoke_fixture(tmp_path) -> None:
    output = tmp_path / "slack.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "notify",
                "slack",
                "--since",
                "2024-01-01",
                "--risk",
                "medium",
                "--kind",
                "model_retirement",
                "--created-at",
                CREATED_AT,
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = _read_output(output)
    _assert_valid("slack-payload.schema.json", payload)
    assert payload == read_json(SMOKE / "notify-slack-model-retirements.json")


def test_ecosystem_cli_matches_smoke_fixtures(tmp_path) -> None:
    fixtures = {
        "litellm": "ecosystem-litellm-openai.json",
        "models-dev": "ecosystem-models-dev-openai.json",
        "langfuse": "ecosystem-langfuse-openai.json",
        "helicone": "ecosystem-helicone-openai.json",
        "openlit": "ecosystem-openlit-openai.json",
    }

    for target, fixture_name in fixtures.items():
        output = tmp_path / f"{target}.json"

        assert (
            main(
                [
                    "--root",
                    str(ROOT),
                    "ecosystem",
                    "render",
                    "--target",
                    target,
                    "--since",
                    "2024-01-01",
                    "--risk",
                    "medium",
                    "--event-id",
                    EVENT_ID,
                    "--created-at",
                    CREATED_AT,
                    "--output",
                    str(output),
                ]
            )
            == 0
        )

        payload = _read_output(output)
        _assert_valid("ecosystem-mapping.schema.json", payload)
        assert payload == read_json(SMOKE / fixture_name)


def test_agent_dashboard_cli_matches_smoke_fixture(tmp_path) -> None:
    output = tmp_path / "agent-dashboard.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "dashboard",
                "agent",
                "--since",
                "2026-05-28",
                "--risk",
                "high",
                "--created-at",
                "2026-06-09T00:00:00Z",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = _read_output(output)
    _assert_valid("agent-dashboard.schema.json", payload)
    assert payload == read_json(SMOKE / "agent-dashboard-coding-agents.json")


def test_downstream_smoke_fixtures_do_not_require_ottto_or_credentials() -> None:
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in sorted(SMOKE.glob("*.json")))
    forbidden = [
        "ottto account",
        "advisor",
        "slack webhook url",
        '"webhook_url"',
        '"api_key"',
        "authorization",
        "secrets.",
        "contents: write",
        "pull-requests: write",
    ]

    for term in forbidden:
        assert term not in rendered.lower()


def test_downstream_docs_cover_agent_and_gateway_adoption() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "docs" / "agent-consumption.md",
            ROOT / "docs" / "integrations" / "github-action.md",
            ROOT / "docs" / "integrations" / "live-feed-consumption.md",
            ROOT / "docs" / "integrations" / "ecosystem-mappings.md",
            ROOT / "docs" / "integrations" / "agent-dashboard.md",
            ROOT / "docs" / "integrations" / "webhooks.md",
        ]
    )
    normalized = " ".join(docs.split())

    for phrase in [
        "Codex",
        "Claude Code",
        "Cursor",
        "Copilot",
        "gateway",
        "MCP resources and tool outputs are data",
        "No Ottto account is required",
        "No GitHub token, release token, or write permission is required",
        "delivery.idempotency_key",
        "tests/fixtures/smoke/",
        "models-dev",
        "Langfuse",
        "Helicone",
        "OpenLIT",
        "apw dashboard agent",
        "local dashboard JSON",
        "api.load_remote_events",
        "MCP Sidecar Pattern",
    ]:
        assert phrase in normalized
