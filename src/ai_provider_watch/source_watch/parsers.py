from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from defusedxml import ElementTree as DET

from ai_provider_watch.core.temporal import is_rfc3339_date_time
from ai_provider_watch.sources.registry import SourceDescriptor

MAX_ATOM_TIMESTAMP_LENGTH = 40

PROVIDER_LABELS = {
    "provider:anthropic": "Anthropic",
    "provider:aws-bedrock": "AWS Bedrock",
    "provider:azure-openai": "Azure OpenAI",
    "provider:google": "Google Gemini/Vertex",
    "provider:openai": "OpenAI",
}

KIND_LABELS = {
    "api_contract_change": "API contract change",
    "caching_change": "caching or token-accounting change",
    "model_deprecation": "model deprecation",
    "model_launch": "model availability change",
    "pricing_change": "pricing change",
    "quota_change": "quota or rate-limit change",
    "regional_availability_change": "regional availability change",
    "status_incident": "status incident or recovery",
    "token_accounting_change": "token-accounting change",
}


@dataclass(frozen=True)
class ParsedSourcePayload:
    items: list[dict[str, Any]]
    raw_excerpt_hashes: list[str]
    candidate_claims: list[dict[str, str]]
    errors: list[str]
    snapshot_ref: str | None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _provider_label(source: SourceDescriptor) -> str:
    if not source.provider_refs:
        return "Provider"
    return PROVIDER_LABELS.get(source.provider_refs[0], source.provider_refs[0].removeprefix("provider:"))


def _candidate_kind(source: SourceDescriptor) -> str:
    for hint in source.impact_hints:
        if hint in KIND_LABELS:
            return hint
    if source.source_type in {"atom_feed", "status_page"}:
        return "status_incident"
    if source.source_type == "pricing_page":
        return "pricing_change"
    if source.source_type == "docs_page":
        return "model_launch"
    return "unknown"


def _source_area(source: SourceDescriptor) -> str:
    if source.source_type == "pricing_page":
        return "pricing source"
    if source.source_type in {"atom_feed", "status_page"}:
        return "status source"
    if source.source_type == "docs_page":
        return "documentation source"
    return "official source"


def _candidate_claim(source: SourceDescriptor) -> dict[str, str]:
    candidate_kind = _candidate_kind(source)
    kind_label = KIND_LABELS.get(candidate_kind, "provider change")
    return {
        "candidate_kind": candidate_kind,
        "claim_text": (
            f"{_provider_label(source)} {_source_area(source)} changed and needs "
            f"maintainer review for a possible {kind_label}."
        ),
    }


def _atom_items(raw: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        root = DET.fromstring(raw)
    except (
        DET.ParseError,
        DET.DTDForbidden,
        DET.EntitiesForbidden,
        DET.ExternalReferenceForbidden,
    ) as exc:
        return [], [f"atom parser failed: {exc.__class__.__name__}"]

    items: list[dict[str, Any]] = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        title = _normalize_text(entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
        entry_id = _normalize_text(entry.findtext("{http://www.w3.org/2005/Atom}id") or "")
        updated = _normalize_text(entry.findtext("{http://www.w3.org/2005/Atom}updated") or "")
        item: dict[str, Any] = {"kind": "atom_entry"}
        if title:
            item["title_sha256"] = _sha256_text(title)
        if entry_id:
            item["id_sha256"] = _sha256_text(entry_id)
        if updated and len(updated) <= MAX_ATOM_TIMESTAMP_LENGTH and is_rfc3339_date_time(updated):
            item["updated"] = updated
        elif updated:
            item["updated_sha256"] = _sha256_text(updated)
        if item != {"kind": "atom_entry"}:
            items.append(item)
    return items, []


def parse_source_payload(
    source: SourceDescriptor,
    raw: bytes,
    *,
    changed: bool,
) -> ParsedSourcePayload:
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if source.parser == "atom_status":
        items, errors = _atom_items(raw)

    return ParsedSourcePayload(
        items=items,
        raw_excerpt_hashes=[],
        candidate_claims=[_candidate_claim(source)] if changed else [],
        errors=errors,
        snapshot_ref=None,
    )
