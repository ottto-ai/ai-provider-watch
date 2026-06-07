from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from defusedxml import ElementTree as DET

from ai_provider_watch.core.temporal import is_rfc3339_date_time
from ai_provider_watch.source_watch.scopes import scoped_source_content
from ai_provider_watch.sources.registry import SourceDescriptor

MAX_ATOM_TIMESTAMP_LENGTH = 40
MAX_MODEL_ID_LENGTH = 96
MAX_MODEL_ID_SEGMENT_LENGTH = 32
MAX_STATUS_REF_LENGTH = 160

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
    "model_retirement": "model retirement",
    "pricing_change": "pricing change",
    "quota_change": "quota or rate-limit change",
    "regional_availability_change": "regional availability change",
    "status_incident": "status incident or recovery",
    "token_accounting_change": "token-accounting change",
}

OPENAI_MODEL_PATTERN = re.compile(
    r"\bchat-latest\b(?![.-])"
    r"|\bchatgpt-[0-9][a-z]?(?:-[a-z0-9]+)*\b(?![.-])"
    r"|"
    r"\bcodex-mini\b(?![.-])"
    r"|\bcodex-mini-latest\b(?![.-])"
    r"|\bcomputer-use-preview\b(?![.-])"
    r"|\bsora(?:-[0-9][a-z0-9.-]*)?\b(?![.-])"
    r"|"
    r"\bdall-e-[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*\b"
    r"|\bgpt-(?:(?:35|[0-9][a-z]?(?:\.[0-9])?)(?:-(?:[0-9]{4}(?:-[0-9]{2}-[0-9]{2})?|[0-9]{2,4}|16k|32k|audio|chat|codex|cyber|deep|diarize|global|instruct|latest|max|mini|nano|preview|pro|realtime|regional|research|search|transcribe|tts|turbo|us|vision))*|audio(?:-mini)?(?:-[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*)?(?![.-])|chat-latest(?![.-])|image-[0-9][a-z0-9.-]*|oss-[0-9]+b(?![.-])|realtime(?:-mini)?(?:-(?:[0-9][a-z0-9]*(?:[.-][a-z0-9]+)*|transcribe|translate|whisper))?(?![.-]))\b(?![.-]|\s+(?:chat|codex|cyber|max|mini|nano|preview|pro)\b)"
    r"|\bo[0-9](?:-[a-z0-9]+)*\b"
    r"|\btext-embedding-(?:[0-9][a-z0-9]*(?:-[a-z0-9]+)*|ada-[0-9]+)\b"
    r"|\btts(?:-hd)?(?:-[0-9][a-z0-9.-]*)?\b(?![.-])"
    r"|\bwhisper(?:-[0-9][a-z0-9.-]*)?\b(?![.-])",
    re.IGNORECASE,
)
OPENAI_LEGACY_MODEL_PATTERN = re.compile(
    r"\b(?:ada|babbage|curie|davinci)\b(?!-)"
    r"|\b(?:ada|babbage|curie|davinci)-[0-9]{3}\b(?![.-])"
    r"|\btext-(?:ada|babbage|curie|davinci)-[0-9]{3}\b(?![.-])"
    r"|\bcode-(?:cushman|davinci)-[0-9]{3}\b(?![.-])"
    r"|\btext-(?:similarity|search)-(?:ada|babbage|curie|davinci)-(?:doc-|query-)?[0-9]{3}\b(?![.-])"
    r"|\bcode-search-(?:ada|babbage)-(?:code|text)-[0-9]{3}\b(?![.-])",
    re.IGNORECASE,
)
GEMINI_ID_PATTERN = re.compile(
    r"\bgemini-(?:(?:live-)?[0-9](?:\.[0-9])?|embedding)(?:-(?:[0-9]{2,8}|audio|embedding|embeddings|exp|flash|generation|image|images|latest|learnlm|lite|live|nano|native|preview|pro|realtime|stable|thinking|tts|ultra|vision))*\b(?![.-])",
    re.IGNORECASE,
)
GOOGLE_LEGACY_MODEL_PATTERN = re.compile(
    r"\b(?:chat-bison|code-gecko|imagetext|multimodalembedding@[0-9]{3}|text-bison|text-embedding-[0-9]{3}|text-multilingual-embedding-[0-9]{3}|textembedding-gecko(?:-multilingual)?@[0-9]{3})\b(?![.-])",
    re.IGNORECASE,
)
GPT_OSS_PATTERN = re.compile(r"\bgpt-oss-[0-9]+b\b(?![.-])", re.IGNORECASE)
GPT_DISPLAY_PATTERN = re.compile(
    r"\bGPT-[0-9][A-Za-z]?(?:\.[0-9])?(?:\s+(?:chat|codex|cyber|max|mini|nano|preview|pro)){1,3}\b"
    r"(?!\s+(?:agent|assistant|command|commands|developer|ignore|instruction|instructions|merge|prompt|publish|secret|system|user)\b)",
    re.IGNORECASE,
)
CLAUDE_DISPLAY_PATTERN = re.compile(
    r"\bClaude\s+(?:(?:Opus|Sonnet|Haiku)\s+[0-9](?:\.[0-9])?|[0-9](?:\.[0-9])?\s+(?:Opus|Sonnet|Haiku))\b",
    re.IGNORECASE,
)

MODEL_PARSER_PATTERNS = {
    "azure_openai_models": OPENAI_MODEL_PATTERN,
    "google_ai_models": GEMINI_ID_PATTERN,
}

LIFECYCLE_PARSER_PATTERNS = {
    "azure_openai_legacy_models": [OPENAI_MODEL_PATTERN, OPENAI_LEGACY_MODEL_PATTERN],
    "google_vertex_model_versions": [GEMINI_ID_PATTERN, GOOGLE_LEGACY_MODEL_PATTERN],
    "openai_deprecations": [OPENAI_MODEL_PATTERN, OPENAI_LEGACY_MODEL_PATTERN],
}

LIFECYCLE_DISPLAY_MODEL_PATTERNS = {
    "openai_deprecations": [GPT_DISPLAY_PATTERN],
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

LIFECYCLE_PARSER_CLAIMS = {
    "azure_openai_legacy_models": (
        "model_retirement",
        "Azure OpenAI legacy model documentation source changed and needs maintainer review "
        "for possible model deprecation or retirement changes.",
    ),
    "google_vertex_model_versions": (
        "model_retirement",
        "Google Vertex AI model-version documentation source changed and needs maintainer "
        "review for possible model lifecycle or retirement changes.",
    ),
    "openai_deprecations": (
        "model_retirement",
        "OpenAI deprecation documentation source changed and needs maintainer review "
        "for possible model deprecation, retirement, or API contract changes.",
    ),
}

PRICING_PARSER_NAMES = {
    "anthropic_pricing",
    "aws_bedrock_pricing",
    "azure_openai_pricing",
    "google_vertex_pricing",
    "openai_pricing",
}

PRICING_MODEL_PATTERNS = {
    "azure_openai_pricing": [OPENAI_MODEL_PATTERN],
    "google_vertex_pricing": [GEMINI_ID_PATTERN, GPT_OSS_PATTERN],
    "openai_pricing": [OPENAI_MODEL_PATTERN],
}

DISPLAY_MODEL_PATTERNS = {
    "anthropic_pricing": [
        CLAUDE_DISPLAY_PATTERN,
    ],
    "azure_openai_pricing": [
        GPT_DISPLAY_PATTERN,
    ],
    "aws_bedrock_model_cards": [
        re.compile(
            r"\b(?:Amazon\s+)?Nova\s+(?:[0-9]\s+)?(?:Premier|Pro|Lite|Micro|Canvas|Reel)\b",
            re.IGNORECASE,
        ),
        CLAUDE_DISPLAY_PATTERN,
        re.compile(r"\bLlama\s+[0-9](?:\.[0-9])?\s+(?:Maverick|Scout|[0-9]+B)\b", re.IGNORECASE),
    ],
    "aws_bedrock_pricing": [
        re.compile(
            r"\b(?:Amazon\s+)?Nova\s+(?:[0-9]\s+)?(?:Premier|Pro|Lite|Micro|Canvas|Reel)\b",
            re.IGNORECASE,
        ),
        CLAUDE_DISPLAY_PATTERN,
        re.compile(r"\bLlama\s+[0-9](?:\.[0-9])?\s+(?:Maverick|Scout|[0-9]+B)\b", re.IGNORECASE),
    ],
    "google_vertex_pricing": [
        re.compile(
            r"\bGemini\s+[0-9](?:\.[0-9])?\s+(?:Pro|Flash(?:-Lite)?|Ultra|Nano)\b",
            re.IGNORECASE,
        ),
        CLAUDE_DISPLAY_PATTERN,
    ],
    "openai_pricing": [
        GPT_DISPLAY_PATTERN,
    ],
}

PRICING_SIGNAL_KEYWORDS = {
    "batch": ("batch",),
    "cache_hit": ("cache hit", "cache read"),
    "cache_write": ("cache write", "cache creation"),
    "cached_input": ("cached input", "cached tokens"),
    "input_tokens": ("input", "input tokens"),
    "output_tokens": ("output", "output tokens"),
    "priority_processing": ("priority",),
    "provisioned_throughput": ("provisioned", "ptu"),
    "regional_pricing": ("data zone", "global", "region", "regional"),
    "token_unit": ("1m tokens", "million tokens", "mtok", "per 1m"),
}

PRICE_POINT_PATTERN = re.compile(
    r"\$\s*([0-9]{1,5}(?:\.[0-9]{1,6})?)\s*/\s*"
    r"(?:1\s*m(?:illion)?\s*tokens?|1m\s*tokens?|million\s+tokens|m\s?tok|mtok)\b",
    re.IGNORECASE,
)

PRICE_DIMENSION_KEYWORDS = {
    "cached_input": ("cached input", "cached tokens"),
    "cache_write": ("cache write", "cache creation"),
    "cache_hit": ("cache hit", "cache read"),
    "priority_processing": ("priority",),
    "input_tokens": ("input",),
    "output_tokens": ("output",),
}

LIMIT_DIMENSION_PATTERNS = {
    "requests_per_minute": (
        re.compile(r"\b(?:requests?|reqs?)\s*(?:per|/)\s*minute\b", re.IGNORECASE),
        re.compile(r"\brpm\b", re.IGNORECASE),
    ),
    "tokens_per_minute": (
        re.compile(r"\b(?:tokens?|tok)\s*(?:per|/)\s*minute\b", re.IGNORECASE),
        re.compile(r"\btpm\b", re.IGNORECASE),
    ),
    "requests_per_day": (
        re.compile(r"\b(?:requests?|reqs?)\s*(?:per|/)\s*day\b", re.IGNORECASE),
        re.compile(r"\brpd\b", re.IGNORECASE),
    ),
    "tokens_per_day": (
        re.compile(r"\b(?:tokens?|tok)\s*(?:per|/)\s*day\b", re.IGNORECASE),
        re.compile(r"\btpd\b", re.IGNORECASE),
    ),
    "tokens_per_request": (
        re.compile(r"\b(?:tokens?|tok)\s*(?:per|/)\s*request\b", re.IGNORECASE),
    ),
}

LIMIT_VALUE_PATTERN = re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,9})\b")
LIMIT_CONTEXT_TOKENS = (
    "limit",
    "quota",
    "rate",
    "request",
    "requests",
    "rpm",
    "rpd",
    "token",
    "tokens",
    "tpm",
    "tpd",
)

MONTHS = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}
ISO_DATE_PATTERN = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")
MONTH_DATE_PATTERN = re.compile(
    r"\b("
    + "|".join(MONTHS)
    + r")\s+([0-9]{1,2}),\s+([0-9]{4})\b",
    re.IGNORECASE,
)
LIFECYCLE_DATE_HEADER_TOKENS = ("deprecat", "discontinu", "retir", "shutdown", "sunset")
DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)

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


class _VisibleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._code_depth = 0
        self._table_depth = 0
        self.parts: list[str] = []
        self.structured_parts: list[str] = []
        self.status_hrefs: list[str] = []
        self.datetimes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if normalized_tag == "code":
            self._code_depth += 1
        if normalized_tag == "table":
            self._table_depth += 1
        normalized_attrs = {name.lower(): value for name, value in attrs if value is not None}
        if normalized_tag == "a":
            href = normalized_attrs.get("href")
            if href and "/incidents/" in href and len(href) <= MAX_STATUS_REF_LENGTH:
                self.status_hrefs.append(_normalize_text(href))
        if normalized_tag == "time":
            datetime_value = normalized_attrs.get("datetime")
            if datetime_value:
                self.datetimes.append(_normalize_text(datetime_value))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
        if normalized_tag == "code" and self._code_depth:
            self._code_depth -= 1
        if normalized_tag == "table" and self._table_depth:
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)
            if self._code_depth or self._table_depth:
                self.structured_parts.append(data)


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._table_depth = 0
        self._cell_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if normalized_tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
        elif normalized_tag == "tr" and self._table_depth:
            self._current_row = []
        elif normalized_tag in {"td", "th"} and self._table_depth:
            self._cell_depth += 1
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if normalized_tag in {"td", "th"} and self._cell_depth:
            if self._current_row is not None and self._current_cell is not None:
                self._current_row.append(_normalize_text(" ".join(self._current_cell)))
            self._current_cell = None
            self._cell_depth -= 1
        elif normalized_tag == "tr" and self._table_depth:
            if self._current_table is not None and self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None
        elif normalized_tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._current_table:
                self.tables.append(self._current_table)
                self._current_table = None
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._cell_depth and self._current_cell is not None:
            self._current_cell.append(data)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(DASH_TRANSLATION)).strip()


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
    if source.parser in LIFECYCLE_PARSER_CLAIMS:
        candidate_kind, claim_text = LIFECYCLE_PARSER_CLAIMS[source.parser]
        return {"candidate_kind": candidate_kind, "claim_text": claim_text}
    if source.parser in PRICING_PARSER_NAMES:
        review_scope = "pricing, token-accounting, cache, batch, or regional availability changes"
        if "quota_change" in source.impact_hints or "rate_limit_change" in source.impact_hints:
            review_scope = (
                "pricing, token-accounting, cache, batch, quota/rate-limit, "
                "or regional availability changes"
            )
        return {
            "candidate_kind": "pricing_change",
            "claim_text": (
                f"{_provider_label(source)} pricing source changed and needs maintainer review "
                f"for possible {review_scope}."
            ),
        }
    if source.parser == "aws_bedrock_model_cards":
        return {
            "candidate_kind": "model_launch",
            "claim_text": (
                "AWS Bedrock model documentation source changed and needs maintainer review "
                "for possible model availability, deprecation, or regional availability changes."
            ),
        }
    if source.parser == "statuspage_html":
        return {
            "candidate_kind": "status_incident",
            "claim_text": (
                f"{_provider_label(source)} status source changed and needs maintainer review "
                "for possible incident or recovery changes."
            ),
        }

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


def _visible_html_payload(raw: bytes) -> _VisibleHTMLParser:
    parser = _VisibleHTMLParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    return parser


def _visible_html_text(raw: bytes) -> str:
    return _normalize_text(" ".join(_visible_html_payload(raw).parts))


def _structured_html_text(raw: bytes) -> str:
    return _normalize_text(" ".join(_visible_html_payload(raw).structured_parts))


def _table_payload(raw: bytes) -> list[list[list[str]]]:
    parser = _TableHTMLParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    return parser.tables


def _model_display_id(value: str) -> str:
    model_id = re.sub(r"[^a-z0-9.@]+", "-", value.lower()).strip("-")
    if model_id.startswith("nova-"):
        return f"amazon-{model_id}"
    return model_id


def _model_ids_from_text(text: str, parser_name: str) -> list[str]:
    return _model_ids_from_patterns(
        text,
        PRICING_MODEL_PATTERNS.get(parser_name, []) + DISPLAY_MODEL_PATTERNS.get(parser_name, []),
    )


def _model_ids_from_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    model_ids: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            model_id = _model_display_id(match.group(0))
            if _is_bounded_model_id(model_id):
                model_ids.add(model_id)
    return sorted(model_ids)


def _lifecycle_model_patterns(parser_name: str) -> list[re.Pattern[str]]:
    return (
        LIFECYCLE_PARSER_PATTERNS[parser_name]
        + LIFECYCLE_DISPLAY_MODEL_PATTERNS.get(parser_name, [])
    )


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


def _model_ref_items_from_text(text: str, parser_name: str) -> list[dict[str, str]]:
    return [
        {
            "kind": "model_ref",
            "model_id": model_id,
            "source_parser": parser_name,
        }
        for model_id in _model_ids_from_text(text, parser_name)
    ]


def _model_ref_items_from_visible_text(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    return _model_ref_items_from_text(_visible_html_text(raw), parser_name)


def _pricing_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    text = _structured_html_text(raw)
    lower_text = text.lower()
    model_items = _model_ref_items_from_text(text, parser_name)
    price_items = _price_point_items(raw, parser_name)
    signal_items = [
        {
            "kind": "pricing_signal",
            "signal": signal,
            "source_parser": parser_name,
        }
        for signal, keywords in sorted(PRICING_SIGNAL_KEYWORDS.items())
        if any(keyword in lower_text for keyword in keywords)
    ]
    limit_items = _limit_signal_items(raw, parser_name)
    return model_items + price_items + signal_items + limit_items


def _price_dimension(text: str) -> str | None:
    lower_text = text.lower()
    for dimension, keywords in PRICE_DIMENSION_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            return dimension
    return None


def _price_point_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    items: dict[tuple[str, str, str], dict[str, str]] = {}
    for table in _table_payload(raw):
        headers: list[str] = []
        for row in table:
            if not row:
                continue
            if not headers:
                headers = row
                continue
            row_text = _normalize_text(" ".join(row))
            model_ids = _model_ids_from_text(row_text, parser_name)
            if not model_ids:
                continue
            for index, cell in enumerate(row):
                header = headers[index] if index < len(headers) else ""
                dimension = _price_dimension(f"{header} {cell}")
                if dimension is None:
                    continue
                for match in PRICE_POINT_PATTERN.finditer(cell):
                    amount = match.group(1)
                    for model_id in model_ids:
                        key = (model_id, dimension, amount)
                        items[key] = {
                            "kind": "price_point",
                            "model_id": model_id,
                            "billing_dimension": dimension,
                            "price_usd_per_1m_tokens": amount,
                            "unit": "1m_tokens",
                            "source_parser": parser_name,
                        }
    return [items[key] for key in sorted(items)]


def _limit_dimension(text: str) -> str | None:
    for dimension, patterns in LIMIT_DIMENSION_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            return dimension
    return None


def _limit_value(text: str) -> str | None:
    for match in LIMIT_VALUE_PATTERN.finditer(text):
        value = match.group(1).replace(",", "")
        if value != "0":
            return value
    return None


def _limit_value_from_row(headers: list[str], row: list[str], dimension: str, row_text: str) -> str | None:
    preferred_header_tokens = ("limit", "quota", "rate", "value", "rpm", "rpd", "tpm", "tpd")
    for index, cell in enumerate(row):
        header = headers[index] if index < len(headers) else ""
        header_cell = f"{header} {cell}".lower()
        if not any(token in header_cell for token in preferred_header_tokens):
            continue
        if _limit_dimension(cell) == dimension:
            continue
        value = _limit_value(cell)
        if value is not None:
            return value
    return _limit_value(row_text)


def _limit_signal_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    items: dict[tuple[str, str, str], dict[str, str]] = {}
    for table in _table_payload(raw):
        headers: list[str] = []
        for row in table:
            if not row:
                continue
            if not headers:
                headers = row
                continue
            row_text = _normalize_text(" ".join(row))
            lower_row = row_text.lower()
            if not any(token in lower_row for token in LIMIT_CONTEXT_TOKENS):
                continue
            dimension = _limit_dimension(row_text)
            if dimension is None:
                continue
            value = _limit_value_from_row(headers, row, dimension, row_text)
            if value is None:
                continue
            model_ids = _model_ids_from_text(row_text, parser_name) or [""]
            for model_id in model_ids:
                key = (dimension, value, model_id)
                item = {
                    "kind": "limit_signal",
                    "limit_dimension": dimension,
                    "limit_value": value,
                    "unit": dimension,
                    "source_parser": parser_name,
                }
                if model_id:
                    item["model_id"] = model_id
                items[key] = item
    return [items[key] for key in sorted(items)]


def _lifecycle_dates_from_text(text: str) -> list[str]:
    dates = set(ISO_DATE_PATTERN.findall(text))
    for match in MONTH_DATE_PATTERN.finditer(text):
        month = MONTHS[match.group(1).lower()]
        day = int(match.group(2))
        year = match.group(3)
        dates.add(f"{year}-{month}-{day:02d}")
    return sorted(dates)


def _has_lifecycle_date_header(cell: str) -> bool:
    lower_cell = cell.lower()
    return "date" in lower_cell and any(
        token in lower_cell for token in LIFECYCLE_DATE_HEADER_TOKENS
    )


def _lifecycle_table_text_and_dates(raw: bytes, parser_name: str) -> tuple[str, list[str]]:
    selected_cells: list[str] = []
    dates: set[str] = set()
    model_patterns = _lifecycle_model_patterns(parser_name)
    for table in _table_payload(raw):
        headers: list[str] = []
        for row in table:
            if any(_has_lifecycle_date_header(cell) for cell in row):
                headers = row
                selected_cells.extend(row)
                continue
            if not headers:
                continue
            row_text = _normalize_text(" ".join(row))
            if not _model_ids_from_patterns(row_text, model_patterns):
                continue
            selected_cells.extend(row)
            for index, cell in enumerate(row):
                header = headers[index] if index < len(headers) else ""
                if _has_lifecycle_date_header(header):
                    dates.update(_lifecycle_dates_from_text(cell))
    return _normalize_text(" ".join(selected_cells)), sorted(dates)


def _lifecycle_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    text, dates = _lifecycle_table_text_and_dates(raw, parser_name)
    if not text:
        text = _structured_html_text(raw)
    model_items = [
        {
            "kind": "model_ref",
            "model_id": model_id,
            "source_parser": parser_name,
        }
        for model_id in _model_ids_from_patterns(text, _lifecycle_model_patterns(parser_name))
    ]
    date_items = [
        {
            "kind": "lifecycle_date",
            "date": date_value,
            "source_parser": parser_name,
        }
        for date_value in dates
    ]
    return model_items + date_items


def _statuspage_items(raw: bytes) -> list[dict[str, str]]:
    parsed = _visible_html_payload(raw)
    href_items = [
        {
            "kind": "status_incident_ref",
            "href_sha256": _sha256_text(href),
            "source_parser": "statuspage_html",
        }
        for href in sorted(set(parsed.status_hrefs))
    ]
    datetime_items = [
        {
            "kind": "status_timestamp",
            "timestamp": value,
            "source_parser": "statuspage_html",
        }
        for value in sorted(set(parsed.datetimes))
        if len(value) <= MAX_ATOM_TIMESTAMP_LENGTH and is_rfc3339_date_time(value)
    ]
    return href_items + datetime_items


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
    scoped = scoped_source_content(source, raw)
    raw = scoped.raw
    errors.extend(scoped.errors)
    if source.parser == "atom_status":
        items, atom_errors = _atom_items(raw)
        errors.extend(atom_errors)
    elif source.parser in MODEL_PARSER_PATTERNS:
        items = _model_ref_items(raw, source.parser)
    elif source.parser in LIFECYCLE_PARSER_PATTERNS:
        items = _lifecycle_items(raw, source.parser)
    elif source.parser in PRICING_PARSER_NAMES:
        items = _pricing_items(raw, source.parser)
    elif source.parser == "aws_bedrock_model_cards":
        items = _model_ref_items_from_visible_text(raw, source.parser)
    elif source.parser == "statuspage_html":
        items = _statuspage_items(raw)

    return ParsedSourcePayload(
        items=items,
        raw_excerpt_hashes=[],
        candidate_claims=[_candidate_claim(source)] if changed else [],
        errors=errors,
        snapshot_ref=None,
    )
