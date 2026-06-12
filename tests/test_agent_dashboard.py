from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.pipeline.agent_dashboard import build_agent_dashboard

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-09T00:00:00Z"


def _assert_valid(payload: dict) -> None:
    schema = read_json(ROOT / "schemas" / "agent-dashboard.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert [error.message for error in errors] == []


def test_agent_dashboard_filters_high_risk_agent_events() -> None:
    payload = build_agent_dashboard(
        ROOT,
        since="2026-05-28",
        risk="high",
        created_at=CREATED_AT,
    )

    _assert_valid(payload)
    assert payload["schema_version"] == "apw.agent_dashboard.v0"
    assert payload["delivery_boundary"] == "local_dashboard_json_no_third_party_api_calls"
    assert payload["event_count"] == 6
    assert [card["event_id"] for card in payload["cards"]] == [
        "2026-06-11-openai-codex-app-rate-limit-reset-computer-use",
        "2026-06-08-openai-codex-cli-app-handoff-pat-plugin-json",
        "2026-06-04-openai-codex-cli-admin-rpc-tools-agents",
        "2026-06-02-openai-codex-role-plugins-sites",
        "2026-06-01-openai-codex-aws-bedrock-ga",
        "2026-05-28-anthropic-opus-48-dynamic-workflows",
    ]
    assert {ref for card in payload["cards"] for ref in card["agent_app_refs"]} == {
        "app:claude-code",
        "app:codex",
    }
    assert {card["priority"] for card in payload["cards"]} == {"high"}
    assert all(card["recommended_next_steps"] for card in payload["cards"])


def test_agent_dashboard_can_filter_one_agent_app() -> None:
    payload = build_agent_dashboard(
        ROOT,
        since="2026-05-28",
        risk="medium",
        agent_app="claude-code",
        created_at=CREATED_AT,
    )

    _assert_valid(payload)
    assert payload["filters"]["agent_app"] == "app:claude-code"
    assert payload["event_count"] == 3
    assert all(card["agent_app_refs"] == ["app:claude-code"] for card in payload["cards"])
    assert {card["event_kind"] for card in payload["cards"]} == {
        "status_incident",
        "workflow_behavior_change",
    }


def test_agent_dashboard_output_contains_no_credentials_or_raw_provider_text() -> None:
    payload = build_agent_dashboard(
        ROOT,
        since="2026-05-28",
        risk="medium",
        created_at=CREATED_AT,
    )
    rendered = json.dumps(payload).lower()

    assert "untrusted" in payload["untrusted_input_policy"].lower()
    for forbidden in [
        "api_key",
        "authorization",
        "customer telemetry",
        "slack_webhook_url",
        "webhook_url",
    ]:
        assert forbidden not in rendered


def test_agent_dashboard_cli_writes_schema_valid_payload(tmp_path) -> None:
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
                CREATED_AT,
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = read_json(output)
    _assert_valid(payload)
    assert payload["event_count"] == 6


def test_agent_dashboard_cli_rejects_out_of_schema_limit(capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "dashboard",
                "agent",
                "--limit",
                "51",
            ]
        )
        == 1
    )
    assert "agent dashboard limit must be between 1 and 50" in capsys.readouterr().err
