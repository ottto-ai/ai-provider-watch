from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.pipeline.ecosystem import ECOSYSTEM_TARGETS, build_ecosystem_mapping

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-02T00:00:00Z"
EVENT_ID = "2024-01-04-openai-gpt3-completions-retirement"


def _assert_valid(payload: dict) -> None:
    schema = read_json(ROOT / "schemas" / "ecosystem-mapping.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert [error.message for error in errors] == []


def _payload(target: str) -> dict:
    return build_ecosystem_mapping(
        ROOT,
        target=target,
        since="2024-01-01",
        risk="medium",
        event_id=EVENT_ID,
        created_at=CREATED_AT,
    )


def test_litellm_mapping_includes_gateway_config_search_keys() -> None:
    payload = _payload("litellm")

    _assert_valid(payload)
    record = payload["records"][0]
    assert payload["target"]["strategy"] == "gateway_config_annotation"
    assert "model_list[].litellm_params.model" in record["mapping"]["search_paths"]
    assert "openai/gpt-3.5-turbo-instruct" in record["lookup"]["target_model_ids"]
    assert "litellm_config.yaml" in record["mapping"]["config_file_hints"]


def test_models_dev_mapping_includes_catalog_lookup() -> None:
    payload = _payload("models-dev")

    _assert_valid(payload)
    record = payload["records"][0]
    assert payload["target"]["strategy"] == "catalog_annotation"
    assert record["mapping"]["api_lookup_url"] == "https://models.dev/api.json"
    assert record["mapping"]["suggested_status"] == "deprecated"


def test_observability_targets_include_annotation_shapes() -> None:
    langfuse = _payload("langfuse")
    helicone = _payload("helicone")
    openlit = _payload("openlit")

    for payload in (langfuse, helicone, openlit):
        _assert_valid(payload)
        assert payload["delivery_boundary"] == "mapping_only_no_third_party_api_calls"

    assert langfuse["records"][0]["mapping"]["observation_type"] == "event"
    assert "apw.event:2024-01-04-openai-gpt3-completions-retirement" in langfuse["records"][0]["mapping"]["tags"]
    assert "Helicone-Property-APW-Event-Id" in helicone["records"][0]["mapping"]["custom_properties"]
    assert openlit["records"][0]["mapping"]["resource_or_span_attributes"]["apw.event_id"] == EVENT_ID


def test_ecosystem_cli_writes_payload(tmp_path) -> None:
    output = tmp_path / "mapping.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "ecosystem",
                "render",
                "--target",
                "openlit",
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

    payload = read_json(output)
    _assert_valid(payload)
    assert payload["target"]["id"] == "openlit"


def test_ecosystem_cli_rejects_out_of_schema_limit(capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "ecosystem",
                "render",
                "--target",
                "litellm",
                "--limit",
                "101",
            ]
        )
        == 1
    )
    assert "ecosystem mapping limit must be between 1 and 100" in capsys.readouterr().err


def test_ecosystem_examples_match_current_renderer() -> None:
    for target in sorted(ECOSYSTEM_TARGETS):
        expected = _payload(target)
        actual = read_json(ROOT / "examples" / "ecosystem" / f"{target}-openai-retirement.json")
        assert actual == expected
