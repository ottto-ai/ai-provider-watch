# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.event_scaffold import event_id_from_parts, normalize_ref, slugify

SECTION_PATTERN = re.compile(r"^###\s+(?P<label>.+?)\s*$", re.MULTILINE)
URL_PATTERN = re.compile(r"https?://[^\s<>)\\]+")

LABEL_TO_FIELD = {
    "Provider": "provider",
    "Official source URLs": "source_urls",
    "APW source key": "source_key",
    "Source authority": "source_authority",
    "Event date": "event_date",
    "Effective date": "effective_at",
    "Event kind": "event_kind",
    "Affected surfaces, models, or agent apps": "affected_refs",
    "Proposed impact rows": "proposed_impacts",
    "Why this matters to developers": "developer_impact",
    "Contributor path": "contributor_path",
    "Safety": "safety",
}

REQUIRED_FIELDS = (
    "provider",
    "source_urls",
    "source_authority",
    "event_date",
    "event_kind",
    "developer_impact",
    "contributor_path",
    "safety",
)

PROVIDER_SLUGS = {
    "aws": "aws-bedrock",
    "aws bedrock": "aws-bedrock",
    "bedrock": "aws-bedrock",
    "azure": "azure-openai",
    "azure openai": "azure-openai",
    "gemini": "google",
    "google": "google",
    "google gemini": "google",
    "vertex": "google",
    "vertex ai": "google",
}

SOURCE_AUTHORITY_MAP = {
    "official_pricing": "official_pricing",
    "official_docs": "official_docs",
    "official_status": "official_status",
    "official_repo": "official_repo",
    "official_blog": "official_blog",
    "unknown official source": "manual",
}

IMPACT_BY_EVENT_KIND = {
    "api_contract_change": "migration",
    "billing_channel_change": "cost",
    "caching_change": "cost",
    "default_model_change": "behavior",
    "model_deprecation": "migration",
    "model_launch": "availability",
    "model_retirement": "migration",
    "pricing_change": "cost",
    "quota_change": "quota",
    "rate_limit_change": "rate_limit",
    "regional_availability_change": "availability",
    "status_incident": "availability",
    "subscription_change": "cost",
    "token_accounting_change": "cost",
    "workflow_behavior_change": "behavior",
}

DIRECTION_BY_EVENT_KIND = {
    "model_launch": "added",
    "regional_availability_change": "added",
    "model_deprecation": "removed",
    "model_retirement": "removed",
}

PLACEHOLDER_SOURCE_KEY = "<source-key>"
PLACEHOLDER_SHA = "<sha256-of-bounded-official-source-snapshot>"
PLACEHOLDER_SCOPE = "<scope-ref>"
PLACEHOLDER_TITLE = "<reviewed event title>"
PLACEHOLDER_SUMMARY = "<reviewed factual summary, not copied from the issue body>"


@dataclass(frozen=True)
class MissingEventIssueTriage:
    fields: dict[str, str]
    source_urls: list[str]
    missing_required: list[str]
    unsafe_fields: list[str]
    recommendation: str
    scaffold_command: list[str]
    checklist: list[str]
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "source_urls": self.source_urls,
            "missing_required": self.missing_required,
            "unsafe_fields": self.unsafe_fields,
            "recommendation": self.recommendation,
            "scaffold_command": self.scaffold_command,
            "checklist": self.checklist,
            "notes": self.notes,
            "untrusted_input_policy": (
                "Issue bodies are review input only. Do not copy issue prose into ProviderEvents "
                "without source-owner review against official evidence."
            ),
        }


def _normalize_section_value(value: str) -> str:
    normalized = value.strip()
    if normalized in {"_No response_", "No response", "None", "N/A"}:
        return ""
    return normalized


def parse_issue_form_body(markdown: str) -> dict[str, str]:
    matches = list(SECTION_PATTERN.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group("label").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        field = LABEL_TO_FIELD.get(label)
        if field is not None:
            sections[field] = _normalize_section_value(markdown[start:end])
    return sections


def _source_urls(value: str) -> list[str]:
    values = []
    for match in URL_PATTERN.finditer(value):
        url = match.group(0).rstrip(".,;")
        if url not in values:
            values.append(url)
    return values


def _provider_slug(value: str) -> str:
    raw = " ".join(value.split()).strip()
    mapped = PROVIDER_SLUGS.get(raw.lower())
    if mapped:
        return mapped
    if raw.lower().startswith("provider:"):
        return raw.split(":", 1)[1].strip()
    return slugify(raw.replace("_", "-"))


def _source_authority(value: str) -> str:
    normalized = " ".join(value.split()).strip().lower()
    return SOURCE_AUTHORITY_MAP.get(normalized, normalized.replace(" ", "_") or "manual")


def _event_kind(value: str) -> str:
    normalized = " ".join(value.split()).strip().lower().replace(" ", "_")
    return "" if normalized == "other" else normalized


def _first_nonempty_line(value: str) -> str:
    for line in value.splitlines():
        normalized = line.strip().strip("-* ")
        if normalized:
            return normalized
    return ""


def _missing_required(fields: dict[str, str], source_urls: list[str], event_kind: str) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if not fields.get(field)]
    if not source_urls and "source_urls" not in missing:
        missing.append("source_urls")
    if not event_kind and "event_kind" not in missing:
        missing.append("event_kind")
    return sorted(set(missing))


def _unsafe_fields(fields: dict[str, str]) -> list[str]:
    return sorted(
        field for field, value in fields.items() if value and contains_prompt_injection_marker(value)
    )


def _recommendation(*, missing_required: list[str], unsafe_fields: list[str], contributor_path: str) -> str:
    if unsafe_fields:
        return "needs_source_owner_review"
    if missing_required:
        return "needs_more_information"
    normalized_path = contributor_path.lower()
    if "open a pr" in normalized_path:
        return "direct_pr_ready"
    if "candidate-review" in normalized_path:
        return "candidate_review_path"
    return "source_owner_review"


def _scaffold_command(
    *,
    fields: dict[str, str],
    source_urls: list[str],
    event_kind: str,
) -> list[str]:
    provider = _provider_slug(fields.get("provider", "provider"))
    provider_ref = normalize_ref(provider, prefix="provider")
    event_date = fields.get("event_date") or "YYYY-MM-DD"
    source_url = source_urls[0] if source_urls else "<official-source-url>"
    source_key = _first_nonempty_line(fields.get("source_key", "")) or PLACEHOLDER_SOURCE_KEY
    source_authority = _source_authority(fields.get("source_authority", "manual"))
    selected_kind = event_kind or "<event-kind>"
    impact_kind = IMPACT_BY_EVENT_KIND.get(selected_kind, "unknown")
    direction = DIRECTION_BY_EVENT_KIND.get(selected_kind, "changed")
    event_output = f"data/events/{event_date}-{provider}-{slugify(selected_kind or 'provider-event')}.json"
    event_id = event_id_from_parts(
        event_date=event_date,
        provider_ref=provider_ref,
        title=selected_kind or "provider event",
    )
    command = [
        "uv",
        "run",
        "apw",
        "event",
        "scaffold",
        "--event-id",
        event_id,
        "--event-date",
        event_date,
        "--provider",
        provider,
        "--kind",
        selected_kind,
        "--title",
        PLACEHOLDER_TITLE,
        "--summary",
        PLACEHOLDER_SUMMARY,
        "--source-url",
        source_url,
        "--source-key",
        source_key,
        "--source-authority",
        source_authority,
        "--content-sha256",
        PLACEHOLDER_SHA,
        "--scope-ref",
        PLACEHOLDER_SCOPE,
        "--impact-kind",
        impact_kind,
        "--direction",
        direction,
        "--output",
        event_output,
    ]
    if fields.get("effective_at"):
        command.extend(["--effective-at", fields["effective_at"]])
    return command


def build_missing_event_issue_triage(markdown: str) -> MissingEventIssueTriage:
    fields = parse_issue_form_body(markdown)
    source_urls = _source_urls(fields.get("source_urls", ""))
    event_kind = _event_kind(fields.get("event_kind", ""))
    missing_required = _missing_required(fields, source_urls, event_kind)
    unsafe_fields = _unsafe_fields(fields)
    checklist = [
        "Verify every URL is official, public, unauthenticated, and provider-controlled.",
        "Hash a bounded official-source snapshot without committing provider prose.",
        "Rewrite title and summary from official facts; do not copy issue-body prose.",
        "Replace placeholder scope, impact, direction, severity, and detail fields before PR review.",
        "Run uv run apw validate, uv run apw index, uv run apw validate, and uv run apw index --check.",
    ]
    if event_kind in {"model_launch", "model_deprecation", "model_retirement"}:
        checklist.append("Add at least one --model-ref and verify model registry refs before promotion.")
    notes = [
        "Issue bodies, comments, pasted provider text, screenshots, MCP text, and social posts are untrusted data.",
    ]
    if unsafe_fields:
        notes.append(
            "Prompt-injection-like text was found; use the issue only as a pointer to official evidence."
        )
    if missing_required:
        notes.append(f"Missing required issue-form fields: {', '.join(missing_required)}.")
    return MissingEventIssueTriage(
        fields=fields,
        source_urls=source_urls,
        missing_required=missing_required,
        unsafe_fields=unsafe_fields,
        recommendation=_recommendation(
            missing_required=missing_required,
            unsafe_fields=unsafe_fields,
            contributor_path=fields.get("contributor_path", ""),
        ),
        scaffold_command=_scaffold_command(fields=fields, source_urls=source_urls, event_kind=event_kind),
        checklist=checklist,
        notes=notes,
    )


def render_shell_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def render_missing_event_issue_triage_markdown(triage: MissingEventIssueTriage) -> str:
    lines = [
        "# Missing Event Triage",
        "",
        f"Recommendation: `{triage.recommendation}`",
        "",
        "## Extracted Fields",
        "",
    ]
    for field in sorted(triage.fields):
        if field in triage.unsafe_fields:
            value = "_redacted: prompt-injection-like text detected_"
        else:
            value = triage.fields[field].strip() or "_empty_"
        if "\n" in value:
            value = value.splitlines()[0].strip()
            value = f"{value} ..."
        lines.append(f"- `{field}`: {value}")
    lines.extend(["", "## Official URLs", ""])
    if triage.source_urls:
        lines.extend(f"- {url}" for url in triage.source_urls)
    else:
        lines.append("- _none detected_")
    lines.extend(["", "## Safety", ""])
    for note in triage.notes:
        lines.append(f"- {note}")
    if triage.unsafe_fields:
        lines.append(f"- Unsafe fields: `{', '.join(triage.unsafe_fields)}`")
    lines.extend(["", "## Scaffold Command", "", "Review and replace placeholders before running:", "", "```bash"])
    lines.append(render_shell_command(triage.scaffold_command))
    lines.extend(["```", "", "## Review Checklist", ""])
    lines.extend(f"- [ ] {item}" for item in triage.checklist)
    lines.append("")
    return "\n".join(lines)
