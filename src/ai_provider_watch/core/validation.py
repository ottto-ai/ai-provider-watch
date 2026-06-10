from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.feeds import build_artifacts
from ai_provider_watch.core.io import candidate_paths, event_paths, read_json
from ai_provider_watch.core.issues import ValidationIssue
from ai_provider_watch.core.temporal import is_rfc3339_date_time
from ai_provider_watch.source_watch.fixtures import validate_parser_fixtures
from ai_provider_watch.sources.registry import (
    is_url_allowed_for_source,
    load_source_descriptors,
    validate_source_packages,
)

SCHEMA_FILES = {
    "event": "event.schema.json",
    "event_detail": "event-detail.schema.json",
    "impact": "impact.schema.json",
    "source": "source.schema.json",
    "observation": "observation.schema.json",
    "candidate": "candidate.schema.json",
    "candidate_quality": "candidate-quality.schema.json",
    "candidate_to_event_packet": "candidate-to-event-packet.schema.json",
    "source_owner_packet": "source-owner-packet.schema.json",
    "llm_review_request": "llm-review-request.schema.json",
    "llm_review_result": "llm-review-result.schema.json",
    "promotion_readiness": "promotion-readiness.schema.json",
    "repo_impact": "repo-impact.schema.json",
    "webhook_payload": "webhook-payload.schema.json",
    "slack_payload": "slack-payload.schema.json",
    "ecosystem_mapping": "ecosystem-mapping.schema.json",
    "json_feed": "json-feed.schema.json",
    "feed_freshness": "feed-freshness.schema.json",
    "source_coverage": "source-coverage.schema.json",
    "operations_report": "operations-report.schema.json",
    "release_manifest": "release-manifest.schema.json",
    "release_evidence_index": "release-evidence-index.schema.json",
    "release_dry_run": "release-dry-run.schema.json",
    "release_publication_packet": "release-publication-packet.schema.json",
    "release_verification": "release-verification.schema.json",
    "adoption_scenarios": "adoption-scenarios.schema.json",
    "agent_dashboard": "agent-dashboard.schema.json",
}

DETAIL_BY_EVENT_KIND = {
    "pricing_change": {"price_change", "generic_change"},
    "quota_change": {"quota_change", "generic_change"},
    "rate_limit_change": {"rate_limit_change", "generic_change"},
    "model_launch": {"model_lifecycle", "generic_change"},
    "model_deprecation": {"model_lifecycle", "generic_change"},
    "model_retirement": {"model_lifecycle", "generic_change"},
    "default_model_change": {"default_model_change", "generic_change"},
    "token_accounting_change": {"token_accounting_change", "generic_change"},
    "caching_change": {"price_change", "token_accounting_change", "generic_change"},
    "billing_channel_change": {"generic_change"},
    "api_contract_change": {"api_contract_change", "generic_change"},
    "sdk_behavior_change": {"api_contract_change", "generic_change"},
    "status_incident": {"status_incident", "generic_change"},
    "status_recovery": {"status_incident", "generic_change"},
    "subscription_change": {"subscription_change", "generic_change"},
    "terms_policy_change": {"generic_change"},
    "regional_availability_change": {"generic_change"},
    "workflow_behavior_change": {"default_model_change", "api_contract_change", "generic_change"},
    "catalog_correction": {"model_lifecycle", "generic_change"},
}


def load_schemas(root: Path) -> dict[str, dict[str, Any]]:
    return {name: read_json(root / "schemas" / filename) for name, filename in SCHEMA_FILES.items()}


def _issues(path: Path, data: Any, schema: dict[str, Any], label: str) -> list[ValidationIssue]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    found: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path)
        suffix = f" at {location}" if location else ""
        found.append(ValidationIssue(str(path), f"{label}{suffix}: {error.message}"))
    return found


def _ids(items: list[dict[str, Any]], key: str) -> set[str]:
    return {str(item[key]) for item in items if key in item}


def _duplicate_issues(path: Path, items: list[dict[str, Any]], key: str) -> list[ValidationIssue]:
    seen: set[str] = set()
    found: list[ValidationIssue] = []
    for item in items:
        value = str(item.get(key))
        if value in seen:
            found.append(ValidationIssue(str(path), f"duplicate {key}: {value}"))
        seen.add(value)
    return found


def _validate_registries(root: Path) -> tuple[list[ValidationIssue], dict[str, set[str]]]:
    issues: list[ValidationIssue] = []
    providers_path = root / "registries" / "providers.json"
    surfaces_path = root / "registries" / "provider-surfaces.json"
    apps_path = root / "registries" / "agent-apps.json"
    models_path = root / "registries" / "models.json"

    providers = read_json(providers_path).get("providers", [])
    surfaces = read_json(surfaces_path).get("surfaces", [])
    apps = read_json(apps_path).get("agent_apps", [])
    models = read_json(models_path).get("models", [])

    issues.extend(_duplicate_issues(providers_path, providers, "id"))
    issues.extend(_duplicate_issues(surfaces_path, surfaces, "id"))
    issues.extend(_duplicate_issues(apps_path, apps, "id"))

    provider_ids = _ids(providers, "id")
    for surface in surfaces:
        provider_id = surface.get("provider_id")
        if provider_id not in provider_ids:
            issues.append(ValidationIssue(str(surfaces_path), f"surface {surface.get('id')} references unknown provider {provider_id}"))

    return issues, {
        "provider": {f"provider:{item}" for item in provider_ids},
        "surface": {f"surface:{item}" for item in _ids(surfaces, "id")},
        "app": {f"app:{item}" for item in _ids(apps, "id")},
        "model": {f"model:{item}" for item in _ids(models, "id")},
    }


def _validate_sources(root: Path, source_schema: dict[str, Any], providers: set[str]) -> tuple[list[ValidationIssue], set[str]]:
    path = root / "sources" / "registry.json"
    registry = read_json(path)
    issues = _issues(path, registry, source_schema, "source registry")
    sources = registry.get("sources", [])
    issues.extend(_duplicate_issues(path, sources, "key"))
    source_keys = _ids(sources, "key")

    for source in sources:
        for provider_ref in source.get("provider_refs", []):
            if provider_ref not in providers:
                issues.append(ValidationIssue(str(path), f"source {source.get('key')} references unknown provider {provider_ref}"))

    for package_path in sorted((root / "sources").glob("*/source.json")):
        package = read_json(package_path)
        for source_key in package.get("source_keys", []):
            if source_key not in source_keys:
                issues.append(ValidationIssue(str(package_path), f"source package references unknown source key {source_key}"))
    return issues, source_keys


def _known_ref(ref: str, known_refs: dict[str, set[str]]) -> bool:
    kind = ref.split(":", 1)[0]
    if kind in {"plan", "endpoint", "sdk", "gateway", "region", "account"}:
        return True
    return ref in known_refs.get(kind, set())


def _candidate_time_issues(path: Path, candidate: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    created_at = candidate.get("created_at")
    if isinstance(created_at, str) and not is_rfc3339_date_time(created_at):
        issues.append(ValidationIssue(str(path), "candidate created_at must be RFC 3339 date-time"))

    evidence_refs = candidate.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        return issues
    for index, evidence in enumerate(evidence_refs):
        if not isinstance(evidence, dict):
            continue
        retrieved_at = evidence.get("retrieved_at")
        if isinstance(retrieved_at, str) and not is_rfc3339_date_time(retrieved_at):
            issues.append(
                ValidationIssue(
                    str(path),
                    f"candidate evidence_refs.{index}.retrieved_at must be RFC 3339 date-time",
                )
            )
    return issues


def validate(root: Path) -> list[ValidationIssue]:
    schemas = load_schemas(root)
    issues: list[ValidationIssue] = []
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover
            issues.append(ValidationIssue(f"schemas/{SCHEMA_FILES[name]}", str(exc)))

    registry_issues, known_refs = _validate_registries(root)
    issues.extend(registry_issues)
    source_issues, source_keys = _validate_sources(root, schemas["source"], known_refs["provider"])
    issues.extend(source_issues)
    issues.extend(validate_source_packages(root))
    issues.extend(validate_parser_fixtures(root))
    sources_by_key = {
        source.key: source for source in load_source_descriptors(root, enabled_only=False)
    }

    event_ids: set[str] = set()
    for event_path in event_paths(root):
        event = read_json(event_path)
        issues.extend(_issues(event_path, event, schemas["event"], "event"))
        issues.extend(_issues(event_path, event.get("detail", {}), schemas["event_detail"], "detail"))
        for index, impact in enumerate(event.get("impacts", [])):
            issues.extend(_issues(event_path, impact, schemas["impact"], f"impact[{index}]"))

        event_id = event.get("id")
        if event_id in event_ids:
            issues.append(ValidationIssue(str(event_path), f"duplicate event id {event_id}"))
        event_ids.add(event_id)

        detail_kind = event.get("detail", {}).get("kind")
        if detail_kind and detail_kind not in DETAIL_BY_EVENT_KIND.get(event.get("event_kind"), set()):
            issues.append(ValidationIssue(str(event_path), f"detail kind {detail_kind} is not valid for event kind {event.get('event_kind')}"))
        for provider_ref in event.get("provider_refs", []):
            if not _known_ref(provider_ref, known_refs):
                issues.append(ValidationIssue(str(event_path), f"unknown provider ref {provider_ref}"))
        for evidence in event.get("evidence_refs", []):
            if evidence.get("source_key") not in source_keys:
                issues.append(ValidationIssue(str(event_path), f"unknown evidence source key {evidence.get('source_key')}"))
        for impact in event.get("impacts", []):
            scope_ref = impact.get("scope_ref")
            if isinstance(scope_ref, str) and ":" in scope_ref and not _known_ref(scope_ref, known_refs):
                issues.append(ValidationIssue(str(event_path), f"unknown impact scope {scope_ref}"))

    candidate_ids: set[str] = set()
    for candidate_path in candidate_paths(root):
        candidate = read_json(candidate_path)
        issues.extend(_issues(candidate_path, candidate, schemas["candidate"], "candidate"))
        if not isinstance(candidate, dict):
            continue
        issues.extend(_candidate_time_issues(candidate_path, candidate))
        candidate_id = candidate.get("id")
        if isinstance(candidate_id, str):
            if candidate_id in candidate_ids:
                issues.append(ValidationIssue(str(candidate_path), f"duplicate candidate id {candidate_id}"))
            candidate_ids.add(candidate_id)
        candidate_provider_refs = candidate.get("provider_refs", [])
        if isinstance(candidate_provider_refs, list):
            for provider_ref in candidate_provider_refs:
                if isinstance(provider_ref, str) and not _known_ref(provider_ref, known_refs):
                    issues.append(
                        ValidationIssue(str(candidate_path), f"unknown provider ref {provider_ref}")
                    )
        candidate_source_keys = candidate.get("source_keys", [])
        candidate_source_key_values: set[str] = set()
        if isinstance(candidate_source_keys, list):
            for source_key in candidate_source_keys:
                if isinstance(source_key, str) and source_key not in source_keys:
                    issues.append(
                        ValidationIssue(
                            str(candidate_path), f"unknown candidate source key {source_key}"
                        )
                    )
                if isinstance(source_key, str):
                    candidate_source_key_values.add(source_key)
        candidate_evidence_refs = candidate.get("evidence_refs", [])
        candidate_evidence_source_key_values: set[str] = set()
        if isinstance(candidate_evidence_refs, list):
            for evidence in candidate_evidence_refs:
                if not isinstance(evidence, dict):
                    continue
                evidence_source_key = evidence.get("source_key")
                if isinstance(evidence_source_key, str):
                    candidate_evidence_source_key_values.add(evidence_source_key)
                if (
                    isinstance(evidence_source_key, str)
                    and candidate_source_key_values
                    and evidence_source_key not in candidate_source_key_values
                ):
                    issues.append(
                        ValidationIssue(
                            str(candidate_path),
                            f"candidate evidence source key {evidence_source_key} is not declared in source_keys",
                        )
                    )
                if not isinstance(evidence_source_key, str):
                    continue
                if evidence_source_key not in source_keys:
                    issues.append(
                        ValidationIssue(
                            str(candidate_path),
                            f"unknown candidate evidence source key {evidence_source_key}",
                        )
                    )
                    continue
                evidence_source = sources_by_key.get(evidence_source_key)
                evidence_url = evidence.get("url")
                if (
                    evidence_source is not None
                    and isinstance(evidence_url, str)
                    and not is_url_allowed_for_source(evidence_url, evidence_source)
                ):
                    issues.append(
                        ValidationIssue(
                            str(candidate_path),
                            f"candidate evidence url is outside allowed domains for {evidence_source.key}: {evidence_url}",
                        )
                    )
                if evidence_source is not None and evidence.get("authority") != evidence_source.authority:
                    issues.append(
                        ValidationIssue(
                            str(candidate_path),
                            f"candidate evidence authority does not match source {evidence_source.key}: {evidence.get('authority')}",
                        )
                    )
        if candidate_source_key_values != candidate_evidence_source_key_values:
            issues.append(
                ValidationIssue(
                    str(candidate_path),
                    "candidate source_keys must match evidence source keys",
                )
            )
        allowed_candidate_provider_refs: set[str] = set()
        for source_key in candidate_evidence_source_key_values:
            source = sources_by_key.get(source_key)
            if source is not None:
                allowed_candidate_provider_refs.update(source.provider_refs)
        if allowed_candidate_provider_refs and isinstance(candidate_provider_refs, list):
            for provider_ref in candidate_provider_refs:
                if (
                    isinstance(provider_ref, str)
                    and provider_ref not in allowed_candidate_provider_refs
                ):
                    issues.append(
                        ValidationIssue(
                            str(candidate_path),
                            f"candidate provider ref {provider_ref} is not declared by candidate evidence sources",
                        )
                    )

    if (root / "examples").exists():
        adoption_scenarios_path = root / "examples" / "adoption" / "scenarios.json"
        if not adoption_scenarios_path.exists():
            issues.append(
                ValidationIssue(
                    str(adoption_scenarios_path),
                    "missing adoption scenarios manifest",
                )
            )
        else:
            issues.extend(
                _issues(
                    adoption_scenarios_path,
                    read_json(adoption_scenarios_path),
                    schemas["adoption_scenarios"],
                    "adoption scenarios",
                )
            )

    manifest_path = root / "data" / "releases" / "dev" / "manifest.json"
    if manifest_path.exists():
        issues.extend(_issues(manifest_path, read_json(manifest_path), schemas["release_manifest"], "release manifest"))
    freshness_path = root / "data" / "feeds" / "freshness.json"
    if not freshness_path.exists():
        issues.append(ValidationIssue(str(freshness_path), "missing feed freshness metadata"))
    else:
        freshness = read_json(freshness_path)
        issues.extend(_issues(freshness_path, freshness, schemas["feed_freshness"], "feed freshness"))
        expected_freshness_text = build_artifacts(root)[Path("data/feeds/freshness.json")]
        expected_freshness = json.loads(expected_freshness_text)
        if freshness != expected_freshness:
            issues.append(
                ValidationIssue(
                    str(freshness_path),
                    "feed freshness metadata is stale; run apw index",
                )
            )
    coverage_path = root / "data" / "feeds" / "coverage.json"
    if not coverage_path.exists():
        issues.append(ValidationIssue(str(coverage_path), "missing source coverage metadata"))
    else:
        coverage = read_json(coverage_path)
        issues.extend(_issues(coverage_path, coverage, schemas["source_coverage"], "source coverage"))
        expected_coverage_text = build_artifacts(root)[Path("data/feeds/coverage.json")]
        expected_coverage = json.loads(expected_coverage_text)
        if coverage != expected_coverage:
            issues.append(
                ValidationIssue(
                    str(coverage_path),
                    "source coverage metadata is stale; run apw index",
                )
            )
    operations_path = root / "data" / "feeds" / "operations.json"
    if not operations_path.exists():
        issues.append(ValidationIssue(str(operations_path), "missing operations report metadata"))
    else:
        operations = read_json(operations_path)
        issues.extend(_issues(operations_path, operations, schemas["operations_report"], "operations report"))
        expected_operations_text = build_artifacts(root)[Path("data/feeds/operations.json")]
        expected_operations = json.loads(expected_operations_text)
        if operations != expected_operations:
            issues.append(
                ValidationIssue(
                    str(operations_path),
                    "operations report metadata is stale; run apw index",
                )
            )
    json_feed_path = root / "data" / "feeds" / "feed.json"
    if not json_feed_path.exists():
        issues.append(ValidationIssue(str(json_feed_path), "missing JSON Feed metadata"))
    else:
        json_feed = read_json(json_feed_path)
        issues.extend(_issues(json_feed_path, json_feed, schemas["json_feed"], "JSON Feed"))
        expected_json_feed_text = build_artifacts(root)[Path("data/feeds/feed.json")]
        expected_json_feed = json.loads(expected_json_feed_text)
        if json_feed != expected_json_feed:
            issues.append(
                ValidationIssue(
                    str(json_feed_path),
                    "JSON Feed metadata is stale; run apw index",
                )
            )
    return issues
