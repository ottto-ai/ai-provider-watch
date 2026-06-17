from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.source_catalog import build_source_catalog

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-08T12:00:00Z"


def test_source_catalog_matches_schema_and_current_support() -> None:
    catalog = build_source_catalog(ROOT, created_at=CREATED_AT)
    schema = load_schemas(ROOT)["source_catalog"]

    assert not list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(catalog))
    assert catalog["schema_version"] == "apw.source_catalog.v0"
    assert catalog["generated_at"] == CREATED_AT
    assert catalog["summary"]["provider_count"] == 5
    assert catalog["summary"]["source_count"] == 21
    assert catalog["summary"]["enabled_deterministic_source_count"] == 21
    assert catalog["summary"]["validated_source_count"] == 21
    assert catalog["summary"]["candidate_backlog_count"] == 0
    assert catalog["summary"]["cadence_counts"] == {"daily": 19, "hourly": 2}
    assert "no raw provider content" in catalog["catalog_policy"]

    providers = {provider["provider_ref"]: provider for provider in catalog["providers"]}
    assert providers["provider:openai"]["display_name"] == "OpenAI"
    assert providers["provider:openai"]["source_count"] == 6
    assert providers["provider:openai"]["validated_source_count"] == 6
    assert providers["provider:openai"]["latest_event_date"] == "2026-06-16"
    assert "pricing_page" in providers["provider:openai"]["source_types"]
    assert "status_incident" in providers["provider:openai"]["impact_hints"]

    sources = {source["key"]: source for source in catalog["sources"]}
    assert sources["openai.status"]["cadence"] == "hourly"
    assert sources["openai.status"]["validation_status"] == "validated"
    assert sources["openai.status"]["parser_fixture_count"] == 1
    assert sources["openai.status"]["source_state"]["http_status"] == 200
    assert sources["openai.status"]["source_state"]["content_sha256"]
    assert sources["google.vertex_pricing"]["cadence"] == "daily"
    assert sources["azure_openai.whats_new"]["reviewed_event_count"] >= 1
