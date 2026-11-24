from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import event_paths, read_json
from ai_provider_watch.pipeline.coverage import build_source_coverage_report

OPERATIONS_REPORT_SCHEMA_VERSION = "apw.operations_report.v0"
SOURCE_STATE_FRESHNESS_TARGET_HOURS = 72
REVIEWED_EVENT_FRESHNESS_TARGET_DAYS = 14
ENABLED_SOURCE_COVERAGE_TARGET_RATIO = 0.8
CANDIDATE_BACKLOG_TARGET_COUNT = 0
REQUIRED_INTAKE_TEMPLATES = [
    ".github/ISSUE_TEMPLATE/missing_event.yml",
    ".github/ISSUE_TEMPLATE/provider_data_correction.yml",
    ".github/ISSUE_TEMPLATE/new_source.yml",
    ".github/ISSUE_TEMPLATE/downstream_mapping.yml",
]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    if len(normalized) > 10 and normalized[10] == "t":
        normalized = f"{normalized[:10]}T{normalized[11:]}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_hours(generated_at: str, observed_at: str | None) -> float | None:
    generated = _parse_rfc3339(generated_at)
    observed = _parse_rfc3339(observed_at)
    if generated is None or observed is None:
        return None
    return round(max((generated - observed).total_seconds(), 0) / 3600, 2)


def _age_days(generated_at: str, event_date: str | None) -> int | None:
    generated = _parse_rfc3339(generated_at)
    if generated is None or not event_date:
        return None
    try:
        parsed_date = date.fromisoformat(event_date)
    except ValueError:
        return None
    return max((generated.date() - parsed_date).days, 0)


def _status_for_threshold(
    *,
    actual: float | int | None,
    target: float | int,
    direction: str,
    warn_only: bool = False,
) -> str:
    if actual is None:
        return "unknown"
    passing = actual >= target if direction == "min" else actual <= target
    if passing:
        return "pass"
    return "warn" if warn_only else "fail"


def _overall_status(slo_rows: list[dict[str, Any]]) -> str:
    statuses = {row.get("status") for row in slo_rows}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    if "unknown" in statuses:
        return "unknown"
    return "pass"


def _event_correction_counts(root: Path) -> dict[str, int]:
    correction_count = 0
    retraction_count = 0
    for path in event_paths(root):
        event = read_json(path)
        if event.get("event_kind") == "catalog_correction":
            correction_count += 1
        status = str(event.get("lifecycle_status") or "")
        if status in {"retracted", "superseded"}:
            retraction_count += 1
    return {
        "correction_event_count": correction_count,
        "retracted_or_superseded_event_count": retraction_count,
    }


def _intake_template_status(root: Path) -> dict[str, Any]:
    present = [path for path in REQUIRED_INTAKE_TEMPLATES if (root / path).exists()]
    missing = [path for path in REQUIRED_INTAKE_TEMPLATES if path not in present]
    return {
        "required_templates": REQUIRED_INTAKE_TEMPLATES,
        "present_templates": present,
        "missing_templates": missing,
        "status": "pass" if not missing else "fail",
    }


def build_operations_report(
    root: Path,
    *,
    created_at: str | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = created_at or _utc_now()
    coverage_report = coverage or build_source_coverage_report(root, created_at=generated_at)
    summary = coverage_report["summary"]
    source_state = coverage_report["source_state"]
    source_state_age_hours = _age_hours(generated_at, source_state.get("latest_retrieved_at"))
    latest_event_age_days = _age_days(generated_at, summary.get("latest_event_date"))
    candidate_backlog_count = int(summary["candidate_backlog_count"])
    source_coverage_ratio = float(summary["fetched_enabled_source_ratio"])
    intake_templates = _intake_template_status(root)

    slo_rows = [
        {
            "id": "reviewed_event_freshness",
            "label": "Latest reviewed event freshness",
            "status": _status_for_threshold(
                actual=latest_event_age_days,
                target=REVIEWED_EVENT_FRESHNESS_TARGET_DAYS,
                direction="max",
                warn_only=True,
            ),
            "actual": latest_event_age_days,
            "target": REVIEWED_EVENT_FRESHNESS_TARGET_DAYS,
            "unit": "days",
            "details": "Days between generated_at and the latest reviewed ProviderEvent event_date.",
        },
        {
            "id": "source_state_freshness",
            "label": "Source-state freshness",
            "status": _status_for_threshold(
                actual=source_state_age_hours,
                target=SOURCE_STATE_FRESHNESS_TARGET_HOURS,
                direction="max",
            ),
            "actual": source_state_age_hours,
            "target": SOURCE_STATE_FRESHNESS_TARGET_HOURS,
            "unit": "hours",
            "details": "Hours since the latest deterministic source-state retrieval.",
        },
        {
            "id": "enabled_source_coverage",
            "label": "Enabled source-state coverage",
            "status": _status_for_threshold(
                actual=source_coverage_ratio,
                target=ENABLED_SOURCE_COVERAGE_TARGET_RATIO,
                direction="min",
            ),
            "actual": source_coverage_ratio,
            "target": ENABLED_SOURCE_COVERAGE_TARGET_RATIO,
            "unit": "ratio",
            "details": "Share of enabled deterministic sources with committed source-state fingerprints.",
        },
        {
            "id": "candidate_backlog",
            "label": "Review candidate backlog",
            "status": _status_for_threshold(
                actual=candidate_backlog_count,
                target=CANDIDATE_BACKLOG_TARGET_COUNT,
                direction="max",
                warn_only=True,
            ),
            "actual": candidate_backlog_count,
            "target": CANDIDATE_BACKLOG_TARGET_COUNT,
            "unit": "candidates",
            "details": "Review candidates present outside reviewed ProviderEvent data.",
        },
        {
            "id": "public_intake_templates",
            "label": "Public feedback intake templates",
            "status": intake_templates["status"],
            "actual": len(intake_templates["present_templates"]),
            "target": len(intake_templates["required_templates"]),
            "unit": "templates",
            "details": "Missing-event, correction, source, and downstream mapping templates exist.",
        },
    ]

    correction_counts = _event_correction_counts(root)
    return {
        "schema_version": OPERATIONS_REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "package_version": __version__,
        "overall_status": _overall_status(slo_rows),
        "summary": {
            "provider_count": summary["provider_count"],
            "source_count": summary["source_count"],
            "enabled_deterministic_source_count": summary["enabled_deterministic_source_count"],
            "fetched_enabled_source_count": summary["fetched_enabled_source_count"],
            "missing_enabled_source_count": summary["missing_enabled_source_count"],
            "enabled_source_coverage_ratio": source_coverage_ratio,
            "reviewed_event_count": summary["reviewed_event_count"],
            "latest_event_date": summary["latest_event_date"],
            "latest_reviewed_event_age_days": latest_event_age_days,
            "candidate_backlog_count": candidate_backlog_count,
            "source_state_latest_retrieved_at": source_state.get("latest_retrieved_at"),
            "source_state_age_hours": source_state_age_hours,
            "warning_count": summary["warning_count"],
        },
        "slos": slo_rows,
        "source_coverage": {
            "schema_version": coverage_report["schema_version"],
            "path": "data/feeds/coverage.json",
            "warning_count": len(coverage_report["warnings"]),
            "warnings": coverage_report["warnings"],
        },
        "candidate_backlog": coverage_report["candidate_backlog"],
        "contributor_quality": {
            "intake_templates": intake_templates,
            "source_owner_review_path": "docs/contributors/review-workflow.md",
            "candidate_quality_command": "uv run apw candidate quality --candidates data/candidates/review",
        },
        "correction_retraction": {
            **correction_counts,
            "latency_status": "not_measured_until_public_issue_volume",
            "target": "Document correction or retraction disposition in the next reviewed PR and release notes.",
            "policy_path": "docs/operations/v1-governance.md#correction-and-retraction-policy",
            "issue_template": ".github/ISSUE_TEMPLATE/provider_data_correction.yml",
        },
        "release_train": {
            "current_mode": "manual_signed_data_tags",
            "cadence_target": "daily CalVer data tags after guarded automation is stable",
            "automation_status": "dry_run_only_until_signing_equivalence",
            "release_gates_path": "docs/operations/release-gates.md",
            "v1_governance_path": "docs/operations/v1-governance.md",
        },
        "policy": {
            "raw_provider_content": "no raw provider content is included; report contains counts, timestamps, paths, and policy refs only",
            "publication": "operations report is visibility only and cannot publish events, tags, releases, or packages",
            "untrusted_input": "issue bodies, PR comments, social posts, MCP text, and provider pages remain untrusted data",
            "private_ottto_boundary": "no private Ottto UI, Advisor, telemetry, customer data, credentials, or infrastructure required",
        },
    }
