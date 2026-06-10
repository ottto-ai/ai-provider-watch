from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json

ROOT = Path(__file__).resolve().parents[1]


def _assert_schema_valid(name: str, payload: object) -> None:
    schema = read_json(ROOT / "schemas" / name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    assert errors == []


def test_event_scaffold_writes_valid_model_lifecycle_event(tmp_path, capsys) -> None:
    output = tmp_path / "event.json"

    assert (
        main(
            [
                "event",
                "scaffold",
                "--event-date",
                "2026-06-10",
                "--observed-at",
                "2026-06-10T12:00:00Z",
                "--provider",
                "aws-bedrock",
                "--kind",
                "model_launch",
                "--title",
                "AWS Added Claude Fable 5 Availability",
                "--summary",
                "AWS added Claude Fable 5 availability through Bedrock for reviewed routing and cost evaluation.",
                "--source-url",
                "https://aws.amazon.com/about-aws/whats-new/2026/06/claude-fable-5-aws/",
                "--source-key",
                "aws_bedrock.whats_new",
                "--source-authority",
                "official_blog",
                "--content-sha256",
                "6f01dc703fe5c6c430428b7d45dd52cbe741ce133c188e21570770b459931be5",
                "--scope-ref",
                "surface:aws-bedrock/api",
                "--impact-kind",
                "availability",
                "--direction",
                "added",
                "--severity",
                "high",
                "--model-ref",
                "anthropic/claude-fable-5",
                "--who",
                "platform_engineers",
                "--who",
                "coding_agent_users",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == ""
    event = read_json(output)
    assert event["id"] == "2026-06-10-aws-bedrock-aws-added-claude-fable-5-availability"
    assert event["provider_refs"] == ["provider:aws-bedrock"]
    assert event["detail"]["kind"] == "model_lifecycle"
    assert event["detail"]["lifecycle_action"] == "launch"
    assert event["detail"]["model_refs"] == ["model:anthropic/claude-fable-5"]
    assert event["impacts"][0]["who_should_care"] == [
        "platform_engineers",
        "coding_agent_users",
    ]
    _assert_schema_valid("event.schema.json", event)
    _assert_schema_valid("event-detail.schema.json", event["detail"])
    _assert_schema_valid("impact.schema.json", event["impacts"][0])


def test_event_scaffold_hashes_local_snapshot_file(tmp_path, capsys) -> None:
    snapshot = tmp_path / "bounded-source.txt"
    snapshot.write_text("bounded facts only\n", encoding="utf-8")

    assert (
        main(
            [
                "event",
                "scaffold",
                "--event-date",
                "2026-06-10",
                "--observed-at",
                "2026-06-10T12:00:00Z",
                "--provider",
                "openai",
                "--kind",
                "api_contract_change",
                "--title",
                "OpenAI Changed Responses API Contract",
                "--summary",
                "OpenAI changed a Responses API contract and maintainers need to verify migration impact.",
                "--source-url",
                "https://developers.openai.com/api/docs/changelog",
                "--source-key",
                "openai.docs",
                "--source-authority",
                "official_docs",
                "--content-text-file",
                str(snapshot),
                "--scope-ref",
                "endpoint:openai/responses",
                "--impact-kind",
                "migration",
                "--direction",
                "changed",
            ]
        )
        == 0
    )

    event = json.loads(capsys.readouterr().out)
    assert event["evidence_refs"][0]["content_sha256"] == (
        "b42301731cc05766a4c44bfda79cdaa9daf6e137d4cd0a2df50b5b77fa2def2b"
    )
    assert event["detail"]["kind"] == "api_contract_change"
    _assert_schema_valid("event.schema.json", event)
    _assert_schema_valid("event-detail.schema.json", event["detail"])
    _assert_schema_valid("impact.schema.json", event["impacts"][0])


def test_event_scaffold_rejects_missing_model_ref(capsys) -> None:
    assert (
        main(
            [
                "event",
                "scaffold",
                "--event-date",
                "2026-06-10",
                "--observed-at",
                "2026-06-10T12:00:00Z",
                "--provider",
                "aws-bedrock",
                "--kind",
                "model_launch",
                "--title",
                "AWS Added Claude Fable 5 Availability",
                "--summary",
                "AWS added Claude Fable 5 availability through Bedrock for reviewed routing and cost evaluation.",
                "--source-url",
                "https://aws.amazon.com/about-aws/whats-new/2026/06/claude-fable-5-aws/",
                "--source-key",
                "aws_bedrock.whats_new",
                "--source-authority",
                "official_blog",
                "--content-sha256",
                "6f01dc703fe5c6c430428b7d45dd52cbe741ce133c188e21570770b459931be5",
                "--scope-ref",
                "surface:aws-bedrock/api",
                "--impact-kind",
                "availability",
                "--direction",
                "added",
            ]
        )
        == 1
    )

    assert "--model-ref is required" in capsys.readouterr().err
