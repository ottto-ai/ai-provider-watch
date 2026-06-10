# SPDX-FileCopyrightText: AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shlex
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai_provider_watch.core.temporal import require_rfc3339_date_time
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.event_scaffold import (
    EventScaffoldError,
    build_event_scaffold,
)
from ai_provider_watch.pipeline.promotion import KIND_TO_IMPACT_KINDS
from ai_provider_watch.pipeline.review_pr import CandidateFile

DEFAULT_CANDIDATE_SCAFFOLD_LIMITATION = (
    "Draft generated from a review-only candidate; verify official evidence, "
    "event date, affected scope, detail shape, and duplicate status before promotion."
)

DIRECTION_BY_KIND = {
    "model_launch": "added",
    "regional_availability_change": "added",
    "model_deprecation": "removed",
    "model_retirement": "removed",
    "status_recovery": "changed",
}


class CandidateScaffoldError(ValueError):
    """Raised when a candidate cannot be converted into an event scaffold."""


@dataclass(frozen=True)
class CandidateEventScaffold:
    event: dict[str, Any]
    candidate_id: str


def _candidate_by_id(candidate_files: list[CandidateFile], candidate_id: str) -> dict[str, Any]:
    matches = [
        candidate_file.payload
        for candidate_file in candidate_files
        if candidate_file.payload.get("id") == candidate_id
    ]
    if not matches:
        raise CandidateScaffoldError(f"candidate not found: {candidate_id}")
    if len(matches) > 1:
        raise CandidateScaffoldError(f"candidate id is not unique: {candidate_id}")
    return matches[0]


def _first_string(values: Any, *, label: str) -> str:
    if isinstance(values, list):
        strings = [item for item in values if isinstance(item, str) and item.strip()]
        if strings:
            return strings[0]
    raise CandidateScaffoldError(f"candidate has no usable {label}")


def _first_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence_refs = candidate.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        raise CandidateScaffoldError("candidate has no usable evidence_refs")
    for evidence in evidence_refs:
        if isinstance(evidence, dict):
            required = ("source_key", "url", "retrieved_at", "authority", "content_sha256")
            if all(isinstance(evidence.get(key), str) and evidence.get(key) for key in required):
                return evidence
    raise CandidateScaffoldError("candidate has no complete evidence ref")


def _provider_slug(provider_ref: str) -> str:
    return provider_ref.split(":", 1)[1] if ":" in provider_ref else provider_ref


def _human_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").replace("/", " ").title()


def _event_date(value: str | None, evidence: dict[str, Any]) -> tuple[str, str]:
    if value:
        date.fromisoformat(value)
        return value, "exact"
    retrieved_at = str(evidence["retrieved_at"])
    require_rfc3339_date_time(retrieved_at, "candidate evidence retrieved_at")
    return retrieved_at[:10], "unknown"


def _summary(candidate: dict[str, Any], override: str | None) -> str:
    if override:
        return override
    claim_text = candidate.get("claim_text")
    if not isinstance(claim_text, str) or contains_prompt_injection_marker(claim_text):
        raise CandidateScaffoldError("candidate claim_text is not safe enough for a draft summary")
    normalized = " ".join(claim_text.split())
    if len(normalized) < 20:
        normalized = f"{normalized}. Verify the official source before promotion."
    if len(normalized) <= 420:
        return normalized
    return f"{normalized[:417].rstrip()}..."


def _event_kind(candidate: dict[str, Any], override: str | None) -> str:
    if override:
        return override
    candidate_kind = candidate.get("candidate_kind")
    if not isinstance(candidate_kind, str) or candidate_kind == "unknown":
        raise CandidateScaffoldError("--kind is required for candidates with unknown candidate_kind")
    return candidate_kind


def _impact_kind(event_kind: str, override: str | None) -> str:
    if override:
        return override
    return KIND_TO_IMPACT_KINDS.get(event_kind, ["unknown"])[0]


def _limitations(candidate: dict[str, Any], extra: list[str] | None) -> list[str]:
    values = [DEFAULT_CANDIDATE_SCAFFOLD_LIMITATION]
    if extra:
        values.extend(extra)
    candidate_limitations = candidate.get("limitations")
    if isinstance(candidate_limitations, list):
        values.extend(item for item in candidate_limitations if isinstance(item, str))
    return list(dict.fromkeys(values))


def build_candidate_event_scaffold(
    candidate_files: list[CandidateFile],
    *,
    candidate_id: str,
    event_date: str | None = None,
    provider: str | None = None,
    event_kind: str | None = None,
    title: str | None = None,
    summary: str | None = None,
    scope_type: str | None = None,
    scope_ref: str | None = None,
    impact_kind: str | None = None,
    direction: str | None = None,
    severity: str = "medium",
    confidence: str = "confirmed",
    observed_at: str | None = None,
    lifecycle_status: str = "reviewed",
    detail_kind: str = "generic_change",
    model_refs: list[str] | None = None,
    replacement_refs: list[str] | None = None,
    lifecycle_action: str | None = None,
    migration_notes: str | None = None,
    new_default: str | None = None,
    old_default: str | None = None,
    status: str | None = None,
    components: list[str] | None = None,
    subscription_impact: str = "unknown",
    api_usage_impact: str = "direct",
    recommended_action: str | None = None,
    limitations: list[str] | None = None,
) -> CandidateEventScaffold:
    candidate = _candidate_by_id(candidate_files, candidate_id)
    evidence = _first_evidence(candidate)
    provider_ref = provider or _first_string(candidate.get("provider_refs"), label="provider_refs")
    selected_kind = _event_kind(candidate, event_kind)
    selected_date, default_date_confidence = _event_date(event_date, evidence)
    observed_value = observed_at or str(evidence["retrieved_at"])
    require_rfc3339_date_time(observed_value, "observed_at")
    selected_scope_ref = scope_ref or provider_ref
    selected_scope_type = scope_type or ("provider" if selected_scope_ref == provider_ref else "provider_surface")
    selected_title = title or f"{_human_label(_provider_slug(provider_ref))} {_human_label(selected_kind)} Candidate"
    selected_summary = _summary(candidate, summary)
    selected_direction = direction or DIRECTION_BY_KIND.get(selected_kind, "unknown")

    try:
        event = build_event_scaffold(
            event_date=selected_date,
            provider=provider_ref,
            event_kind=selected_kind,
            title=selected_title,
            summary=selected_summary,
            source_url=str(evidence["url"]),
            source_key=str(evidence["source_key"]),
            source_authority=str(evidence["authority"]),
            content_sha256=str(evidence["content_sha256"]),
            scope_type=selected_scope_type,
            scope_ref=selected_scope_ref,
            impact_kind=_impact_kind(selected_kind, impact_kind),
            direction=selected_direction,
            severity=severity,
            confidence=confidence,
            observed_at=observed_value,
            lifecycle_status=lifecycle_status,
            date_confidence="exact" if event_date else default_date_confidence,
            detail_kind=detail_kind,
            model_refs=model_refs,
            replacement_refs=replacement_refs,
            lifecycle_action=lifecycle_action,
            migration_notes=migration_notes,
            new_default=new_default,
            old_default=old_default,
            status=status,
            components=components,
            subscription_impact=subscription_impact,
            api_usage_impact=api_usage_impact,
            recommended_action=recommended_action
            or "Verify official evidence and edit this candidate-derived draft before opening a promotion PR.",
            selector=evidence.get("selector") if isinstance(evidence.get("selector"), str) else None,
            snapshot_ref=evidence.get("snapshot_ref") if isinstance(evidence.get("snapshot_ref"), str) else None,
            license_note="Official evidence metadata copied from a review-only candidate; no source prose copied.",
            tags=[
                f"candidate:{candidate_id}",
                provider_ref,
                f"impact:{selected_kind}",
            ],
            limitations=_limitations(candidate, limitations),
        )
    except EventScaffoldError as exc:
        raise CandidateScaffoldError(str(exc)) from exc
    return CandidateEventScaffold(event=event, candidate_id=candidate_id)


def _arg(parts: list[str], name: str, value: Any) -> None:
    if value is not None:
        parts.extend([name, str(value)])


def _args_for_event_scaffold(event: dict[str, Any]) -> list[str]:
    evidence = event["evidence_refs"][0]
    impact = event["impacts"][0]
    detail = event["detail"]
    parts = [
        "uv",
        "run",
        "apw",
        "event",
        "scaffold",
        "--event-id",
        event["id"],
        "--event-date",
        event["event_date"],
        "--provider",
        event["provider_refs"][0],
        "--kind",
        event["event_kind"],
        "--title",
        event["title"],
        "--summary",
        event["summary"],
        "--source-url",
        evidence["url"],
        "--source-key",
        evidence["source_key"],
        "--source-authority",
        evidence["authority"],
        "--content-sha256",
        evidence["content_sha256"],
        "--scope-type",
        impact["scope_type"],
        "--scope-ref",
        impact["scope_ref"],
        "--impact-kind",
        impact["impact_kind"],
        "--direction",
        impact["direction"],
        "--severity",
        event["severity"],
        "--confidence",
        event["confidence"],
        "--observed-at",
        event["observed_at"],
        "--lifecycle-status",
        event["lifecycle_status"],
        "--date-confidence",
        event.get("date_confidence", "exact"),
        "--detail-kind",
        detail["kind"],
    ]
    _arg(parts, "--selector", evidence.get("selector"))
    _arg(parts, "--snapshot-ref", evidence.get("snapshot_ref"))
    _arg(parts, "--license-note", evidence.get("license_note"))
    _arg(parts, "--recommended-action", impact.get("recommended_action"))
    _arg(parts, "--subscription-impact", impact.get("subscription_impact"))
    _arg(parts, "--api-usage-impact", impact.get("api_usage_impact"))
    for tag in event.get("tags", []):
        parts.extend(["--tag", str(tag)])
    for limitation in event.get("limitations", []):
        parts.extend(["--limitation", str(limitation)])
    return parts


def render_candidate_event_scaffold_command(
    scaffold: CandidateEventScaffold,
    *,
    output: str | None = None,
) -> str:
    parts = _args_for_event_scaffold(scaffold.event)
    if output:
        parts.extend(["--output", output])
    return " \\\n  ".join(shlex.quote(part) for part in parts)
