from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ai_provider_watch.core.temporal import is_rfc3339_date_time, require_rfc3339_date_time
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.candidates import KNOWN_CANDIDATE_KINDS, PARSER_CONTRACT_VERSION
from ai_provider_watch.pipeline.review_pr import CandidateFile
from ai_provider_watch.sources.registry import SourceDescriptor, is_url_allowed_for_source

PROMOTION_READINESS_REPORT_SCHEMA_VERSION = "apw.promotion_readiness_report.v0"

PROVIDER_CONTROLLED_AUTHORITIES = {
    "official_blog",
    "official_docs",
    "official_pricing",
    "official_repo",
    "official_status",
}

HIGH_SIGNAL_KINDS = {
    "api_contract_change",
    "billing_channel_change",
    "caching_change",
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
    "token_accounting_change",
    "workflow_behavior_change",
}

DATED_SOURCE_TYPES = {
    "atom_feed",
    "github_releases",
    "rss_feed",
    "status_page",
}

DATED_PARSER_NAMES = {
    "anthropic_release_notes",
    "anthropic_news_index",
    "aws_bedrock_whats_new_feed",
    "azure_openai_whats_new",
    "azure_openai_legacy_models",
    "google_gemini_changelog",
    "google_vertex_model_versions",
    "openai_api_changelog",
    "openai_news_feed",
    "openai_deprecations",
}

GENERIC_CLAIM_MARKERS = (
    "changed and needs maintainer review",
    "documentation changed",
    "docs changed",
    "feed changed",
    "needs maintainer review",
    "page changed",
    "possible incident",
    "possible status",
    "source changed",
    "supported model list",
)

CONCRETE_DATE_PATTERN = re.compile(
    r"\b[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?\b"
    r"|\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+[0-9]{1,2},\s+[0-9]{4}\b",
    re.IGNORECASE,
)

CONCRETE_ACTION_MARKERS = (
    "announced",
    "available",
    "availability",
    "billing",
    "cache",
    "caching",
    "cost",
    "deprecation",
    "incident",
    "launch",
    "released",
    "reports",
    "retirement",
    "status",
    "token",
)

SUBJECT_SIGNAL_PATTERN = re.compile(
    r"\b(?:api|aws-bedrock|azure-openai|claude(?:-[a-z0-9.]+)+|codex|computer-use|gemini|gpt|model|openai|realtime|responses-api|sdk|vertex-ai)\b",
    re.IGNORECASE,
)

READINESS_TO_RECOMMENDATION = {
    "auto_promotion_eligible": "promote",
    "needs_source_owner_review": "needs_human_review",
    "not_ready": "reject",
    "duplicate_or_superseded": "duplicate",
}

KIND_TO_IMPACT_KINDS = {
    "api_contract_change": ["migration", "behavior"],
    "billing_channel_change": ["cost"],
    "caching_change": ["cost", "behavior"],
    "default_model_change": ["behavior", "cost"],
    "model_deprecation": ["migration", "availability"],
    "model_launch": ["availability"],
    "model_retirement": ["migration", "availability"],
    "pricing_change": ["cost"],
    "quota_change": ["quota"],
    "rate_limit_change": ["rate_limit"],
    "regional_availability_change": ["availability"],
    "sdk_behavior_change": ["behavior", "migration"],
    "status_incident": ["availability"],
    "status_recovery": ["availability"],
    "subscription_change": ["quota", "cost"],
    "token_accounting_change": ["cost", "behavior"],
    "workflow_behavior_change": ["behavior", "cost"],
}

CANDIDATE_ID_PATTERN = re.compile(r"^candidate-[a-z0-9][a-z0-9-]*-[a-f0-9]{16}$")
SOURCE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*[a-z0-9]$|^[a-z0-9]$")
PROVIDER_REF_PATTERN = re.compile(r"^provider:[a-z0-9][a-z0-9_-]*$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
DEDUPE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{12,200}$")
RELATIVE_JSON_PATH_PATTERN = re.compile(r"^(?:[A-Za-z0-9._+-]+/)*[A-Za-z0-9._+-]+\.json$")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            rendered = path.relative_to(root).as_posix()
        except ValueError:
            rendered = path.as_posix()
    else:
        rendered = path.as_posix()
    if contains_prompt_injection_marker(rendered):
        return "<invalid-path>"
    return rendered if RELATIVE_JSON_PATH_PATTERN.fullmatch(rendered) else "<invalid-path>"


def _safe_scalar(value: Any, pattern: re.Pattern[str], fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    if contains_prompt_injection_marker(value):
        return fallback
    return value if pattern.fullmatch(value) else fallback


def _safe_values(value: Any, pattern: re.Pattern[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            item
            for item in value
            if isinstance(item, str)
            and not contains_prompt_injection_marker(item)
            and pattern.fullmatch(item)
        }
    )


def _candidate_kind(value: Any) -> str:
    if not isinstance(value, str) or contains_prompt_injection_marker(value):
        return "<invalid-kind>"
    return value if value in KNOWN_CANDIDATE_KINDS else "<invalid-kind>"


def _source_authorities(sources: list[SourceDescriptor]) -> list[str]:
    return sorted({source.authority for source in sources if source.authority})


def _source_types(sources: list[SourceDescriptor]) -> list[str]:
    return sorted({source.source_type for source in sources if source.source_type})


def _flag_score(flags: dict[str, bool]) -> int:
    if not flags:
        return 0
    return round(sum(1 for value in flags.values() if value) / len(flags) * 100)


def _candidate_evidence_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_refs = candidate.get("evidence_refs", [])
    return [item for item in evidence_refs if isinstance(item, dict)] if isinstance(evidence_refs, list) else []


def _evidence_summary(evidence: dict[str, Any]) -> dict[str, str]:
    return {
        "source_key": str(evidence.get("source_key") or "<invalid-source>"),
        "url": str(evidence.get("url") or "<invalid-url>"),
        "authority": str(evidence.get("authority") or "<invalid-authority>"),
        "retrieved_at": str(evidence.get("retrieved_at") or "<invalid-date-time>"),
    }


def _impact_kinds(candidate_kind: str) -> list[str]:
    return KIND_TO_IMPACT_KINDS.get(candidate_kind, ["unknown"])


def _specific_fact_signal(claim_text: Any) -> bool:
    if not isinstance(claim_text, str) or contains_prompt_injection_marker(claim_text):
        return False
    normalized = re.sub(r"\s+", " ", claim_text.lower())
    if any(marker in normalized for marker in GENERIC_CLAIM_MARKERS):
        return False
    return (
        bool(CONCRETE_DATE_PATTERN.search(claim_text))
        and bool(SUBJECT_SIGNAL_PATTERN.search(claim_text))
        and any(marker in normalized for marker in CONCRETE_ACTION_MARKERS)
    )


def _concrete_date_signal(claim_text: Any) -> bool:
    return isinstance(claim_text, str) and bool(CONCRETE_DATE_PATTERN.search(claim_text))


def _specific_subject_signal(claim_text: Any) -> bool:
    return isinstance(claim_text, str) and bool(SUBJECT_SIGNAL_PATTERN.search(claim_text))


def _readiness(
    *,
    critical_blockers: list[str],
    review_blockers: list[str],
    duplicate_blockers: list[str],
) -> str:
    if duplicate_blockers:
        return "duplicate_or_superseded"
    if critical_blockers:
        return "not_ready"
    if review_blockers:
        return "needs_source_owner_review"
    return "auto_promotion_eligible"


def _report_candidate(
    candidate_file: CandidateFile,
    *,
    root: Path | None,
    sources_by_key: dict[str, SourceDescriptor],
    dedupe_counts: Counter[str],
    candidate_id_counts: Counter[str],
) -> dict[str, Any]:
    candidate = candidate_file.payload
    candidate_id = _safe_scalar(candidate.get("id"), CANDIDATE_ID_PATTERN, "<invalid-id>")
    candidate_kind = _candidate_kind(candidate.get("candidate_kind"))
    source_keys = _safe_values(candidate.get("source_keys"), SOURCE_KEY_PATTERN)
    provider_refs = _safe_values(candidate.get("provider_refs"), PROVIDER_REF_PATTERN)
    dedupe_key = _safe_scalar(candidate.get("dedupe_key"), DEDUPE_KEY_PATTERN, "<invalid-dedupe-key>")
    evidence_refs = _candidate_evidence_refs(candidate)
    claim_text = candidate.get("claim_text")
    prompt_safe = isinstance(claim_text, str) and not contains_prompt_injection_marker(claim_text)
    concrete_date_signal = _concrete_date_signal(claim_text)
    specific_subject_signal = _specific_subject_signal(claim_text)
    specific_fact_signal = _specific_fact_signal(claim_text)
    claim_text_hash = _sha256_text(claim_text) if isinstance(claim_text, str) else "<invalid-sha256>"

    critical_blockers: list[str] = []
    review_blockers: list[str] = []
    duplicate_blockers: list[str] = []
    reasons: list[str] = []

    if candidate_id == "<invalid-id>":
        critical_blockers.append("Candidate id is missing, malformed, or prompt-like.")
    if candidate_id_counts.get(candidate_id, 0) > 1:
        duplicate_blockers.append("Candidate id appears more than once in this review window.")
    if not source_keys:
        critical_blockers.append("Candidate has no valid source keys.")
    if not provider_refs:
        critical_blockers.append("Candidate has no valid provider refs.")
    if candidate_kind == "<invalid-kind>":
        critical_blockers.append("Candidate kind is missing, malformed, or unsupported.")
    elif candidate_kind == "unknown" or candidate_kind not in HIGH_SIGNAL_KINDS:
        critical_blockers.append("Candidate kind is not high-signal enough for promotion-ready handling.")
    if dedupe_key == "<invalid-dedupe-key>":
        critical_blockers.append("Candidate dedupe key is missing or malformed.")
    elif dedupe_counts[dedupe_key] > 1:
        duplicate_blockers.append("Candidate dedupe key appears more than once in this review window.")
    if not prompt_safe:
        critical_blockers.append("Candidate claim text is missing or contains prompt-like text.")
    if not specific_fact_signal:
        review_blockers.append("Candidate claim is generic change-detection output; source owner must verify a concrete fact before promotion.")

    parser = candidate.get("parser")
    if not isinstance(parser, dict) or parser.get("contract_version") != PARSER_CONTRACT_VERSION:
        critical_blockers.append("Candidate parser contract is missing or unsupported.")

    sources: list[SourceDescriptor] = []
    for source_key in source_keys:
        source = sources_by_key.get(source_key)
        if source is None:
            critical_blockers.append(f"Source {source_key} is not in the source registry.")
            continue
        sources.append(source)
        if source.authority not in PROVIDER_CONTROLLED_AUTHORITIES:
            critical_blockers.append(f"Source {source_key} authority {source.authority} is not provider-controlled official evidence.")
        if not source.enabled or source.automation_status != "enabled_deterministic":
            review_blockers.append(f"Source {source_key} is not enabled deterministic automation.")
        if source.parser == "manual_review":
            review_blockers.append(f"Source {source_key} still uses manual_review parser.")
        for blocker in source.graduation_blockers:
            review_blockers.append(f"Source {source_key} graduation blocker: {blocker}")

    evidence_summaries: list[dict[str, str]] = []
    for evidence in evidence_refs:
        summary = _evidence_summary(evidence)
        evidence_summaries.append(summary)
        source_key = summary["source_key"]
        source = sources_by_key.get(source_key)
        if source_key not in source_keys:
            critical_blockers.append(f"Evidence source {source_key} is not listed on the candidate.")
        if source is None:
            critical_blockers.append(f"Evidence source {source_key} is not in the source registry.")
            continue
        authority = summary["authority"]
        if authority not in PROVIDER_CONTROLLED_AUTHORITIES:
            critical_blockers.append(f"Evidence authority {authority} is not provider-controlled official evidence.")
        if authority != source.authority:
            critical_blockers.append(f"Evidence authority {authority} does not match source {source_key} authority {source.authority}.")
        if not is_url_allowed_for_source(summary["url"], source):
            critical_blockers.append(f"Evidence URL for {source_key} is outside the source allowed domains.")
        if not is_rfc3339_date_time(summary["retrieved_at"]):
            critical_blockers.append(f"Evidence retrieved_at for {source_key} is not RFC3339.")
        if not SHA256_PATTERN.fullmatch(str(evidence.get("content_sha256") or "")):
            critical_blockers.append(f"Evidence content_sha256 for {source_key} is missing or malformed.")
        if not SHA256_PATTERN.fullmatch(str(evidence.get("fingerprint") or "")):
            critical_blockers.append(f"Evidence fingerprint for {source_key} is missing or malformed.")

    if not evidence_summaries:
        critical_blockers.append("Candidate has no evidence refs.")

    official_provider_controlled = bool(sources) and all(
        source.authority in PROVIDER_CONTROLLED_AUTHORITIES for source in sources
    ) and all(evidence["authority"] in PROVIDER_CONTROLLED_AUTHORITIES for evidence in evidence_summaries)
    enabled_deterministic = bool(sources) and all(
        source.enabled and source.automation_status == "enabled_deterministic" and source.parser != "manual_review"
        for source in sources
    )
    dated_source_signal = bool(sources) and any(
        source.source_type in DATED_SOURCE_TYPES or source.parser in DATED_PARSER_NAMES
        for source in sources
    )
    if not dated_source_signal:
        review_blockers.append("Source type does not provide an independent dated change signal.")
    allowed_evidence = bool(evidence_summaries) and not any("Evidence URL" in blocker for blocker in critical_blockers)
    high_signal_kind = candidate_kind in HIGH_SIGNAL_KINDS
    no_duplicates = not duplicate_blockers
    schema_safe = not critical_blockers

    flags = {
        "official_provider_controlled": official_provider_controlled,
        "enabled_deterministic": enabled_deterministic,
        "allowed_evidence": allowed_evidence,
        "high_signal_kind": high_signal_kind,
        "dated_source_signal": dated_source_signal,
        "concrete_date_signal": concrete_date_signal,
        "specific_subject_signal": specific_subject_signal,
        "specific_fact_signal": specific_fact_signal,
        "schema_safe": schema_safe,
        "prompt_safe": prompt_safe,
        "no_duplicate_in_window": no_duplicates,
    }
    readiness = _readiness(
        critical_blockers=critical_blockers,
        review_blockers=review_blockers,
        duplicate_blockers=duplicate_blockers,
    )
    recommendation = READINESS_TO_RECOMMENDATION[readiness]

    if official_provider_controlled:
        reasons.append("Every source/evidence authority is provider-controlled official evidence.")
    if enabled_deterministic:
        reasons.append("Every source is enabled deterministic automation.")
    if high_signal_kind:
        reasons.append("Candidate kind maps to APW high-signal impact categories.")
    if dated_source_signal:
        reasons.append("At least one source type carries an independent dated change signal.")
    if concrete_date_signal:
        reasons.append("Candidate claim includes a bounded date signal.")
    if specific_subject_signal:
        reasons.append("Candidate claim includes a bounded provider surface, API, or model subject signal.")
    if specific_fact_signal:
        reasons.append("Candidate claim has a concrete-fact signal rather than generic change-detection wording.")
    if no_duplicates:
        reasons.append("No duplicate candidate id or dedupe key was found in this review window.")

    canonical_event_hints = None
    if readiness in {"auto_promotion_eligible", "needs_source_owner_review"} and candidate_kind in KNOWN_CANDIDATE_KINDS:
        canonical_event_hints = {
            "event_kind": candidate_kind,
            "provider_refs": provider_refs,
            "source_authorities": _source_authorities(sources),
            "source_types": _source_types(sources),
            "impact_kinds": _impact_kinds(candidate_kind),
            "evidence_refs": evidence_summaries,
        }

    return {
        "candidate_id": candidate_id,
        "path": _safe_path(candidate_file.path, root),
        "candidate_kind": candidate_kind,
        "source_keys": source_keys,
        "provider_refs": provider_refs,
        "dedupe_key": dedupe_key,
        "readiness": readiness,
        "recommendation": recommendation,
        "score": _flag_score(flags),
        "flags": flags,
        "reasons": sorted(set(reasons)),
        "promotion_blockers": sorted(set([*duplicate_blockers, *critical_blockers, *review_blockers])),
        "canonical_event_hints": canonical_event_hints,
        "evidence_refs": evidence_summaries,
        "claim_text": {
            "included": False,
            "policy": "claim_text is omitted from promotion-readiness reports",
            "sha256": claim_text_hash,
            "char_count": len(claim_text) if isinstance(claim_text, str) else 0,
            "prompt_like": not prompt_safe,
        },
    }


def build_promotion_readiness_report(
    candidate_files: list[CandidateFile],
    sources: list[SourceDescriptor],
    *,
    root: Path | None,
    created_at: str,
) -> dict[str, Any]:
    require_rfc3339_date_time(created_at, "created_at")
    sources_by_key = {source.key: source for source in sources}
    dedupe_counts = Counter(
        candidate_file.payload.get("dedupe_key")
        for candidate_file in candidate_files
        if isinstance(candidate_file.payload.get("dedupe_key"), str)
    )
    candidate_id_counts = Counter(
        candidate_file.payload.get("id")
        for candidate_file in candidate_files
        if isinstance(candidate_file.payload.get("id"), str)
    )
    candidate_reports = [
        _report_candidate(
            candidate_file,
            root=root,
            sources_by_key=sources_by_key,
            dedupe_counts=dedupe_counts,
            candidate_id_counts=candidate_id_counts,
        )
        for candidate_file in candidate_files
    ]
    readiness_counts = Counter(item["readiness"] for item in candidate_reports)
    recommendation_counts = Counter(item["recommendation"] for item in candidate_reports)
    return {
        "schema_version": PROMOTION_READINESS_REPORT_SCHEMA_VERSION,
        "created_at": created_at,
        "candidate_count": len(candidate_reports),
        "policy": {
            "authority": "advisory_only",
            "provider_controlled_authorities": sorted(PROVIDER_CONTROLLED_AUTHORITIES),
            "high_signal_kinds": sorted(HIGH_SIGNAL_KINDS),
            "dated_source_types": sorted(DATED_SOURCE_TYPES),
            "dated_parser_names": sorted(DATED_PARSER_NAMES),
            "forbidden_authority": [
                "merge_pull_request",
                "publish_provider_event",
                "write_data_events",
                "create_or_push_release_tag",
                "request_oidc_token",
                "read_release_token",
            ],
        },
        "summary": {
            "readiness_counts": dict(sorted(readiness_counts.items())),
            "recommendation_counts": dict(sorted(recommendation_counts.items())),
            "promotion_ready_candidate_ids": sorted(
                item["candidate_id"]
                for item in candidate_reports
                if item["readiness"] == "auto_promotion_eligible"
            ),
        },
        "candidates": sorted(candidate_reports, key=lambda item: item["candidate_id"]),
    }
