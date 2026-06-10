from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.operations import build_operations_report

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-10T00:00:00Z"


def test_operations_report_matches_schema_and_current_public_gaps() -> None:
    report = build_operations_report(ROOT, created_at=CREATED_AT)
    schema = load_schemas(ROOT)["operations_report"]

    assert not list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    assert report["schema_version"] == "apw.operations_report.v0"
    assert report["generated_at"] == CREATED_AT
    assert report["overall_status"] == "pass"
    assert report["summary"]["provider_count"] == 5
    assert report["summary"]["reviewed_event_count"] == 39
    assert report["summary"]["latest_event_date"] == "2026-06-10"
    assert report["summary"]["latest_reviewed_event_age_days"] == 0
    assert report["summary"]["enabled_source_coverage_ratio"] == 1.0
    assert report["summary"]["missing_enabled_source_count"] == 0
    assert report["summary"]["source_count"] == 20
    assert report["summary"]["candidate_backlog_count"] == 0
    assert report["summary"]["source_state_latest_retrieved_at"] == "2026-06-10T20:21:35Z"
    assert report["summary"]["source_state_age_hours"] == 0.0


def test_operations_report_slos_and_policy_boundaries() -> None:
    report = build_operations_report(ROOT, created_at=CREATED_AT)
    slos = {row["id"]: row for row in report["slos"]}

    assert slos["reviewed_event_freshness"]["status"] == "pass"
    assert slos["source_state_freshness"]["status"] == "pass"
    assert slos["enabled_source_coverage"]["status"] == "pass"
    assert slos["candidate_backlog"]["status"] == "pass"
    assert slos["public_intake_templates"]["status"] == "pass"
    assert report["contributor_quality"]["intake_templates"]["missing_templates"] == []
    assert report["correction_retraction"]["latency_status"] == "not_measured_until_public_issue_volume"
    assert report["release_train"]["automation_status"] == "dry_run_only_until_signing_equivalence"
    assert "no raw provider content" in report["policy"]["raw_provider_content"]
    assert "cannot publish events" in report["policy"]["publication"]
    assert "private Ottto" in report["policy"]["private_ottto_boundary"]
