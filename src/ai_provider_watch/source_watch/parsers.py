from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from defusedxml import ElementTree as DET

from ai_provider_watch.core.temporal import is_rfc3339_date_time
from ai_provider_watch.sources.registry import SourceDescriptor

MAX_ATOM_TIMESTAMP_LENGTH = 40
MAX_MODEL_ID_LENGTH = 96
MAX_MODEL_ID_SEGMENT_LENGTH = 32

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

MODEL_PARSER_PATTERNS = {
    "azure_openai_models": re.compile(
        r"\bcodex-mini\b"
        r"|\bcomputer-use-preview\b"
        r"|\bsora(?:-[0-9][a-z0-9.-]*)?\b"
        r"|"
        r"\bdall-e-[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*\b"
        r"|\bgpt-(?:[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*|audio(?:-mini)?|chat-latest|image-[0-9][a-z0-9.-]*|oss-[0-9]+b|realtime(?:-mini)?)\b"
        r"|\bo[0-9](?:-[a-z0-9]+)*\b"
        r"|\btext-embedding-(?:[0-9][a-z0-9]*(?:-[a-z0-9]+)*|ada-[0-9]+)\b"
        r"|\btts(?:-hd)?(?:-[0-9][a-z0-9.-]*)?\b"
        r"|\bwhisper(?:-[0-9][a-z0-9.-]*)?\b",
        re.IGNORECASE,
    ),
    "google_ai_models": re.compile(
        r"\bgemini-[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*\b",
        re.IGNORECASE,
    ),
}

MODEL_PARSER_CLAIMS = {
    "azure_openai_models": (
        "model_launch",
        "Azure OpenAI model documentation source changed and needs maintainer review "
        "for possible model availability or deprecation changes.",
    ),
    "google_ai_models": (
        "model_launch",
        "Google Gemini/Vertex model documentation source changed and needs maintainer review "
        "for possible model availability or deprecation changes.",
    ),
}

DISALLOWED_MODEL_ID_SEGMENTS = {
    "agent",
    "assistant",
    "candidate",
    "command",
    "commands",
    "developer",
    "ignore",
    "instruction",
    "instructions",
    "merge",
    "prompt",
    "publish",
    "secret",
    "system",
    "user",
}


@dataclass(frozen=True)
class ParsedSourcePayload:
    items: list[dict[str, Any]]
    raw_excerpt_hashes: list[str]
    candidate_claims: list[dict[str, str]]
    errors: list[str]
    snapshot_ref: str | None


class _ModelTokenParser(HTMLParser):
    def __init__(self, *, include_model_hrefs: bool) -> None:
        super().__init__(convert_charrefs=True)
        self._code_depth = 0
        self._include_model_hrefs = include_model_hrefs
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "code":
            self._code_depth += 1
        if normalized_tag == "a" and self._include_model_hrefs:
            for name, value in attrs:
                if name.lower() == "href" and value and "/models/" in value:
                    self.parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "code" and self._code_depth:
            self._code_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._code_depth:
            self.parts.append(data)


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
    if source.parser in MODEL_PARSER_CLAIMS:
        candidate_kind, claim_text = MODEL_PARSER_CLAIMS[source.parser]
        return {"candidate_kind": candidate_kind, "claim_text": claim_text}

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


def _model_candidate_text(raw: bytes, *, include_model_hrefs: bool) -> str:
    parser = _ModelTokenParser(include_model_hrefs=include_model_hrefs)
    parser.feed(raw.decode("utf-8", errors="ignore"))
    return _normalize_text(" ".join(parser.parts))


def _model_ref_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    pattern = MODEL_PARSER_PATTERNS[parser_name]
    text = _model_candidate_text(raw, include_model_hrefs=parser_name == "google_ai_models")
    model_ids = sorted(
        {
            model_id
            for match in pattern.finditer(text)
            if _is_bounded_model_id(model_id := match.group(0).lower())
        }
    )
    return [
        {
            "kind": "model_ref",
            "model_id": model_id,
            "source_parser": parser_name,
        }
        for model_id in model_ids
    ]


def _is_bounded_model_id(model_id: str) -> bool:
    if len(model_id) > MAX_MODEL_ID_LENGTH:
        return False
    segments = [segment for segment in re.split(r"[.:-]+", model_id) if segment]
    if not segments:
        return False
    if any(len(segment) > MAX_MODEL_ID_SEGMENT_LENGTH for segment in segments):
        return False
    return not any(segment in DISALLOWED_MODEL_ID_SEGMENTS for segment in segments)


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
    elif source.parser in MODEL_PARSER_PATTERNS:
        items = _model_ref_items(raw, source.parser)

    return ParsedSourcePayload(
        items=items,
        raw_excerpt_hashes=[],
        candidate_claims=[_candidate_claim(source)] if changed else [],
        errors=errors,
        snapshot_ref=None,
    )
