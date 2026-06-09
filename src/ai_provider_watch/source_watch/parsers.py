from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from defusedxml import ElementTree as DET

from ai_provider_watch.core.temporal import is_rfc3339_date_time
from ai_provider_watch.source_watch.scopes import scoped_source_content
from ai_provider_watch.sources.registry import SourceDescriptor, is_url_allowed_for_source

MAX_ATOM_TIMESTAMP_LENGTH = 40
MAX_ANNOUNCEMENT_CLAIMS = 6
MAX_LIFECYCLE_CLAIMS = 8
MAX_MODEL_ID_LENGTH = 96
MAX_MODEL_ID_SEGMENT_LENGTH = 32
MAX_OPERATIONAL_DELTA_CLAIMS = 8
MAX_PRICING_DELTA_CLAIMS = 8
MAX_STATUS_REF_LENGTH = 160
OPERATIONAL_ROW_STATE_SCHEMA_VERSION = "apw.operational_rows.v0"
PRICING_ROW_STATE_SCHEMA_VERSION = "apw.pricing_rows.v0"

PROVIDER_LABELS = {
    "provider:anthropic": "Anthropic",
    "provider:aws-bedrock": "AWS Bedrock",
    "provider:azure-openai": "Azure OpenAI",
    "provider:google": "Google Gemini/Vertex",
    "provider:openai": "OpenAI",
}

KIND_LABELS = {
    "api_contract_change": "API contract change",
    "billing_channel_change": "billing channel change",
    "caching_change": "caching or token-accounting change",
    "default_model_change": "default-model change",
    "model_deprecation": "model deprecation",
    "model_launch": "model availability change",
    "model_retirement": "model retirement",
    "pricing_change": "pricing change",
    "quota_change": "quota or rate-limit change",
    "rate_limit_change": "rate-limit change",
    "regional_availability_change": "regional availability change",
    "sdk_behavior_change": "SDK behavior change",
    "status_incident": "status incident or recovery",
    "status_recovery": "status incident or recovery",
    "subscription_change": "subscription change",
    "token_accounting_change": "token-accounting change",
    "workflow_behavior_change": "workflow behavior change",
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
        "for possible model availability, deprecation, default-model, or workflow behavior changes.",
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

DATED_ANNOUNCEMENT_PARSER_NAMES = {
    "anthropic_news_index",
    "aws_bedrock_whats_new_feed",
    "azure_openai_whats_new",
    "google_gemini_changelog",
    "openai_news_feed",
}

ANNOUNCEMENT_MODEL_PATTERNS = [
    OPENAI_MODEL_PATTERN,
    OPENAI_LEGACY_MODEL_PATTERN,
    GEMINI_ID_PATTERN,
    GOOGLE_LEGACY_MODEL_PATTERN,
    GPT_OSS_PATTERN,
    GPT_DISPLAY_PATTERN,
    CLAUDE_DISPLAY_PATTERN,
    re.compile(
        r"\b(?:Amazon\s+)?Nova\s+(?:[0-9]\s+)?(?:Premier|Pro|Lite|Micro|Canvas|Reel)\b",
        re.IGNORECASE,
    ),
]

ANNOUNCEMENT_SUBJECT_KEYWORDS = {
    "api": "api",
    "agentcore": "bedrock-agentcore",
    "amazon bedrock": "amazon-bedrock",
    "audio": "audio",
    "aws bedrock": "aws-bedrock",
    "azure openai": "azure-openai",
    "batch": "batch-api",
    "bedrock": "aws-bedrock",
    "cache": "prompt-caching",
    "caching": "prompt-caching",
    "claude code": "claude-code",
    "codex": "codex",
    "computer use": "computer-use",
    "gemini api": "gemini-api",
    "mcp": "mcp",
    "model router": "model-router",
    "prompt caching": "prompt-caching",
    "realtime": "realtime-api",
    "responses api": "responses-api",
    "sdk": "sdk",
    "token": "tokens",
    "vertex ai": "vertex-ai",
}

ANNOUNCEMENT_RELEVANCE_KEYWORDS = tuple(sorted(ANNOUNCEMENT_SUBJECT_KEYWORDS))

ANNOUNCEMENT_KIND_KEYWORDS = (
    ("pricing_change", ("billing", "cost", "price", "pricing")),
    ("token_accounting_change", ("cache", "caching", "cached", "token accounting", "tokens")),
    ("quota_change", ("quota",)),
    ("rate_limit_change", ("rate limit", "rate-limit", "rpm", "tpm")),
    ("model_retirement", ("retire", "retired", "retirement", "shut down", "shutdown", "sunset")),
    ("model_deprecation", ("deprecat", "legacy model")),
    ("default_model_change", ("default model", "model router", "routing")),
    (
        "model_launch",
        (
            "available",
            "general availability",
            "generally available",
            "introducing",
            "launch",
            "launched",
            "model availability",
            "released",
            "preview",
        ),
    ),
    ("regional_availability_change", ("region", "regional", "data zone")),
    ("api_contract_change", ("endpoint", "header", "request parameter", "responses api")),
    ("sdk_behavior_change", ("sdk", "library")),
    ("workflow_behavior_change", ("agentcore", "claude code", "codex", "coding agent", "managed agents", "mcp", "workflow")),
)

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

DEFAULT_SCOPE_KEYWORDS = {
    "realtime": ("realtime", "real time", "streaming"),
    "audio": ("audio", "speech", "voice"),
    "coding": ("code", "coding", "codex"),
    "embeddings": ("embedding", "embeddings"),
    "image_generation": ("image", "vision"),
    "text_generation": ("chat", "conversation", "generation", "generative", "text"),
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

TOKEN_ACCOUNTING_SIGNALS = {
    "batch",
    "cache_hit",
    "cache_write",
    "cached_input",
    "input_tokens",
    "output_tokens",
    "token_unit",
}

PRICE_DIMENSION_LABELS = {
    "cached_input": "cached input",
    "cache_hit": "cache hit",
    "cache_write": "cache write",
    "input_tokens": "input tokens",
    "output_tokens": "output tokens",
    "priority_processing": "priority processing",
}

PRICING_SIGNAL_LABELS = {
    "batch": "batch",
    "cache_hit": "cache hit",
    "cache_write": "cache write",
    "cached_input": "cached input",
    "input_tokens": "input tokens",
    "output_tokens": "output tokens",
    "priority_processing": "priority processing",
    "provisioned_throughput": "provisioned throughput",
    "regional_pricing": "regional pricing",
    "token_unit": "token unit",
}

PRICE_POINT_PATTERN = re.compile(
    r"\$\s*([0-9]{1,5}(?:\.[0-9]{1,6})?)\s*/\s*"
    r"(?:1\s*m(?:illion)?\s*tokens?|1m\s*tokens?|million\s+tokens|m\s?tok|mtok)\b",
    re.IGNORECASE,
)
PRICE_AMOUNT_PATTERN = re.compile(r"^[0-9]{1,5}(?:\.[0-9]{1,6})?$")

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

LIMIT_DIMENSION_LABELS = {
    "requests_per_day": "requests per day",
    "requests_per_minute": "requests per minute",
    "tokens_per_day": "tokens per day",
    "tokens_per_minute": "tokens per minute",
    "tokens_per_request": "tokens per request",
}

DEFAULT_SCOPE_LABELS = {
    "audio": "audio",
    "coding": "coding",
    "embeddings": "embeddings",
    "global": "global",
    "image_generation": "image generation",
    "realtime": "realtime",
    "text_generation": "text generation",
}

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
MONTH_YEAR_PATTERN = re.compile(
    r"\b("
    + "|".join(MONTHS)
    + r")\s+([0-9]{4})\b",
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


class _AnchorTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._anchor_depth = 0
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth or normalized_tag != "a":
            return
        attrs_by_name = {name.lower(): value for name, value in attrs if value is not None}
        href = attrs_by_name.get("href")
        if href:
            self._anchor_depth += 1
            self._current_href = href
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if normalized_tag == "a" and self._anchor_depth:
            text = _normalize_text(" ".join(self._current_text))
            if self._current_href and text:
                self.links.append((self._current_href, text))
            self._anchor_depth -= 1
            self._current_href = None
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and self._anchor_depth:
            self._current_text.append(data)


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


def _anchor_links(raw: bytes, source: SourceDescriptor) -> list[tuple[str, str]]:
    parser = _AnchorTextParser()
    parser.feed(raw.decode("utf-8", errors="ignore"))
    links: list[tuple[str, str]] = []
    for href, text in parser.links:
        url = urljoin(source.url, href)
        if is_url_allowed_for_source(url, source):
            links.append((url, text))
    return links


def _date_from_datetime_text(value: str) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if ISO_DATE_PATTERN.fullmatch(normalized):
        return normalized
    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return parsed.date().isoformat()


def _date_from_text(value: str, *, allow_month_year: bool) -> str | None:
    normalized = _normalize_text(value)
    iso_match = ISO_DATE_PATTERN.search(normalized)
    if iso_match:
        return iso_match.group(0)
    month_match = MONTH_DATE_PATTERN.search(normalized)
    if month_match:
        month = MONTHS[month_match.group(1).lower()]
        day = int(month_match.group(2))
        return f"{month_match.group(3)}-{month}-{day:02d}"
    if allow_month_year:
        month_year = MONTH_YEAR_PATTERN.search(normalized)
        if month_year:
            return f"{month_year.group(2)}-{MONTHS[month_year.group(1).lower()]}"
    return None


def _announcement_subjects(text: str) -> list[str]:
    lower_text = text.lower()
    subjects = {
        model_id
        for pattern in ANNOUNCEMENT_MODEL_PATTERNS
        for match in pattern.finditer(text)
        if _is_bounded_model_id(model_id := _model_display_id(match.group(0)))
    }
    for keyword, subject in ANNOUNCEMENT_SUBJECT_KEYWORDS.items():
        if keyword in lower_text:
            subjects.add(subject)
    return sorted(subjects)[:8]


def _announcement_kind(text: str, source: SourceDescriptor) -> str | None:
    lower_text = text.lower()
    for candidate_kind, keywords in ANNOUNCEMENT_KIND_KEYWORDS:
        if any(keyword in lower_text for keyword in keywords):
            return candidate_kind
    for hint in source.impact_hints:
        if hint in KIND_LABELS:
            return hint
    return None


def _announcement_relevant(text: str, subjects: list[str]) -> bool:
    lower_text = text.lower()
    return bool(subjects) or any(keyword in lower_text for keyword in ANNOUNCEMENT_RELEVANCE_KEYWORDS)


def _announcement_claim_text(
    source: SourceDescriptor,
    *,
    date_value: str,
    candidate_kind: str,
    subjects: list[str],
) -> str:
    kind_label = KIND_LABELS.get(candidate_kind, "provider change")
    article = "an" if kind_label[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    subject_text = ", ".join(subjects[:6]) if subjects else "provider API or model surface"
    return (
        f"{_provider_label(source)} official dated source reports {article} {kind_label} "
        f"on {date_value} for {subject_text}."
    )


def _announcement_item(
    source: SourceDescriptor,
    *,
    text: str,
    date_value: str,
    candidate_kind: str,
    evidence_url: str | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": "dated_announcement_ref",
        "published_date": date_value,
        "title_sha256": _sha256_text(text),
        "source_parser": source.parser,
        "candidate_kind": candidate_kind,
    }
    subjects = _announcement_subjects(text)
    if subjects:
        item["subjects"] = subjects
    if evidence_url:
        item["link_sha256"] = _sha256_text(evidence_url)
    return item


def _announcement_claim(
    source: SourceDescriptor,
    *,
    text: str,
    date_value: str,
    candidate_kind: str,
    evidence_url: str | None,
) -> dict[str, str]:
    subjects = _announcement_subjects(text)
    claim: dict[str, str] = {
        "candidate_kind": candidate_kind,
        "claim_text": _announcement_claim_text(
            source,
            date_value=date_value,
            candidate_kind=candidate_kind,
            subjects=subjects,
        ),
        "selector": f"announcement:{_sha256_text(text)[:16]}",
        "snapshot_ref": f"entry:{_sha256_text(text)[:16]}",
    }
    if evidence_url:
        claim["evidence_url"] = evidence_url
    return claim


def _dedupe_announcement_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        subjects = ",".join(_announcement_subjects(str(record.get("text") or "")))
        key = (
            str(record.get("date_value") or ""),
            str(record.get("candidate_kind") or ""),
            subjects or _sha256_text(str(record.get("text") or "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _rss_or_atom_announcement_records(
    source: SourceDescriptor,
    raw: bytes,
    *,
    required_keywords: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        root = DET.fromstring(raw)
    except (
        DET.ParseError,
        DET.DTDForbidden,
        DET.EntitiesForbidden,
        DET.ExternalReferenceForbidden,
    ) as exc:
        return [], [f"announcement feed parser failed: {exc.__class__.__name__}"]

    records: list[dict[str, Any]] = []
    entries = list(root.findall(".//item")) + list(root.findall("{http://www.w3.org/2005/Atom}entry"))
    for entry in entries:
        title = _normalize_text(entry.findtext("title") or entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
        description = _normalize_text(entry.findtext("description") or entry.findtext("summary") or "")
        link = _normalize_text(entry.findtext("link") or "")
        if not link:
            link_node = entry.find("{http://www.w3.org/2005/Atom}link")
            if link_node is not None:
                link = _normalize_text(link_node.attrib.get("href", ""))
        evidence_url = urljoin(source.url, link) if link else None
        if evidence_url and not is_url_allowed_for_source(evidence_url, source):
            evidence_url = None
        published = (
            entry.findtext("pubDate")
            or entry.findtext("published")
            or entry.findtext("updated")
            or entry.findtext("{http://www.w3.org/2005/Atom}published")
            or entry.findtext("{http://www.w3.org/2005/Atom}updated")
            or ""
        )
        date_value = _date_from_datetime_text(published) or _date_from_text(title, allow_month_year=False)
        text = _normalize_text(f"{title} {description}")
        lower_text = text.lower()
        if required_keywords and not any(keyword in lower_text for keyword in required_keywords):
            continue
        subjects = _announcement_subjects(text)
        if not date_value or not _announcement_relevant(text, subjects):
            continue
        candidate_kind = _announcement_kind(text, source)
        if candidate_kind is None:
            continue
        records.append(
            {
                "text": text,
                "date_value": date_value,
                "candidate_kind": candidate_kind,
                "evidence_url": evidence_url,
            }
        )
    return _dedupe_announcement_records(records)[:MAX_ANNOUNCEMENT_CLAIMS], []


def _anthropic_news_records(source: SourceDescriptor, raw: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for evidence_url, text in _anchor_links(raw, source):
        date_value = _date_from_text(text, allow_month_year=False)
        subjects = _announcement_subjects(text)
        if not date_value or not _announcement_relevant(text, subjects):
            continue
        candidate_kind = _announcement_kind(text, source)
        if candidate_kind is None:
            continue
        records.append(
            {
                "text": text,
                "date_value": date_value,
                "candidate_kind": candidate_kind,
                "evidence_url": evidence_url,
            }
        )
    return _dedupe_announcement_records(records)[:MAX_ANNOUNCEMENT_CLAIMS]


def _dated_text_records(
    source: SourceDescriptor,
    raw: bytes,
    *,
    allow_month_year: bool,
) -> list[dict[str, Any]]:
    text = _visible_html_text(raw)
    matches = list(MONTH_DATE_PATTERN.finditer(text))
    if allow_month_year:
        matches += [match for match in MONTH_YEAR_PATTERN.finditer(text) if match not in matches]
    matches = sorted(matches, key=lambda item: item.start())
    records: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 900)
        segment = _normalize_text(text[match.start() : end])
        date_value = _date_from_text(segment, allow_month_year=allow_month_year)
        subjects = _announcement_subjects(segment)
        if not date_value or not _announcement_relevant(segment, subjects):
            continue
        candidate_kind = _announcement_kind(segment, source)
        if candidate_kind is None:
            continue
        records.append(
            {
                "text": segment,
                "date_value": date_value,
                "candidate_kind": candidate_kind,
                "evidence_url": source.url,
            }
        )
    return _dedupe_announcement_records(records)[:MAX_ANNOUNCEMENT_CLAIMS]


def _dated_announcement_payload(
    source: SourceDescriptor,
    raw: bytes,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if source.parser == "openai_news_feed":
        records, errors = _rss_or_atom_announcement_records(source, raw)
    elif source.parser == "aws_bedrock_whats_new_feed":
        records, errors = _rss_or_atom_announcement_records(
            source,
            raw,
            required_keywords=("bedrock",),
        )
    elif source.parser == "anthropic_news_index":
        records = _anthropic_news_records(source, raw)
    elif source.parser == "google_gemini_changelog":
        records = _dated_text_records(source, raw, allow_month_year=False)
    elif source.parser == "azure_openai_whats_new":
        records = _dated_text_records(source, raw, allow_month_year=True)
    else:
        records = []

    items = [
        _announcement_item(
            source,
            text=record["text"],
            date_value=record["date_value"],
            candidate_kind=record["candidate_kind"],
            evidence_url=record.get("evidence_url"),
        )
        for record in records
    ]
    claims = [
        _announcement_claim(
            source,
            text=record["text"],
            date_value=record["date_value"],
            candidate_kind=record["candidate_kind"],
            evidence_url=record.get("evidence_url"),
        )
        for record in records
    ]
    return items, claims, errors


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


def _model_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    return _model_ref_items(raw, parser_name) + _default_model_items(raw, parser_name)


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


def _default_scope(text: str) -> str:
    lower_text = text.lower()
    for scope, keywords in DEFAULT_SCOPE_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            return scope
    return "global"


def _default_model_items(raw: bytes, parser_name: str) -> list[dict[str, str]]:
    items: dict[tuple[str, str], dict[str, str]] = {}
    model_patterns = (
        [MODEL_PARSER_PATTERNS[parser_name]]
        if parser_name in MODEL_PARSER_PATTERNS
        else PRICING_MODEL_PATTERNS.get(parser_name, []) + DISPLAY_MODEL_PATTERNS.get(parser_name, [])
    )
    for table in _table_payload(raw):
        headers: list[str] = []
        for row in table:
            if not row:
                continue
            if not headers:
                headers = row
                continue
            row_text = _normalize_text(" ".join(row))
            header_text = _normalize_text(" ".join(headers))
            if "default" not in f"{header_text} {row_text}".lower():
                continue
            model_ids = _model_ids_from_patterns(row_text, model_patterns)
            if not model_ids:
                continue
            scope = _default_scope(row_text)
            for model_id in model_ids:
                items[(scope, model_id)] = {
                    "kind": "default_model_signal",
                    "default_scope": scope,
                    "model_id": model_id,
                    "source_parser": parser_name,
                }
    return [items[key] for key in sorted(items)]


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


def _price_row_key(model_id: str, billing_dimension: str, unit: str) -> str:
    return f"price:{model_id}:{billing_dimension}:{unit}"


def _price_point_state_row(item: dict[str, Any]) -> dict[str, str] | None:
    if item.get("kind") != "price_point":
        return None
    model_id = item.get("model_id")
    billing_dimension = item.get("billing_dimension")
    amount = item.get("price_usd_per_1m_tokens")
    unit = item.get("unit")
    if (
        not isinstance(model_id, str)
        or not _is_bounded_model_id(model_id)
        or not isinstance(billing_dimension, str)
        or billing_dimension not in PRICE_DIMENSION_KEYWORDS
        or not isinstance(amount, str)
        or not PRICE_AMOUNT_PATTERN.fullmatch(amount)
        or unit != "1m_tokens"
    ):
        return None
    row_key = _price_row_key(model_id, billing_dimension, unit)
    row_sha256 = _sha256_text(f"{row_key}:{amount}")
    return {
        "row_key": row_key,
        "row_sha256": row_sha256,
        "model_id": model_id,
        "billing_dimension": billing_dimension,
        "price_usd_per_1m_tokens": amount,
        "unit": unit,
    }


def _pricing_signal_state_row(item: dict[str, Any]) -> dict[str, str] | None:
    if item.get("kind") != "pricing_signal":
        return None
    signal = item.get("signal")
    if not isinstance(signal, str) or signal not in PRICING_SIGNAL_KEYWORDS:
        return None
    row_key = f"signal:{signal}"
    return {
        "row_key": row_key,
        "row_sha256": _sha256_text(row_key),
        "signal": signal,
    }


def pricing_state_from_items(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    price_groups: dict[str, list[dict[str, str]]] = {}
    signal_rows: dict[str, dict[str, str]] = {}
    for item in items:
        price_row = _price_point_state_row(item)
        if price_row is not None:
            price_groups.setdefault(price_row["row_key"], []).append(price_row)
            continue
        signal_row = _pricing_signal_state_row(item)
        if signal_row is not None:
            signal_rows[signal_row["row_key"]] = signal_row

    price_rows: list[dict[str, str]] = []
    ambiguous_price_point_keys: list[str] = []
    for row_key, rows in sorted(price_groups.items()):
        amounts = {row["price_usd_per_1m_tokens"] for row in rows}
        if len(amounts) > 1:
            ambiguous_price_point_keys.append(row_key)
            continue
        price_rows.append(sorted(rows, key=lambda row: row["row_sha256"])[0])

    if not price_rows and not signal_rows and not ambiguous_price_point_keys:
        return None
    return {
        "schema_version": PRICING_ROW_STATE_SCHEMA_VERSION,
        "price_points": price_rows,
        "pricing_signals": [signal_rows[key] for key in sorted(signal_rows)],
        "ambiguous_price_point_keys": ambiguous_price_point_keys,
    }


def _pricing_state_from_source_state(previous_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(previous_state, dict):
        return None
    pricing_state = previous_state.get("pricing_rows")
    if not isinstance(pricing_state, dict):
        return None
    if pricing_state.get("schema_version") != PRICING_ROW_STATE_SCHEMA_VERSION:
        return None
    return pricing_state


def _state_rows_by_key(
    pricing_state: dict[str, Any] | None,
    field: str,
) -> dict[str, dict[str, str]]:
    if not isinstance(pricing_state, dict):
        return {}
    rows = pricing_state.get(field)
    if not isinstance(rows, list):
        return {}
    keyed: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_key = row.get("row_key")
        if isinstance(row_key, str):
            keyed[row_key] = {key: value for key, value in row.items() if isinstance(value, str)}
    return keyed


def _ambiguous_price_keys(pricing_state: dict[str, Any] | None) -> set[str]:
    if not isinstance(pricing_state, dict):
        return set()
    keys = pricing_state.get("ambiguous_price_point_keys")
    if not isinstance(keys, list):
        return set()
    return {key for key in keys if isinstance(key, str)}


def _short_row_hash(row: dict[str, str]) -> str:
    row_sha256 = row.get("row_sha256", "")
    if re.fullmatch(r"[a-f0-9]{64}", row_sha256):
        return row_sha256[:16]
    serialized = "|".join(f"{key}={row[key]}" for key in sorted(row))
    return _sha256_text(serialized)[:16]


def _price_delta_claim(
    source: SourceDescriptor,
    action: str,
    row: dict[str, str],
    *,
    previous_row: dict[str, str] | None = None,
) -> dict[str, str]:
    provider = _provider_label(source)
    model_id = row["model_id"]
    dimension = PRICE_DIMENSION_LABELS.get(row["billing_dimension"], row["billing_dimension"])
    amount = row["price_usd_per_1m_tokens"]
    if action == "changed" and previous_row is not None:
        previous_amount = previous_row["price_usd_per_1m_tokens"]
        claim_text = (
            f"{provider} official pricing table changed {model_id} {dimension} price "
            f"from ${previous_amount} / 1M tokens to ${amount} / 1M tokens."
        )
    elif action == "removed":
        claim_text = (
            f"{provider} official pricing table removed {model_id} {dimension} price "
            f"previously listed at ${amount} / 1M tokens."
        )
    else:
        claim_text = (
            f"{provider} official pricing table added {model_id} {dimension} price "
            f"at ${amount} / 1M tokens."
        )
    row_hash = _short_row_hash(row)
    return {
        "candidate_kind": "pricing_change",
        "claim_text": claim_text,
        "selector": f"pricing:{row_hash}",
        "snapshot_ref": f"row:{row_hash}",
    }


def _signal_delta_claim(source: SourceDescriptor, action: str, row: dict[str, str]) -> dict[str, str]:
    provider = _provider_label(source)
    signal = row["signal"]
    label = PRICING_SIGNAL_LABELS.get(signal, signal.replace("_", " "))
    candidate_kind = "token_accounting_change" if signal in TOKEN_ACCOUNTING_SIGNALS else "pricing_change"
    claim_text = f"{provider} official pricing table {action} {label} pricing signal."
    row_hash = _short_row_hash(row)
    return {
        "candidate_kind": candidate_kind,
        "claim_text": claim_text,
        "selector": f"pricing-signal:{row_hash}",
        "snapshot_ref": f"signal:{row_hash}",
    }


def _pricing_delta_claims(
    source: SourceDescriptor,
    current_state: dict[str, Any] | None,
    previous_source_state: dict[str, Any] | None,
) -> list[dict[str, str]]:
    previous_state = _pricing_state_from_source_state(previous_source_state)
    if current_state is None or previous_state is None:
        return []

    current_prices = _state_rows_by_key(current_state, "price_points")
    previous_prices = _state_rows_by_key(previous_state, "price_points")
    ambiguous_keys = _ambiguous_price_keys(current_state) | _ambiguous_price_keys(previous_state)
    claims: list[dict[str, str]] = []
    for row_key in sorted((set(current_prices) | set(previous_prices)) - ambiguous_keys):
        current_row = current_prices.get(row_key)
        previous_row = previous_prices.get(row_key)
        if current_row is not None and previous_row is not None:
            if (
                current_row.get("price_usd_per_1m_tokens")
                != previous_row.get("price_usd_per_1m_tokens")
            ):
                claims.append(
                    _price_delta_claim(
                        source,
                        "changed",
                        current_row,
                        previous_row=previous_row,
                    )
                )
        elif current_row is not None:
            claims.append(_price_delta_claim(source, "added", current_row))
        elif previous_row is not None:
            claims.append(_price_delta_claim(source, "removed", previous_row))

    current_signals = _state_rows_by_key(current_state, "pricing_signals")
    previous_signals = _state_rows_by_key(previous_state, "pricing_signals")
    for row_key in sorted(set(current_signals) | set(previous_signals)):
        if row_key in current_signals and row_key not in previous_signals:
            claims.append(_signal_delta_claim(source, "added", current_signals[row_key]))
        elif row_key in previous_signals and row_key not in current_signals:
            claims.append(_signal_delta_claim(source, "removed", previous_signals[row_key]))

    return claims[:MAX_PRICING_DELTA_CLAIMS]


def _limit_row_key(model_id: str, limit_dimension: str) -> str:
    subject = model_id if model_id else "global"
    return f"limit:{subject}:{limit_dimension}"


def _limit_state_row(item: dict[str, Any]) -> dict[str, str] | None:
    if item.get("kind") != "limit_signal":
        return None
    limit_dimension = item.get("limit_dimension")
    limit_value = item.get("limit_value")
    unit = item.get("unit")
    model_id = item.get("model_id", "")
    if (
        not isinstance(limit_dimension, str)
        or limit_dimension not in LIMIT_DIMENSION_PATTERNS
        or not isinstance(limit_value, str)
        or not LIMIT_VALUE_PATTERN.fullmatch(limit_value)
        or unit != limit_dimension
        or not isinstance(model_id, str)
        or (model_id and not _is_bounded_model_id(model_id))
    ):
        return None
    row_key = _limit_row_key(model_id, limit_dimension)
    row_sha256 = _sha256_text(f"{row_key}:{limit_value}")
    row = {
        "row_key": row_key,
        "row_sha256": row_sha256,
        "limit_dimension": limit_dimension,
        "limit_value": limit_value,
        "unit": unit,
    }
    if model_id:
        row["model_id"] = model_id
    return row


def _default_model_row_key(default_scope: str) -> str:
    return f"default_model:{default_scope}"


def _default_model_state_row(item: dict[str, Any]) -> dict[str, str] | None:
    if item.get("kind") != "default_model_signal":
        return None
    default_scope = item.get("default_scope")
    model_id = item.get("model_id")
    if (
        not isinstance(default_scope, str)
        or default_scope not in DEFAULT_SCOPE_LABELS
        or not isinstance(model_id, str)
        or not _is_bounded_model_id(model_id)
    ):
        return None
    row_key = _default_model_row_key(default_scope)
    row_sha256 = _sha256_text(f"{row_key}:{model_id}")
    return {
        "row_key": row_key,
        "row_sha256": row_sha256,
        "default_scope": default_scope,
        "model_id": model_id,
    }


def operational_state_from_items(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    limit_groups: dict[str, list[dict[str, str]]] = {}
    default_groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        limit_row = _limit_state_row(item)
        if limit_row is not None:
            limit_groups.setdefault(limit_row["row_key"], []).append(limit_row)
            continue
        default_row = _default_model_state_row(item)
        if default_row is not None:
            default_groups.setdefault(default_row["row_key"], []).append(default_row)

    limit_rows: list[dict[str, str]] = []
    ambiguous_limit_keys: list[str] = []
    for row_key, rows in sorted(limit_groups.items()):
        values = {row["limit_value"] for row in rows}
        if len(values) > 1:
            ambiguous_limit_keys.append(row_key)
            continue
        limit_rows.append(sorted(rows, key=lambda row: row["row_sha256"])[0])

    default_rows: list[dict[str, str]] = []
    ambiguous_default_model_keys: list[str] = []
    for row_key, rows in sorted(default_groups.items()):
        model_ids = {row["model_id"] for row in rows}
        if len(model_ids) > 1:
            ambiguous_default_model_keys.append(row_key)
            continue
        default_rows.append(sorted(rows, key=lambda row: row["row_sha256"])[0])

    if (
        not limit_rows
        and not default_rows
        and not ambiguous_limit_keys
        and not ambiguous_default_model_keys
    ):
        return None
    return {
        "schema_version": OPERATIONAL_ROW_STATE_SCHEMA_VERSION,
        "limit_signals": limit_rows,
        "default_models": default_rows,
        "ambiguous_limit_keys": ambiguous_limit_keys,
        "ambiguous_default_model_keys": ambiguous_default_model_keys,
    }


def _operational_state_from_source_state(
    previous_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(previous_state, dict):
        return None
    operational_state = previous_state.get("operational_rows")
    if not isinstance(operational_state, dict):
        return None
    if operational_state.get("schema_version") != OPERATIONAL_ROW_STATE_SCHEMA_VERSION:
        return None
    return operational_state


def _ambiguous_operational_keys(operational_state: dict[str, Any] | None, field: str) -> set[str]:
    if not isinstance(operational_state, dict):
        return set()
    keys = operational_state.get(field)
    if not isinstance(keys, list):
        return set()
    return {key for key in keys if isinstance(key, str)}


def _limit_candidate_kind(limit_dimension: str) -> str:
    if limit_dimension in {"requests_per_minute", "tokens_per_minute"}:
        return "rate_limit_change"
    return "quota_change"


def _limit_delta_claim(
    source: SourceDescriptor,
    action: str,
    row: dict[str, str],
    *,
    previous_row: dict[str, str] | None = None,
) -> dict[str, str]:
    provider = _provider_label(source)
    subject = row.get("model_id") or "global usage"
    dimension = LIMIT_DIMENSION_LABELS.get(row["limit_dimension"], row["limit_dimension"])
    value = row["limit_value"]
    if action == "changed" and previous_row is not None:
        previous_value = previous_row["limit_value"]
        claim_text = (
            f"{provider} official source changed {subject} {dimension} limit "
            f"from {previous_value} to {value}."
        )
    elif action == "removed":
        claim_text = (
            f"{provider} official source removed {subject} {dimension} limit "
            f"previously listed as {value}."
        )
    else:
        claim_text = f"{provider} official source added {subject} {dimension} limit {value}."
    row_hash = _short_row_hash(row)
    return {
        "candidate_kind": _limit_candidate_kind(row["limit_dimension"]),
        "claim_text": claim_text,
        "selector": f"limit:{row_hash}",
        "snapshot_ref": f"limit-row:{row_hash}",
    }


def _default_model_delta_claim(
    source: SourceDescriptor,
    action: str,
    row: dict[str, str],
    *,
    previous_row: dict[str, str] | None = None,
) -> dict[str, str]:
    provider = _provider_label(source)
    scope = DEFAULT_SCOPE_LABELS.get(row["default_scope"], row["default_scope"])
    model_id = row["model_id"]
    if action == "changed" and previous_row is not None:
        previous_model_id = previous_row["model_id"]
        claim_text = (
            f"{provider} official source changed {scope} default model "
            f"from {previous_model_id} to {model_id}."
        )
    elif action == "removed":
        claim_text = (
            f"{provider} official source removed {scope} default model "
            f"previously listed as {model_id}."
        )
    else:
        claim_text = f"{provider} official source added {scope} default model {model_id}."
    row_hash = _short_row_hash(row)
    return {
        "candidate_kind": "default_model_change",
        "claim_text": claim_text,
        "selector": f"default-model:{row_hash}",
        "snapshot_ref": f"default-model-row:{row_hash}",
    }


def _operational_delta_claims(
    source: SourceDescriptor,
    current_state: dict[str, Any] | None,
    previous_source_state: dict[str, Any] | None,
) -> list[dict[str, str]]:
    previous_state = _operational_state_from_source_state(previous_source_state)
    if current_state is None or previous_state is None:
        return []

    claims: list[dict[str, str]] = []
    current_limits = _state_rows_by_key(current_state, "limit_signals")
    previous_limits = _state_rows_by_key(previous_state, "limit_signals")
    ambiguous_limit_keys = _ambiguous_operational_keys(
        current_state,
        "ambiguous_limit_keys",
    ) | _ambiguous_operational_keys(previous_state, "ambiguous_limit_keys")
    for row_key in sorted((set(current_limits) | set(previous_limits)) - ambiguous_limit_keys):
        current_row = current_limits.get(row_key)
        previous_row = previous_limits.get(row_key)
        if current_row is not None and previous_row is not None:
            if current_row.get("limit_value") != previous_row.get("limit_value"):
                claims.append(
                    _limit_delta_claim(
                        source,
                        "changed",
                        current_row,
                        previous_row=previous_row,
                    )
                )
        elif current_row is not None:
            claims.append(_limit_delta_claim(source, "added", current_row))
        elif previous_row is not None:
            claims.append(_limit_delta_claim(source, "removed", previous_row))

    current_defaults = _state_rows_by_key(current_state, "default_models")
    previous_defaults = _state_rows_by_key(previous_state, "default_models")
    ambiguous_default_keys = _ambiguous_operational_keys(
        current_state,
        "ambiguous_default_model_keys",
    ) | _ambiguous_operational_keys(previous_state, "ambiguous_default_model_keys")
    for row_key in sorted((set(current_defaults) | set(previous_defaults)) - ambiguous_default_keys):
        current_row = current_defaults.get(row_key)
        previous_row = previous_defaults.get(row_key)
        if current_row is not None and previous_row is not None:
            if current_row.get("model_id") != previous_row.get("model_id"):
                claims.append(
                    _default_model_delta_claim(
                        source,
                        "changed",
                        current_row,
                        previous_row=previous_row,
                    )
                )
        elif current_row is not None:
            claims.append(_default_model_delta_claim(source, "added", current_row))
        elif previous_row is not None:
            claims.append(_default_model_delta_claim(source, "removed", previous_row))

    return claims[:MAX_OPERATIONAL_DELTA_CLAIMS]


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


def _limit_dimensions(text: str) -> list[str]:
    return [
        dimension
        for dimension, patterns in LIMIT_DIMENSION_PATTERNS.items()
        if any(pattern.search(text) for pattern in patterns)
    ]


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
        cell_dimension = _limit_dimension(header_cell)
        value = _limit_value(cell)
        if cell_dimension == dimension and value is not None:
            return value
        if cell_dimension is not None and cell_dimension != dimension:
            continue
        if not any(token in header_cell for token in preferred_header_tokens):
            continue
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
            dimensions = _limit_dimensions(row_text)
            if not dimensions:
                continue
            model_ids = _model_ids_from_text(row_text, parser_name) or [""]
            for dimension in dimensions:
                value = _limit_value_from_row(headers, row, dimension, row_text)
                if value is None:
                    continue
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


def _has_lifecycle_model_header(cell: str) -> bool:
    lower_cell = cell.lower()
    return "model" in lower_cell and "replacement" not in lower_cell


def _has_lifecycle_replacement_header(cell: str) -> bool:
    lower_cell = cell.lower()
    return (
        "alternative" in lower_cell
        or "replacement" in lower_cell
        or "substitute" in lower_cell
        or "suggested" in lower_cell
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


def _lifecycle_row_records(raw: bytes, parser_name: str) -> list[dict[str, Any]]:
    records: dict[tuple[str, tuple[str, ...], tuple[str, ...]], dict[str, Any]] = {}
    model_patterns = _lifecycle_model_patterns(parser_name)
    for table in _table_payload(raw):
        headers: list[str] = []
        for row in table:
            if any(_has_lifecycle_date_header(cell) for cell in row):
                headers = row
                continue
            if not headers:
                continue

            row_model_ids: set[str] = set()
            replacement_model_ids: set[str] = set()
            lifecycle_dates: set[str] = set()
            for index, cell in enumerate(row):
                header = headers[index] if index < len(headers) else ""
                if _has_lifecycle_date_header(header):
                    lifecycle_dates.update(_lifecycle_dates_from_text(cell))
                elif _has_lifecycle_replacement_header(header):
                    replacement_model_ids.update(_model_ids_from_patterns(cell, model_patterns))
                elif _has_lifecycle_model_header(header):
                    row_model_ids.update(_model_ids_from_patterns(cell, model_patterns))

            if not row_model_ids:
                row_model_ids.update(_model_ids_from_patterns(_normalize_text(" ".join(row)), model_patterns))
            replacement_model_ids.difference_update(row_model_ids)
            if not row_model_ids or not lifecycle_dates:
                continue

            row_hash = _sha256_text(_normalize_text(" ".join(row)))[:16]
            for lifecycle_date in lifecycle_dates:
                key = (
                    lifecycle_date,
                    tuple(sorted(row_model_ids)),
                    tuple(sorted(replacement_model_ids)),
                )
                records[key] = {
                    "kind": "lifecycle_row",
                    "lifecycle_date": lifecycle_date,
                    "model_ids": sorted(row_model_ids),
                    "replacement_model_ids": sorted(replacement_model_ids),
                    "row_sha256": row_hash,
                    "source_parser": parser_name,
                }
    return [records[key] for key in sorted(records, reverse=True)]


def _lifecycle_items(raw: bytes, parser_name: str) -> list[dict[str, Any]]:
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
    return model_items + date_items + _lifecycle_row_records(raw, parser_name)


def _format_model_list(model_ids: list[str]) -> str:
    if not model_ids:
        return "unknown model"
    visible = model_ids[:4]
    rendered = ", ".join(visible)
    extra = len(model_ids) - len(visible)
    if extra > 0:
        rendered = f"{rendered}, and {extra} more"
    return rendered


def _lifecycle_claims(source: SourceDescriptor, raw: bytes) -> list[dict[str, str]]:
    candidate_kind, _ = LIFECYCLE_PARSER_CLAIMS[source.parser]
    claims: list[dict[str, str]] = []
    for record in _lifecycle_row_records(raw, source.parser)[:MAX_LIFECYCLE_CLAIMS]:
        model_text = _format_model_list(record["model_ids"])
        replacement_text = _format_model_list(record["replacement_model_ids"])
        replacement_clause = (
            f" with replacement {replacement_text}" if record["replacement_model_ids"] else ""
        )
        row_hash = str(record["row_sha256"])
        claims.append(
            {
                "candidate_kind": candidate_kind,
                "claim_text": (
                    f"{_provider_label(source)} official lifecycle table lists model retirement "
                    f"on {record['lifecycle_date']} for {model_text}{replacement_clause}."
                ),
                "selector": f"lifecycle:{row_hash}",
                "snapshot_ref": f"row:{row_hash}",
            }
        )
    return claims


def _candidate_claims(source: SourceDescriptor, raw: bytes) -> list[dict[str, str]]:
    if source.parser in LIFECYCLE_PARSER_CLAIMS:
        return _lifecycle_claims(source, raw)
    return [_candidate_claim(source)]


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
    previous_state: dict[str, Any] | None = None,
) -> ParsedSourcePayload:
    items: list[dict[str, Any]] = []
    candidate_claims: list[dict[str, str]] = []
    errors: list[str] = []
    operational_state: dict[str, Any] | None = None
    pricing_state: dict[str, Any] | None = None
    scoped = scoped_source_content(source, raw)
    raw = scoped.raw
    errors.extend(scoped.errors)
    if source.parser == "atom_status":
        items, atom_errors = _atom_items(raw)
        errors.extend(atom_errors)
    elif source.parser in DATED_ANNOUNCEMENT_PARSER_NAMES:
        items, announcement_claims, announcement_errors = _dated_announcement_payload(source, raw)
        errors.extend(announcement_errors)
        if changed:
            candidate_claims = announcement_claims
    elif source.parser in MODEL_PARSER_PATTERNS:
        items = _model_items(raw, source.parser)
        operational_state = operational_state_from_items(items)
        if changed:
            candidate_claims = _operational_delta_claims(
                source,
                operational_state,
                previous_state,
            )
    elif source.parser in LIFECYCLE_PARSER_PATTERNS:
        items = _lifecycle_items(raw, source.parser)
    elif source.parser in PRICING_PARSER_NAMES:
        items = _pricing_items(raw, source.parser)
        pricing_state = pricing_state_from_items(items)
        operational_state = operational_state_from_items(items)
        if changed:
            candidate_claims = _pricing_delta_claims(
                source,
                pricing_state,
                previous_state,
            ) + _operational_delta_claims(source, operational_state, previous_state)
    elif source.parser == "aws_bedrock_model_cards":
        items = _model_ref_items_from_visible_text(raw, source.parser)
    elif source.parser == "statuspage_html":
        items = _statuspage_items(raw)

    return ParsedSourcePayload(
        items=items,
        raw_excerpt_hashes=[],
        candidate_claims=candidate_claims or (_candidate_claims(source, raw) if changed else []),
        errors=errors,
        snapshot_ref=None,
    )
