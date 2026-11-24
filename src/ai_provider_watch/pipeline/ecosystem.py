from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ai_provider_watch.core.feeds import filter_events, load_events
from ai_provider_watch.pipeline.notifications import (
    DEFAULT_SOURCE_URL,
    UNTRUSTED_INPUT_POLICY,
    compact_notification_event,
    parse_since,
)

ECOSYSTEM_TARGETS = {
    "litellm": {
        "display_name": "LiteLLM",
        "category": "gateway",
        "url": "https://docs.litellm.ai/",
        "strategy": "gateway_config_annotation",
    },
    "models-dev": {
        "display_name": "models.dev",
        "category": "model_catalog",
        "url": "https://github.com/anomalyco/models.dev",
        "strategy": "catalog_annotation",
    },
    "langfuse": {
        "display_name": "Langfuse",
        "category": "observability",
        "url": "https://langfuse.com/docs/observability/features/observation-types",
        "strategy": "trace_event_annotation",
    },
    "helicone": {
        "display_name": "Helicone",
        "category": "observability",
        "url": "https://docs.helicone.ai/features/advanced-usage/custom-properties",
        "strategy": "request_property_annotation",
    },
    "openlit": {
        "display_name": "OpenLIT",
        "category": "observability",
        "url": "https://docs.openlit.io/latest/openlit/observability/tracing",
        "strategy": "otel_attribute_annotation",
    },
}

PROVIDER_TARGET_PREFIXES = {
    "provider:openai": ["openai"],
    "provider:anthropic": ["anthropic"],
    "provider:google": ["gemini", "vertex_ai"],
    "provider:aws-bedrock": ["bedrock"],
    "provider:azure-openai": ["azure"],
}


def _created_at(value: str | None) -> str:
    if value:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _selected_events(
    root: Path,
    *,
    since: str,
    risk: str | None,
    provider: str | None,
    kind: str | None,
    event_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 100:
        raise ValueError("ecosystem mapping limit must be between 1 and 100")
    cutoff = parse_since(since)
    events = filter_events(load_events(root), provider=provider, min_severity=risk)
    selected = [
        event
        for event in events
        if date.fromisoformat(event["event_date"]) >= cutoff
        and (kind is None or event.get("event_kind") == kind)
        and (event_id is None or event.get("id") == event_id)
    ]
    return selected[:limit]


def _filters(
    *,
    since: str,
    risk: str | None,
    provider: str | None,
    kind: str | None,
    event_id: str | None,
    limit: int,
) -> dict[str, Any]:
    return {
        "since": since,
        "risk": risk,
        "provider": provider,
        "kind": kind,
        "event_id": event_id,
        "limit": limit,
    }


def _detail_ref_values(event: dict[str, Any], key: str) -> list[str]:
    detail = event.get("detail", {})
    if not isinstance(detail, dict):
        return []
    refs = detail.get(key, [])
    if not isinstance(refs, list):
        return []
    return [ref for ref in refs if isinstance(ref, str)]


def _model_ref_id(ref: str) -> str:
    return ref.split(":", 1)[1] if ref.startswith("model:") else ref


def _target_model_ids(event: dict[str, Any]) -> list[str]:
    refs = [*_detail_ref_values(event, "model_refs"), *_detail_ref_values(event, "replacement_refs")]
    provider_prefixes = [
        prefix
        for provider_ref in event.get("provider_refs", [])
        for prefix in PROVIDER_TARGET_PREFIXES.get(provider_ref, [])
    ]
    model_ids: set[str] = set()
    for ref in refs:
        model_id = _model_ref_id(ref)
        if "/" in model_id:
            model_ids.add(model_id)
            continue
        for prefix in provider_prefixes:
            model_ids.add(f"{prefix}/{model_id}")
        model_ids.add(model_id)
    return sorted(model_ids)


def _base_record(event: dict[str, Any]) -> dict[str, Any]:
    compact = compact_notification_event(event)
    return {
        "event": compact,
        "lookup": {
            "provider_refs": event.get("provider_refs", []),
            "model_refs": _detail_ref_values(event, "model_refs"),
            "replacement_refs": _detail_ref_values(event, "replacement_refs"),
            "target_model_ids": _target_model_ids(event),
            "impact_scope_refs": [
                impact["scope_ref"]
                for impact in event.get("impacts", [])
                if isinstance(impact, dict) and isinstance(impact.get("scope_ref"), str)
            ],
        },
    }


def _event_tags(event: dict[str, Any], target: str) -> list[str]:
    return [
        "apw",
        f"apw.target:{target}",
        f"apw.event:{event['id']}",
        f"apw.kind:{event['event_kind']}",
        f"apw.severity:{event['severity']}",
        *event.get("provider_refs", []),
    ]


def _litellm_record(event: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(event)
    record["mapping"] = {
        "strategy": "gateway_config_annotation",
        "config_file_hints": ["litellm_config.yaml", "litellm.yaml", "config.yaml"],
        "search_paths": ["model_list[].model_name", "model_list[].litellm_params.model"],
        "model_id_candidates": record["lookup"]["target_model_ids"],
        "suggested_checks": [
            "Search LiteLLM proxy configs for affected model IDs and replacements.",
            "Review routing, fallback, budget, and virtual-key policy for matched models.",
            "Do not overwrite LiteLLM pricing/catalog rows from APW without maintainer review.",
        ],
    }
    return record


def _models_dev_record(event: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(event)
    record["mapping"] = {
        "strategy": "catalog_annotation",
        "api_lookup_url": "https://models.dev/api.json",
        "repo_path_hints": ["providers/{provider}/models/{model}.toml"],
        "model_id_candidates": record["lookup"]["target_model_ids"],
        "suggested_catalog_fields": ["status", "last_updated", "cost", "limit"],
        "suggested_status": "deprecated"
        if event.get("event_kind") in {"model_deprecation", "model_retirement"}
        else "review",
    }
    return record


def _langfuse_record(event: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(event)
    record["mapping"] = {
        "strategy": "trace_event_annotation",
        "observation_type": "event",
        "timestamp": event.get("effective_at") or f"{event['event_date']}T00:00:00Z",
        "name": f"apw.{event['event_kind']}",
        "tags": _event_tags(event, "langfuse"),
        "metadata": {
            "apw_event_id": event["id"],
            "apw_severity": event["severity"],
            "apw_provider_refs": event.get("provider_refs", []),
            "apw_model_refs": record["lookup"]["target_model_ids"],
        },
    }
    return record


def _helicone_record(event: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(event)
    record["mapping"] = {
        "strategy": "request_property_annotation",
        "custom_properties": {
            "Helicone-Property-APW-Event-Id": event["id"],
            "Helicone-Property-APW-Severity": event["severity"],
            "Helicone-Property-APW-Kind": event["event_kind"],
        },
        "query_filter_hint": {
            "request_response_rmt": {
                "properties": {
                    "APW-Event-Id": {"equals": event["id"]},
                }
            }
        },
    }
    return record


def _openlit_record(event: dict[str, Any]) -> dict[str, Any]:
    record = _base_record(event)
    record["mapping"] = {
        "strategy": "otel_attribute_annotation",
        "resource_or_span_attributes": {
            "apw.event_id": event["id"],
            "apw.event_kind": event["event_kind"],
            "apw.severity": event["severity"],
            "apw.provider_refs": ",".join(event.get("provider_refs", [])),
        },
        "group_by_hints": ["gen_ai.request.model", "gen_ai.system", "service.name", "apw.event_id"],
        "timeline_timestamp": event.get("effective_at") or f"{event['event_date']}T00:00:00Z",
    }
    return record


RECORD_BUILDERS = {
    "litellm": _litellm_record,
    "models-dev": _models_dev_record,
    "langfuse": _langfuse_record,
    "helicone": _helicone_record,
    "openlit": _openlit_record,
}


def build_ecosystem_mapping(
    root: Path,
    *,
    target: str,
    since: str = "7d",
    risk: str | None = None,
    provider: str | None = None,
    kind: str | None = None,
    event_id: str | None = None,
    limit: int = 20,
    created_at: str | None = None,
    source_url: str = DEFAULT_SOURCE_URL,
) -> dict[str, Any]:
    if target not in ECOSYSTEM_TARGETS:
        raise ValueError(f"unknown ecosystem target: {target}")
    selected = _selected_events(
        root,
        since=since,
        risk=risk,
        provider=provider,
        kind=kind,
        event_id=event_id,
        limit=limit,
    )
    filters = _filters(since=since, risk=risk, provider=provider, kind=kind, event_id=event_id, limit=limit)
    target_meta = ECOSYSTEM_TARGETS[target]
    return {
        "schema_version": "apw.ecosystem_mapping.v0",
        "generated_at": _created_at(created_at),
        "source": {
            "name": "AI Provider Watch",
            "url": source_url,
            "license": "CC0-1.0",
        },
        "target": {
            "id": target,
            **target_meta,
        },
        "filters": filters,
        "event_count": len(selected),
        "records": [RECORD_BUILDERS[target](event) for event in selected],
        "untrusted_input_policy": UNTRUSTED_INPUT_POLICY,
        "delivery_boundary": "mapping_only_no_third_party_api_calls",
    }
