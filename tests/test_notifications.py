from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.pipeline.notifications import build_slack_payload, build_webhook_payload

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-02T00:00:00Z"


def _schema(name: str) -> dict:
    return read_json(ROOT / "schemas" / name)


def _assert_valid(schema_name: str, payload: dict) -> None:
    validator = Draft202012Validator(_schema(schema_name), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert [error.message for error in errors] == []


def test_webhook_payload_is_schema_backed_and_operator_owned() -> None:
    payload = build_webhook_payload(
        ROOT,
        since="2024-01-01",
        risk="medium",
        provider="openai",
        created_at=CREATED_AT,
    )
    rendered = json.dumps(payload)

    _assert_valid("webhook-payload.schema.json", payload)
    assert payload["schema_version"] == "apw.webhook_payload.v0"
    assert payload["event_count"] == 20
    assert {event["id"] for event in payload["events"]} == {
        "2026-06-11-openai-codex-app-rate-limit-reset-computer-use",
        "2026-06-09-openai-codex-mobile-worktrees-goals-review",
        "2026-06-09-openai-codex-cli-web-search-schema-marketplace",
        "2026-06-09-openai-codex-app-migration-plugins-settings",
        "2026-06-08-openai-codex-cli-app-handoff-pat-plugin-json",
        "2026-06-04-openai-codex-cli-admin-rpc-tools-agents",
        "2026-06-04-openai-codex-app-computer-use-plugin-config",
        "2026-06-04-openai-moderation-scores-api",
        "2026-06-04-openai-image-api-401-errors",
        "2026-06-02-openai-codex-mobile-defaults-windows-ssh-side-chat",
        "2026-06-02-openai-codex-role-plugins-sites",
        "2026-06-02-openai-container-session-minute-billing",
        "2026-06-02-openai-gpt-image-model-deprecations",
        "2026-06-01-openai-codex-aws-bedrock-ga",
        "2026-05-29-openai-prompt-cache-retention-default",
        "2026-05-28-openai-chat-latest-alias",
        "2026-05-26-openai-workload-identity-federation",
        "2026-05-07-openai-realtime-voice-api-models",
        "2026-05-07-openai-gpt-55-cyber-trusted-access",
        "2026-05-05-openai-gpt-55-instant-default",
    }
    assert payload["delivery"]["mode"] == "operator_owned"
    assert payload["delivery"]["method"] == "POST"
    assert payload["delivery"]["retry_policy"]["retry_on_status"] == [408, 429, 500, 502, 503, 504]
    assert "webhook_url" not in rendered
    assert "api_key" not in rendered.lower()
    assert "authorization" not in rendered.lower()
    assert "quoted_excerpt" not in rendered


def test_slack_payload_is_schema_backed_and_block_kit_compatible() -> None:
    payload = build_slack_payload(
        ROOT,
        since="2024-01-01",
        risk="medium",
        kind="model_retirement",
        created_at=CREATED_AT,
    )
    rendered = json.dumps(payload)

    _assert_valid("slack-payload.schema.json", payload)
    assert payload["schema_version"] == "apw.slack_payload.v0"
    assert payload["delivery"]["surface"] == "slack_webhook"
    assert payload["delivery"]["requires_operator_owned_webhook_url"] is True
    assert payload["event_count"] >= 1
    assert payload["blocks"][0]["type"] == "header"
    assert any(block["type"] == "section" for block in payload["blocks"])
    assert "slack_token" not in rendered.lower()
    assert "authorization" not in rendered.lower()


def test_notify_cli_writes_webhook_payload(tmp_path) -> None:
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
                "2024-01-04-openai-gpt3-completions-retirement",
                "--created-at",
                CREATED_AT,
                "--output",
                str(output),
            ]
        )
        == 0
    )

    payload = read_json(output)
    _assert_valid("webhook-payload.schema.json", payload)
    assert payload["event_count"] == 1


def test_notify_cli_rejects_out_of_schema_limit(capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "notify",
                "slack",
                "--since",
                "2024-01-01",
                "--limit",
                "101",
            ]
        )
        == 1
    )
    assert "notification limit must be between 1 and 100" in capsys.readouterr().err


def test_notification_examples_match_current_renderer() -> None:
    webhook = build_webhook_payload(
        ROOT,
        since="2024-01-01",
        risk="medium",
        provider="openai",
        created_at=CREATED_AT,
    )
    slack = build_slack_payload(
        ROOT,
        since="2024-01-01",
        risk="medium",
        kind="model_retirement",
        created_at=CREATED_AT,
    )

    assert read_json(ROOT / "examples" / "notifications" / "webhook-medium-openai.json") == webhook
    assert read_json(ROOT / "examples" / "notifications" / "slack-medium-model-retirements.json") == slack
