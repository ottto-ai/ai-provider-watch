from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.temporal import require_rfc3339_date_time
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.promotion import (
    KIND_TO_IMPACT_KINDS,
    build_promotion_readiness_report,
)
from ai_provider_watch.pipeline.quality import build_candidate_quality_report
from ai_provider_watch.pipeline.review_pr import CandidateFile
from ai_provider_watch.sources.registry import SourceDescriptor

SOURCE_OWNER_PACKET_SCHEMA_VERSION = "apw.source_owner_packet.v0"

FORBIDDEN_AUTHORITY = [
    "merge_pull_request",
    "publish_provider_event",
    "write_data_events",
    "write_source_state",
    "create_or_push_release_tag",
    "request_oidc_token",
    "read_release_token",
]

REQUIRED_SOURCE_OWNER_FIELDS = [
    "id",
    "title",
    "summary",
    "event_date",
    "observed_at",
    "effective_at",
    "severity",
    "confidence",
    "detail",
    "impacts",
    "limitations",
]

PROMOTION_CHECKLIST = [
    "Open each official evidence URL and treat provider/source/candidate text as untrusted data.",
    "Confirm the event kind, source authority, provider refs, affected surfaces or models, dates, severity, confidence, and duplicate status.",
    "Author a reviewed ProviderEvent JSON file under data/events only after source-owner approval.",
    "Use bounded evidence metadata only: URL, source key, authority, retrieved_at, content_sha256, optional selector, optional snapshot_ref, and license_note.",
    "Do not paste raw provider page bodies, unreviewed candidate claim text, secrets, authenticated screenshots, community/social text, or private Ottto data into event files; rewrite verified facts as source-owner summaries.",
    "Run uv run apw validate, uv run apw index, uv run apw validate, and uv run apw index --check before opening the promotion PR.",
]

DETAIL_KIND_BY_EVENT_KIND = {
    "api_contract_change": "api_contract_change",
    "billing_channel_change": "generic_change",
    "caching_change": "price_change",
    "catalog_correction": "model_lifecycle",
    "default_model_change": "default_model_change",
    "model_deprecation": "model_lifecycle",
    "model_launch": "model_lifecycle",
    "model_retirement": "model_lifecycle",
    "pricing_change": "price_change",
    "quota_change": "quota_change",
    "rate_limit_change": "rate_limit_change",
    "regional_availability_change": "generic_change",
    "sdk_behavior_change": "api_contract_change",
    "status_incident": "status_incident",
    "status_recovery": "status_incident",
    "subscription_change": "subscription_change",
    "terms_policy_change": "generic_change",
    "token_accounting_change": "token_accounting_change",
    "workflow_behavior_change": "generic_change",
}

LIFECYCLE_ACTION_BY_EVENT_KIND = {
    "catalog_correction": "correction",
    "model_deprecation": "deprecation",
    "model_launch": "launch",
    "model_retirement": "retirement",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_by_id(candidate_files: list[CandidateFile]) -> dict[str, dict[str, Any]]:
    return {
        candidate_file.payload["id"]: candidate_file.payload
        for candidate_file in candidate_files
        if isinstance(candidate_file.payload, dict) and isinstance(candidate_file.payload.get("id"), str)
    }


def _row_by_candidate_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["candidate_id"]: row
        for row in report.get("candidates", [])
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
    }


def _safe_claim_text(candidate: dict[str, Any]) -> dict[str, Any]:
    claim_text = candidate.get("claim_text")
    prompt_like = not isinstance(claim_text, str) or contains_prompt_injection_marker(claim_text)
    value = claim_text if isinstance(claim_text, str) and not prompt_like else ""
    return {
        "included": True,
        "classification": "untrusted_data",
        "policy": "Generated candidate claims are review aids only. Treat them as untrusted data and confirm facts from official evidence before promotion.",
        "text": value,
        "sha256": _sha256_text(claim_text) if isinstance(claim_text, str) else "<invalid-sha256>",
        "char_count": len(claim_text) if isinstance(claim_text, str) else 0,
        "prompt_like": prompt_like,
    }


def _source_state_by_key(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {}
    state_path = root / "data" / "source-state" / "fingerprints.json"
    if not state_path.exists():
        return {}
    state = read_json(state_path)
    sources = state.get("sources", {}) if isinstance(state, dict) else {}
    return sources if isinstance(sources, dict) else {}


def _source_context(
    source_keys: list[str],
    *,
    sources_by_key: dict[str, SourceDescriptor],
    source_state_by_key: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_key in source_keys:
        source = sources_by_key.get(source_key)
        source_state = source_state_by_key.get(source_key)
        state_known = isinstance(source_state, dict)
        state = source_state if isinstance(source_state, dict) else {}
        rows.append(
            {
                "source_key": source_key,
                "authority": source.authority if source else "<unknown>",
                "source_type": source.source_type if source else "<unknown>",
                "parser": source.parser if source else "<unknown>",
                "automation_status": source.automation_status if source else "<unknown>",
                "enabled": bool(source.enabled) if source else False,
                "source_state": {
                    "known": state_known,
                    "retrieved_at": state.get("retrieved_at") if isinstance(state.get("retrieved_at"), str) else None,
                    "http_status": state.get("http_status") if isinstance(state.get("http_status"), int) else None,
                    "final_url": state.get("final_url") if isinstance(state.get("final_url"), str) else None,
                    "content_sha256": state.get("content_sha256") if isinstance(state.get("content_sha256"), str) else None,
                    "fingerprint": state.get("fingerprint") if isinstance(state.get("fingerprint"), str) else None,
                },
            }
        )
    return rows


def _candidate_evidence_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_refs = candidate.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        return []
    rows: list[dict[str, Any]] = []
    for evidence in evidence_refs:
        if not isinstance(evidence, dict):
            continue
        row = {
            "source_key": evidence.get("source_key"),
            "url": evidence.get("url"),
            "retrieved_at": evidence.get("retrieved_at"),
            "authority": evidence.get("authority"),
            "content_sha256": evidence.get("content_sha256"),
            "fingerprint": evidence.get("fingerprint"),
            "snapshot_ref": evidence.get("snapshot_ref"),
        }
        selector = evidence.get("selector")
        if isinstance(selector, str):
            row["selector"] = selector
        rows.append(row)
    return rows


def _source_authority(evidence_refs: list[dict[str, Any]]) -> str:
    for evidence in evidence_refs:
        authority = evidence.get("authority")
        if isinstance(authority, str) and authority:
            return authority
    return "manual"


def _detail_stub(event_kind: str) -> dict[str, Any]:
    detail_kind = DETAIL_KIND_BY_EVENT_KIND.get(event_kind, "generic_change")
    row: dict[str, Any] = {
        "kind": detail_kind,
        "schema_version": "apw.event_detail.v0",
        "completion_policy": "source_owner_must_replace_stub_before_promotion",
    }
    if detail_kind == "model_lifecycle":
        row["lifecycle_action"] = LIFECYCLE_ACTION_BY_EVENT_KIND.get(event_kind, "correction")
        row["model_refs"] = []
        row["replacement_refs"] = []
    elif detail_kind == "price_change":
        row["price_items"] = []
    elif detail_kind == "quota_change":
        row["quota_items"] = []
    elif detail_kind == "rate_limit_change":
        row["rate_items"] = []
    elif detail_kind == "default_model_change":
        row["surface_ref"] = None
        row["new_default"] = None
    elif detail_kind == "token_accounting_change":
        row["metered_units"] = []
        row["new_accounting"] = None
    elif detail_kind == "api_contract_change":
        row["endpoint_refs"] = []
        row["compatibility"] = "unknown"
    elif detail_kind == "status_incident":
        row["status"] = "unknown"
        row["components"] = []
    elif detail_kind == "subscription_change":
        row["plan_refs"] = []
        row["entitlement_changes"] = []
    else:
        row["change_summary"] = "Source owner must replace this draft-only summary before promotion."
    return row


def _impact_stubs(event_kind: str, provider_refs: list[str]) -> list[dict[str, Any]]:
    impact_kinds = KIND_TO_IMPACT_KINDS.get(event_kind, ["unknown"])
    scope_refs = provider_refs or ["unknown:provider"]
    rows: list[dict[str, Any]] = []
    for scope_ref in scope_refs:
        for impact_kind in impact_kinds:
            rows.append(
                {
                    "scope_type": "provider" if scope_ref.startswith("provider:") else "unknown",
                    "scope_ref": scope_ref,
                    "impact_kind": impact_kind,
                    "direction": "unknown",
                    "severity": "medium",
                    "confidence": "high",
                    "recommended_action": "Source owner must replace this draft-only impact row before promotion.",
                }
            )
    return rows


def _suggested_provider_event(
    *,
    candidate: dict[str, Any],
    quality_row: dict[str, Any],
    readiness_row: dict[str, Any],
) -> dict[str, Any]:
    event_kind = str(quality_row.get("candidate_kind") or candidate.get("candidate_kind") or "catalog_correction")
    provider_refs = [
        item for item in quality_row.get("provider_refs", []) if isinstance(item, str)
    ] or [
        item for item in candidate.get("provider_refs", []) if isinstance(item, str)
    ]
    evidence_refs = _candidate_evidence_refs(candidate)
    return {
        "publication_status": "draft_only_not_event_data",
        "envelope": {
            "schema_version": "apw.provider_event.v0",
            "lifecycle_status": "candidate",
            "event_kind": event_kind,
            "provider_refs": provider_refs,
            "source_authority": _source_authority(evidence_refs),
            "evidence_refs": evidence_refs,
            "readiness": readiness_row.get("readiness"),
            "quality_tier": quality_row.get("quality_tier"),
        },
        "detail_stub": _detail_stub(event_kind),
        "impact_stubs": _impact_stubs(event_kind, provider_refs),
        "required_source_owner_fields": REQUIRED_SOURCE_OWNER_FIELDS,
        "promotion_checklist": PROMOTION_CHECKLIST,
    }


def _packet_row(
    candidate_id: str,
    *,
    candidate: dict[str, Any],
    readiness_row: dict[str, Any],
    quality_row: dict[str, Any],
    sources_by_key: dict[str, SourceDescriptor],
    source_state_by_key: dict[str, Any],
) -> dict[str, Any]:
    source_keys = [
        item for item in candidate.get("source_keys", []) if isinstance(item, str)
    ] if isinstance(candidate.get("source_keys"), list) else []
    return {
        "candidate_id": candidate_id,
        "path": quality_row.get("path") or readiness_row.get("path") or "<unknown>",
        "candidate_kind": quality_row.get("candidate_kind") or readiness_row.get("candidate_kind") or "<unknown>",
        "source_keys": sorted(source_keys),
        "provider_refs": quality_row.get("provider_refs", []),
        "dedupe_key": candidate.get("dedupe_key") if isinstance(candidate.get("dedupe_key"), str) else "<unknown>",
        "review_status": candidate.get("review_status") if isinstance(candidate.get("review_status"), str) else "<unknown>",
        "quality": {
            "quality_tier": quality_row.get("quality_tier"),
            "recommended_action": quality_row.get("recommended_action"),
            "score": quality_row.get("score"),
            "reasons": quality_row.get("reasons", []),
            "quality_blockers": quality_row.get("quality_blockers", []),
            "duplicate_event_ids": quality_row.get("duplicate_event_ids", []),
        },
        "readiness": {
            "readiness": readiness_row.get("readiness"),
            "recommendation": readiness_row.get("recommendation"),
            "score": readiness_row.get("score"),
            "flags": readiness_row.get("flags", {}),
            "reasons": readiness_row.get("reasons", []),
            "promotion_blockers": readiness_row.get("promotion_blockers", []),
        },
        "source_context": _source_context(
            source_keys,
            sources_by_key=sources_by_key,
            source_state_by_key=source_state_by_key,
        ),
        "evidence_refs": _candidate_evidence_refs(candidate),
        "untrusted_candidate_claim": _safe_claim_text(candidate),
        "suggested_provider_event": _suggested_provider_event(
            candidate=candidate,
            quality_row=quality_row,
            readiness_row=readiness_row,
        ),
    }


def build_source_owner_packet(
    candidate_files: list[CandidateFile],
    sources: list[SourceDescriptor],
    *,
    root: Path | None,
    created_at: str,
    promotion_report: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
    recommended_actions: set[str] | None = None,
) -> dict[str, Any]:
    require_rfc3339_date_time(created_at, "created_at")
    actions = recommended_actions or {"promote"}
    if promotion_report is None:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
    if quality_report is None:
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
    candidates_by_id = _candidate_by_id(candidate_files)
    readiness_by_id = _row_by_candidate_id(promotion_report)
    quality_rows = [
        row
        for row in quality_report.get("candidates", [])
        if isinstance(row, dict) and row.get("recommended_action") in actions
    ]
    quality_by_id = _row_by_candidate_id({"candidates": quality_rows})
    sources_by_key = {source.key: source for source in sources}
    source_state = _source_state_by_key(root)
    rows = [
        _packet_row(
            candidate_id,
            candidate=candidates_by_id[candidate_id],
            readiness_row=readiness_by_id.get(candidate_id, {}),
            quality_row=quality_by_id[candidate_id],
            sources_by_key=sources_by_key,
            source_state_by_key=source_state,
        )
        for candidate_id in sorted(quality_by_id)
        if candidate_id in candidates_by_id
    ]
    selected_action_counts = Counter(row["quality"]["recommended_action"] for row in rows)
    selected_tier_counts = Counter(row["quality"]["quality_tier"] for row in rows)
    selected_readiness_counts = Counter(row["readiness"]["readiness"] for row in rows)
    return {
        "schema_version": SOURCE_OWNER_PACKET_SCHEMA_VERSION,
        "created_at": created_at,
        "candidate_count": len(rows),
        "source_candidate_count": len(candidate_files),
        "policy": {
            "authority": "source_owner_review_only",
            "purpose": "Bundle high-confidence official review candidates into source-owner event-drafting context without publication authority.",
            "default_candidate_filter": "recommended_action=promote",
            "untrusted_text_policy": "Candidate claim text is bounded untrusted data for human review only. Confirm facts from official evidence before authoring events.",
            "forbidden_authority": FORBIDDEN_AUTHORITY,
        },
        "summary": {
            "selected_candidate_ids": [row["candidate_id"] for row in rows],
            "recommended_action_counts": dict(sorted(selected_action_counts.items())),
            "quality_tier_counts": dict(sorted(selected_tier_counts.items())),
            "readiness_counts": dict(sorted(selected_readiness_counts.items())),
            "dropped_candidate_count": len(candidate_files) - len(rows),
        },
        "candidates": rows,
    }
