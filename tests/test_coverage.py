from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.coverage import build_source_coverage_report

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-08T12:00:00Z"
STALE_CREATED_AT = "2026-06-14T18:00:00Z"


def test_source_coverage_report_matches_schema_and_current_gaps() -> None:
    report = build_source_coverage_report(ROOT, created_at=CREATED_AT)
    schema = load_schemas(ROOT)["source_coverage"]

    assert not list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    assert report["schema_version"] == "apw.source_coverage.v0"
    assert report["generated_at"] == CREATED_AT
    assert report["summary"] == {
        "provider_count": 5,
        "source_count": 19,
        "enabled_deterministic_source_count": 18,
        "fetched_enabled_source_count": 18,
        "missing_enabled_source_count": 0,
        "fetched_enabled_source_ratio": 1.0,
        "manual_review_only_source_count": 1,
        "blocked_pending_parser_source_count": 0,
        "reviewed_event_count": 33,
        "latest_event_date": "2026-06-10",
        "candidate_backlog_count": 9,
        "warning_count": 1,
    }
    assert report["source_state"]["source_count"] == 18
    assert report["candidate_backlog"]["by_status"] == {"needs_review": 9}
    assert "no raw provider content" in report["coverage_policy"]


def test_source_coverage_reports_provider_gaps_and_blocked_sources() -> None:
    report = build_source_coverage_report(ROOT, created_at=CREATED_AT)
    providers = {item["provider_ref"]: item for item in report["providers"]}

    assert providers["provider:openai"]["missing_enabled_source_keys"] == []
    assert providers["provider:openai"]["blocked_pending_parser_source_count"] == 0
    assert providers["provider:google"]["missing_enabled_source_keys"] == []
    assert providers["provider:azure-openai"]["missing_enabled_source_keys"] == []
    assert providers["provider:aws-bedrock"]["missing_enabled_source_keys"] == []
    assert providers["provider:anthropic"]["missing_enabled_source_keys"] == []

    sources = {item["key"]: item for item in report["sources"]}
    assert sources["openai.deprecations"]["coverage_status"] == "enabled_fetched"
    assert sources["openai.deprecations"]["parser_fixture_count"] == 1
    assert sources["openai.codex_docs"]["coverage_status"] == "manual_review_only"
    assert sources["openai.codex_docs"]["parser_fixture_count"] == 0
    assert sources["openai.news"]["coverage_status"] == "enabled_fetched"


def test_source_coverage_warnings_are_structured_visibility_signals() -> None:
    report = build_source_coverage_report(ROOT, created_at=STALE_CREATED_AT)
    warning_codes = [warning["code"] for warning in report["warnings"]]

    assert warning_codes.count("enabled_source_missing_source_state") == 0
    assert warning_codes.count("blocked_official_source") == 0
    assert warning_codes.count("candidate_backlog_present") == 1
    assert "source_state_stale" in warning_codes
    assert not [
        warning["source_key"]
        for warning in report["warnings"]
        if warning["code"] == "enabled_source_missing_source_state"
    ]
