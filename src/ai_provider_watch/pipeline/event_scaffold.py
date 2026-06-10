from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENT_KIND_TO_LIFECYCLE_ACTION = {
    "model_launch": "launch",
    "model_deprecation": "deprecation",
    "model_retirement": "retirement",
    "catalog_correction": "correction",
}

EVENT_KIND_TO_DETAIL_KIND = {
    "pricing_change": "price_change",
    "quota_change": "quota_change",
    "rate_limit_change": "rate_limit_change",
    "model_launch": "model_lifecycle",
    "model_deprecation": "model_lifecycle",
    "model_retirement": "model_lifecycle",
    "default_model_change": "default_model_change",
    "token_accounting_change": "token_accounting_change",
    "api_contract_change": "api_contract_change",
    "sdk_behavior_change": "api_contract_change",
    "status_incident": "status_incident",
    "status_recovery": "status_incident",
    "subscription_change": "subscription_change",
    "catalog_correction": "model_lifecycle",
}

DETAIL_KIND_TO_EVENT_KINDS = {
    "api_contract_change": {"api_contract_change", "sdk_behavior_change", "workflow_behavior_change"},
    "default_model_change": {"default_model_change", "workflow_behavior_change"},
    "generic_change": {
        "api_contract_change",
        "billing_channel_change",
        "caching_change",
        "catalog_correction",
        "default_model_change",
        "model_deprecation",
        "model_launch",
        "model_retirement",
        "pricing_change",
        "quota_change",
        "rate_limit_change",
        "regional_availability_change",
        "sdk_behavior_change",
        "status_incident",
        "status_recovery",
        "subscription_change",
        "terms_policy_change",
        "token_accounting_change",
        "workflow_behavior_change",
    },
    "model_lifecycle": {
        "catalog_correction",
        "model_deprecation",
        "model_launch",
        "model_retirement",
    },
    "price_change": {"caching_change", "pricing_change"},
    "quota_change": {"quota_change"},
    "rate_limit_change": {"rate_limit_change"},
    "status_incident": {"status_incident", "status_recovery"},
    "subscription_change": {"subscription_change"},
    "token_accounting_change": {"caching_change", "token_accounting_change"},
}

DEFAULT_WHO_SHOULD_CARE = ["platform_engineers", "product_engineers"]
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class EventScaffoldError(ValueError):
    """Raised when scaffold inputs cannot produce a valid event draft."""


def normalize_ref(value: str, *, prefix: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise EventScaffoldError(f"{prefix} ref is required")
    return normalized if normalized.startswith(f"{prefix}:") else f"{prefix}:{normalized}"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "provider-event"


def event_id_from_parts(*, event_date: str, provider_ref: str, title: str) -> str:
    provider_slug = provider_ref.split(":", 1)[1].replace("_", "-").replace("/", "-")
    title_slug = slugify(title)
    prefix = f"{event_date}-{provider_slug}-"
    max_title_len = max(24, 120 - len(prefix))
    return f"{prefix}{title_slug[:max_title_len].strip('-')}"


def _rfc3339_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_list(values: list[str] | None) -> list[str]:
    return [value for value in (values or []) if value]


def _detail(
    *,
    event_kind: str,
    detail_kind: str,
    summary: str,
    model_refs: list[str],
    replacement_refs: list[str],
    lifecycle_action: str | None,
    deadline: str | None,
    migration_notes: str | None,
    surface_ref: str,
    new_default: str | None,
    old_default: str | None,
    status: str | None,
    component: list[str],
) -> dict[str, Any]:
    if detail_kind == "generic_change":
        return {
            "kind": "generic_change",
            "schema_version": "apw.event_detail.v0",
            "change_summary": summary,
        }
    if event_kind not in DETAIL_KIND_TO_EVENT_KINDS.get(detail_kind, set()):
        raise EventScaffoldError(f"detail kind {detail_kind} is not valid for event kind {event_kind}")
    if detail_kind == "model_lifecycle":
        if not model_refs:
            raise EventScaffoldError("--model-ref is required for model lifecycle scaffolds")
        return {
            "kind": "model_lifecycle",
            "schema_version": "apw.event_detail.v0",
            "model_refs": model_refs,
            "lifecycle_action": lifecycle_action
            or EVENT_KIND_TO_LIFECYCLE_ACTION.get(event_kind, "correction"),
            "replacement_refs": replacement_refs,
            "deadline": deadline,
            "migration_notes": migration_notes or summary,
        }
    if detail_kind == "status_incident":
        return {
            "kind": "status_incident",
            "schema_version": "apw.event_detail.v0",
            "provider_incident_id": None,
            "status": status or "unknown",
            "started_at": None,
            "resolved_at": None,
            "components": component,
            "raw_status": None,
        }
    if detail_kind == "price_change":
        return {
            "kind": "price_change",
            "schema_version": "apw.event_detail.v0",
            "currency": "USD",
            "price_items": [{"summary": summary}],
        }
    if detail_kind == "quota_change":
        return {
            "kind": "quota_change",
            "schema_version": "apw.event_detail.v0",
            "window": None,
            "reset_policy": None,
            "quota_items": [{"summary": summary}],
        }
    if detail_kind == "rate_limit_change":
        return {
            "kind": "rate_limit_change",
            "schema_version": "apw.event_detail.v0",
            "rate_items": [{"summary": summary}],
        }
    if detail_kind == "default_model_change":
        if not new_default:
            raise EventScaffoldError("--new-default is required for default model scaffolds")
        return {
            "kind": "default_model_change",
            "schema_version": "apw.event_detail.v0",
            "surface_ref": surface_ref,
            "old_default": old_default,
            "new_default": new_default,
            "rollout_window": None,
            "fallback_policy": None,
        }
    if detail_kind == "token_accounting_change":
        return {
            "kind": "token_accounting_change",
            "schema_version": "apw.event_detail.v0",
            "metered_units": ["tokens"],
            "old_accounting": None,
            "new_accounting": summary,
        }
    if detail_kind == "api_contract_change":
        return {
            "kind": "api_contract_change",
            "schema_version": "apw.event_detail.v0",
            "endpoint_refs": [surface_ref],
            "changed_parameters": [],
            "compatibility": "unknown",
            "migration_deadline": deadline,
        }
    if detail_kind == "subscription_change":
        return {
            "kind": "subscription_change",
            "schema_version": "apw.event_detail.v0",
            "plan_refs": [surface_ref],
            "entitlement_changes": [summary],
            "old_terms": None,
            "new_terms": None,
            "effective_at": None,
        }
    raise EventScaffoldError(f"unsupported detail kind: {detail_kind}")


def build_event_scaffold(
    *,
    event_date: str,
    provider: str,
    event_kind: str,
    title: str,
    summary: str,
    source_url: str,
    source_key: str,
    source_authority: str,
    content_sha256: str,
    scope_ref: str,
    impact_kind: str,
    direction: str,
    severity: str = "medium",
    confidence: str = "confirmed",
    observed_at: str | None = None,
    event_id: str | None = None,
    lifecycle_status: str = "reviewed",
    date_confidence: str = "exact",
    announced_at: str | None = None,
    effective_at: str | None = None,
    expires_at: str | None = None,
    migration_deadline: str | None = None,
    detail_kind: str = "auto",
    model_refs: list[str] | None = None,
    replacement_refs: list[str] | None = None,
    lifecycle_action: str | None = None,
    migration_notes: str | None = None,
    new_default: str | None = None,
    old_default: str | None = None,
    status: str | None = None,
    components: list[str] | None = None,
    scope_type: str = "provider_surface",
    subscription_impact: str = "unknown",
    api_usage_impact: str = "direct",
    who_should_care: list[str] | None = None,
    recommended_action: str | None = None,
    selector: str | None = None,
    snapshot_ref: str | None = None,
    license_note: str | None = None,
    tags: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    provider_ref = normalize_ref(provider, prefix="provider")
    surface_ref = scope_ref.strip()
    if not surface_ref:
        raise EventScaffoldError("--scope-ref is required")
    if not SHA256_PATTERN.fullmatch(content_sha256):
        raise EventScaffoldError("--content-sha256 must be a lowercase SHA-256 hex digest")
    selected_detail_kind = EVENT_KIND_TO_DETAIL_KIND.get(event_kind, "generic_change") if detail_kind == "auto" else detail_kind
    model_ref_values = [normalize_ref(value, prefix="model") for value in _optional_list(model_refs)]
    replacement_ref_values = [
        normalize_ref(value, prefix="model") for value in _optional_list(replacement_refs)
    ]
    scaffold_id = event_id or event_id_from_parts(
        event_date=event_date,
        provider_ref=provider_ref,
        title=title,
    )
    observed_value = observed_at or _rfc3339_now()
    evidence = {
        "source_key": source_key,
        "url": source_url,
        "retrieved_at": observed_value,
        "authority": source_authority,
        "content_sha256": content_sha256,
        "license_note": license_note
        or "Official source reviewed for factual metadata; no provider prose copied.",
    }
    if snapshot_ref is not None:
        evidence["snapshot_ref"] = snapshot_ref
    if selector is not None:
        evidence["selector"] = selector
    event = {
        "schema_version": "apw.provider_event.v0",
        "id": scaffold_id,
        "title": title,
        "event_kind": event_kind,
        "lifecycle_status": lifecycle_status,
        "provider_refs": [provider_ref],
        "event_date": event_date,
        "date_confidence": date_confidence,
        "observed_at": observed_value,
        "announced_at": announced_at,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "migration_deadline": migration_deadline,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "source_authority": source_authority,
        "evidence_refs": [evidence],
        "impacts": [
            {
                "scope_type": scope_type,
                "scope_ref": surface_ref,
                "impact_kind": impact_kind,
                "direction": direction,
                "severity": severity,
                "confidence": confidence,
                "subscription_impact": subscription_impact,
                "api_usage_impact": api_usage_impact,
                "who_should_care": who_should_care or DEFAULT_WHO_SHOULD_CARE,
                "recommended_action": recommended_action
                or "Review the official source and decide whether downstream routing, budgets, tests, or migration plans need updates.",
            }
        ],
        "detail": _detail(
            event_kind=event_kind,
            detail_kind=selected_detail_kind,
            summary=summary,
            model_refs=model_ref_values,
            replacement_refs=replacement_ref_values,
            lifecycle_action=lifecycle_action,
            deadline=migration_deadline,
            migration_notes=migration_notes,
            surface_ref=surface_ref,
            new_default=new_default,
            old_default=old_default,
            status=status,
            component=_optional_list(components),
        ),
        "tags": tags
        or [
            f"source:{source_authority}",
            provider_ref,
            f"impact:{event_kind}",
        ],
        "limitations": limitations or [],
    }
    return event
