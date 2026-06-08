from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_provider_watch.core.io import event_paths, read_json
from ai_provider_watch.core.temporal import require_rfc3339_date_time
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.promotion import (
    HIGH_SIGNAL_KINDS,
    KIND_TO_IMPACT_KINDS,
    PROVIDER_CONTROLLED_AUTHORITIES,
    build_promotion_readiness_report,
)
from ai_provider_watch.pipeline.review_pr import CandidateFile
from ai_provider_watch.sources.registry import SourceDescriptor

CANDIDATE_QUALITY_REPORT_SCHEMA_VERSION = "apw.candidate_quality_report.v0"

GENERIC_REVIEW_MARKERS = (
    "changed and needs maintainer review",
    "documentation changed",
    "docs changed",
    "feed changed",
    "needs maintainer review",
    "page changed",
    "source changed",
    "supported model list",
)

ARTICLE_PATH_MARKERS = (
    "/blog/",
    "/changelog",
    "/docs/changelog",
    "/news/",
    "/release",
    "/releases/",
    "/what-s-new",
    "/whats-new",
)

MULTI_ENTRY_SOURCE_KEYS = {
    "azure_openai.whats_new",
    "google.gemini_changelog",
}

OPENAI_NEWS_DIRECT_CHANGE_URL_TERMS = (
    "api",
    "aws",
    "chatgpt",
    "codex",
    "deprecat",
    "gpt",
    "model",
    "o3",
    "o4",
    "pricing",
    "realtime",
    "responses",
    "retire",
    "sora",
    "status",
)

AWS_BEDROCK_ADJACENT_SLUG_MARKERS = (
    "aws-config-new-resource-types",
    "multi-turn-reinforcement-learning-on-sagemaker-ai",
)

MODEL_OR_SURFACE_PATTERN = re.compile(
    r"\b(?:agentcore|api|azure-openai|bedrock|claude(?:-[a-z0-9.-]+)?|codex|computer-use|"
    r"gemini(?:-[a-z0-9.-]+)?|gpt(?:-[a-z0-9.-]+)?|model|nova(?:-[a-z0-9.-]+)?|"
    r"openai|realtime|responses-api|sdk|vertex-ai)\b",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"\b[0-9]{4}-[0-9]{2}(?:-[0-9]{2})?\b"
    r"|\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|"
    r"sep|sept|september|oct|october|nov|november|dec|december)\s+[0-9]{1,2},\s+[0-9]{4}\b",
    re.IGNORECASE,
)

ACTION_PATTERN = re.compile(
    r"\b(?:announced|available|availability|billing|cache|caching|cost|deprecated|deprecation|"
    r"incident|launched|launch|released|reports|retire|retired|retirement|shutdown|status|token)\b",
    re.IGNORECASE,
)


def _safe_claim(candidate: dict[str, Any]) -> str:
    claim = candidate.get("claim_text")
    if not isinstance(claim, str) or contains_prompt_injection_marker(claim):
        return ""
    return re.sub(r"\s+", " ", claim.strip())


def _quality_dimensions(
    candidate: dict[str, Any],
    readiness: dict[str, Any],
    sources: list[SourceDescriptor],
    duplicate_event_ids: list[str],
) -> dict[str, bool]:
    claim_text = _safe_claim(candidate)
    evidence_refs = candidate.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    parser = candidate.get("parser")
    parser_name = parser.get("name") if isinstance(parser, dict) else None
    evidence_urls = [
        evidence.get("url")
        for evidence in evidence_refs
        if isinstance(evidence, dict) and isinstance(evidence.get("url"), str)
    ]
    has_selector_or_snapshot = any(
        isinstance(evidence, dict)
        and (isinstance(evidence.get("selector"), str) or isinstance(evidence.get("snapshot_ref"), str))
        for evidence in evidence_refs
    )
    article_like_evidence = has_selector_or_snapshot or any(
        any(marker in url.lower() for marker in ARTICLE_PATH_MARKERS)
        for url in evidence_urls
    )
    source_authorities = {source.authority for source in sources}
    flags = readiness.get("flags", {}) if isinstance(readiness.get("flags"), dict) else {}
    not_generic = bool(claim_text) and not any(marker in claim_text.lower() for marker in GENERIC_REVIEW_MARKERS)
    source_impact_hints = {
        hint
        for source in sources
        for hint in source.impact_hints
        if isinstance(hint, str)
    }
    candidate_kind = candidate.get("candidate_kind")
    return {
        "provider_controlled_official": bool(source_authorities)
        and source_authorities <= PROVIDER_CONTROLLED_AUTHORITIES
        and bool(flags.get("official_provider_controlled")),
        "enabled_deterministic_source": bool(flags.get("enabled_deterministic")),
        "high_signal_kind": isinstance(candidate_kind, str) and candidate_kind in HIGH_SIGNAL_KINDS,
        "developer_impact_hint": isinstance(candidate_kind, str)
        and (candidate_kind in HIGH_SIGNAL_KINDS or candidate_kind in source_impact_hints),
        "dated_change_signal": bool(flags.get("dated_source_signal")) and bool(DATE_PATTERN.search(claim_text)),
        "specific_subject_signal": bool(MODEL_OR_SURFACE_PATTERN.search(claim_text))
        and bool(flags.get("specific_subject_signal")),
        "specific_action_signal": bool(ACTION_PATTERN.search(claim_text)),
        "specific_fact_signal": bool(flags.get("specific_fact_signal")),
        "article_or_selector_evidence": article_like_evidence,
        "parser_specific": isinstance(parser_name, str)
        and parser_name not in {"manual_review", "change_detector", "generic_change_detector"},
        "non_generic_claim": not_generic,
        "direct_apw_scope_signal": _direct_apw_scope_signal(candidate, evidence_urls),
        "no_promotion_blockers": not readiness.get("promotion_blockers"),
        "not_already_reviewed": not duplicate_event_ids,
    }


def _weighted_score(dimensions: dict[str, bool]) -> int:
    weights = {
        "provider_controlled_official": 12,
        "enabled_deterministic_source": 8,
        "high_signal_kind": 10,
        "developer_impact_hint": 8,
        "dated_change_signal": 12,
        "specific_subject_signal": 10,
        "specific_action_signal": 8,
        "specific_fact_signal": 12,
        "article_or_selector_evidence": 8,
        "parser_specific": 6,
        "non_generic_claim": 4,
        "direct_apw_scope_signal": 8,
        "no_promotion_blockers": 2,
        "not_already_reviewed": 3,
    }
    score = sum(weight for key, weight in weights.items() if dimensions.get(key))
    return min(score, 100)


def _tier(score: int, readiness: str, dimensions: dict[str, bool]) -> str:
    if readiness == "duplicate_or_superseded" or not dimensions.get("not_already_reviewed", True):
        return "duplicate"
    if readiness == "not_ready":
        return "blocked"
    if (
        not dimensions.get("specific_fact_signal")
        or not dimensions.get("non_generic_claim")
        or not dimensions.get("direct_apw_scope_signal", True)
    ):
        return "low_signal"
    if score >= 85 and dimensions.get("specific_fact_signal") and dimensions.get("article_or_selector_evidence"):
        return "high_value"
    if score >= 65:
        return "reviewable"
    return "low_signal"


def _recommended_action(tier: str, readiness: str) -> str:
    if tier == "duplicate":
        return "duplicate"
    if tier == "high_value" and readiness == "auto_promotion_eligible":
        return "promote"
    if tier == "low_signal":
        return "reject"
    return "needs_human_review"


def _reasons(dimensions: dict[str, bool], tier: str) -> list[str]:
    reasons: list[str] = []
    if dimensions["provider_controlled_official"]:
        reasons.append("Evidence is provider-controlled and official.")
    if dimensions["dated_change_signal"]:
        reasons.append("Candidate has a bounded date signal.")
    if dimensions["specific_subject_signal"]:
        reasons.append("Candidate names a concrete provider surface, model, API, or app subject.")
    if dimensions["specific_action_signal"]:
        reasons.append("Candidate includes a developer-relevant action signal.")
    if dimensions["article_or_selector_evidence"]:
        reasons.append("Evidence points to a specific article, changelog section, snapshot, or selector.")
    if not dimensions["not_already_reviewed"]:
        reasons.append("Candidate evidence is already covered by a reviewed event.")
    if not dimensions.get("direct_apw_scope_signal", True):
        reasons.append("Candidate looks adjacent to APW scope rather than a direct provider-impact change.")
    if tier == "low_signal":
        reasons.append("Candidate is too broad or generic for direct source-owner promotion.")
    return reasons


def _blockers(dimensions: dict[str, bool], readiness: dict[str, Any]) -> list[str]:
    blockers = [
        blocker
        for blocker in readiness.get("promotion_blockers", [])
        if isinstance(blocker, str)
    ]
    if not dimensions["provider_controlled_official"]:
        blockers.append("Quality gate requires official provider-controlled evidence.")
    if not dimensions["dated_change_signal"]:
        blockers.append("Quality gate requires a bounded official date signal.")
    if not dimensions["specific_fact_signal"]:
        blockers.append("Quality gate requires a concrete fact rather than generic change detection.")
    if not dimensions["article_or_selector_evidence"]:
        blockers.append("Quality gate prefers article, changelog, selector, or snapshot-scoped evidence.")
    if not dimensions.get("direct_apw_scope_signal", True):
        blockers.append("Quality gate requires a direct APW impact signal, not only a customer story or adjacent-service mention.")
    if not dimensions["not_already_reviewed"]:
        blockers.append("Candidate evidence URL already appears in reviewed event data.")
    return sorted(set(blockers))


def _normal_url(url: Any) -> str | None:
    if not isinstance(url, str) or contains_prompt_injection_marker(url):
        return None
    return url.rstrip("/")


def _is_multi_entry_evidence(evidence: dict[str, Any]) -> bool:
    source_key = evidence.get("source_key")
    if source_key in MULTI_ENTRY_SOURCE_KEYS:
        return True
    url = _normal_url(evidence.get("url"))
    if url is None:
        return False
    path = urlparse(url).path.lower()
    return any(marker in path for marker in ("/changelog", "/whats-new"))


def _evidence_identity(evidence: dict[str, Any]) -> str | None:
    url = _normal_url(evidence.get("url"))
    if url is None:
        return None
    if not _is_multi_entry_evidence(evidence):
        return url
    selector = evidence.get("selector")
    snapshot_ref = evidence.get("snapshot_ref")
    if isinstance(selector, str) and not contains_prompt_injection_marker(selector):
        return f"{url}#selector={selector}"
    if isinstance(snapshot_ref, str) and not contains_prompt_injection_marker(snapshot_ref):
        return f"{url}#snapshot={snapshot_ref}"
    return url


def _direct_apw_scope_signal(candidate: dict[str, Any], evidence_urls: list[str]) -> bool:
    source_keys = candidate.get("source_keys", [])
    source_key_values = {item for item in source_keys if isinstance(item, str)} if isinstance(source_keys, list) else set()
    candidate_kind = candidate.get("candidate_kind")
    normalized_urls = [url.lower() for url in evidence_urls]

    if "openai.news" in source_key_values and candidate_kind == "workflow_behavior_change":
        return any(
            term in url
            for url in normalized_urls
            for term in OPENAI_NEWS_DIRECT_CHANGE_URL_TERMS
        )

    if "aws_bedrock.whats_new" in source_key_values:
        if any(marker in url for url in normalized_urls for marker in AWS_BEDROCK_ADJACENT_SLUG_MARKERS):
            return False

    return True


def _reviewed_events_by_evidence(root: Path | None) -> dict[str, list[str]]:
    if root is None:
        return {}
    reviewed: dict[str, list[str]] = {}
    for path in event_paths(root):
        event = read_json(path)
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            continue
        for evidence in event.get("evidence_refs", []):
            if not isinstance(evidence, dict):
                continue
            identity = _evidence_identity(evidence)
            if identity is None:
                continue
            reviewed.setdefault(identity, []).append(event["id"])
    return {identity: sorted(set(event_ids)) for identity, event_ids in reviewed.items()}


def _duplicate_event_ids(candidate: dict[str, Any], reviewed_by_evidence: dict[str, list[str]]) -> list[str]:
    event_ids: set[str] = set()
    evidence_refs = candidate.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        return []
    for evidence in evidence_refs:
        if not isinstance(evidence, dict):
            continue
        identity = _evidence_identity(evidence)
        if identity is None:
            continue
        event_ids.update(reviewed_by_evidence.get(identity, []))
    return sorted(event_ids)


def _source_descriptors(source_keys: list[str], sources_by_key: dict[str, SourceDescriptor]) -> list[SourceDescriptor]:
    return [sources_by_key[key] for key in source_keys if key in sources_by_key]


def _candidate_kind(candidate: dict[str, Any]) -> str:
    value = candidate.get("candidate_kind")
    return value if isinstance(value, str) else "<invalid-kind>"


def _quality_row(
    candidate_file: CandidateFile,
    *,
    root: Path | None,
    sources_by_key: dict[str, SourceDescriptor],
    readiness_by_id: dict[str, dict[str, Any]],
    reviewed_by_evidence: dict[str, list[str]],
) -> dict[str, Any]:
    candidate = candidate_file.payload
    candidate_id = candidate.get("id") if isinstance(candidate.get("id"), str) else "<invalid-id>"
    source_keys = [
        item
        for item in candidate.get("source_keys", [])
        if isinstance(item, str)
    ] if isinstance(candidate.get("source_keys"), list) else []
    readiness = readiness_by_id.get(candidate_id, {})
    sources = _source_descriptors(source_keys, sources_by_key)
    duplicate_event_ids = _duplicate_event_ids(candidate, reviewed_by_evidence)
    dimensions = _quality_dimensions(candidate, readiness, sources, duplicate_event_ids)
    score = _weighted_score(dimensions)
    readiness_value = readiness.get("readiness") if isinstance(readiness.get("readiness"), str) else "not_ready"
    tier = _tier(score, readiness_value, dimensions)
    action = _recommended_action(tier, readiness_value)
    candidate_path = candidate_file.path
    if root is not None:
        try:
            rendered_path = candidate_path.relative_to(root).as_posix()
        except ValueError:
            rendered_path = candidate_path.as_posix()
    else:
        rendered_path = candidate_path.as_posix()
    event_kind = _candidate_kind(candidate)
    return {
        "candidate_id": candidate_id,
        "path": rendered_path,
        "candidate_kind": event_kind,
        "source_keys": sorted(source_keys),
        "provider_refs": sorted(
            item
            for item in candidate.get("provider_refs", [])
            if isinstance(item, str)
        ) if isinstance(candidate.get("provider_refs"), list) else [],
        "quality_tier": tier,
        "recommended_action": action,
        "score": score,
        "dimensions": dimensions,
        "reasons": _reasons(dimensions, tier),
        "quality_blockers": _blockers(dimensions, readiness),
        "promotion_readiness": readiness_value,
        "duplicate_event_ids": duplicate_event_ids,
        "canonical_event_hints": {
            "event_kind": event_kind,
            "provider_refs": sorted(
                item
                for item in candidate.get("provider_refs", [])
                if isinstance(item, str)
            ) if isinstance(candidate.get("provider_refs"), list) else [],
            "source_authorities": sorted({source.authority for source in sources if source.authority}),
            "source_types": sorted({source.source_type for source in sources if source.source_type}),
            "impact_kinds": KIND_TO_IMPACT_KINDS.get(event_kind, ["unknown"]),
            "evidence_refs": readiness.get("evidence_refs", []),
        } if action in {"promote", "needs_human_review"} else None,
    }


def build_candidate_quality_report(
    candidate_files: list[CandidateFile],
    sources: list[SourceDescriptor],
    *,
    root: Path | None,
    created_at: str,
    promotion_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_rfc3339_date_time(created_at, "created_at")
    if promotion_report is None:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
    readiness_by_id = {
        candidate["candidate_id"]: candidate
        for candidate in promotion_report.get("candidates", [])
        if isinstance(candidate, dict) and isinstance(candidate.get("candidate_id"), str)
    }
    sources_by_key = {source.key: source for source in sources}
    reviewed_by_evidence = _reviewed_events_by_evidence(root)
    rows = [
        _quality_row(
            candidate_file,
            root=root,
            sources_by_key=sources_by_key,
            readiness_by_id=readiness_by_id,
            reviewed_by_evidence=reviewed_by_evidence,
        )
        for candidate_file in candidate_files
    ]
    tier_counts = Counter(row["quality_tier"] for row in rows)
    action_counts = Counter(row["recommended_action"] for row in rows)
    return {
        "schema_version": CANDIDATE_QUALITY_REPORT_SCHEMA_VERSION,
        "created_at": created_at,
        "candidate_count": len(rows),
        "policy": {
            "authority": "advisory_only",
            "purpose": "Rank review-only candidates by developer relevance and source-owner promotion readiness.",
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
            "quality_tier_counts": dict(sorted(tier_counts.items())),
            "recommended_action_counts": dict(sorted(action_counts.items())),
            "high_value_candidate_ids": sorted(
                row["candidate_id"] for row in rows if row["quality_tier"] == "high_value"
            ),
            "reviewable_candidate_ids": sorted(
                row["candidate_id"] for row in rows if row["quality_tier"] in {"high_value", "reviewable"}
            ),
        },
        "candidates": sorted(rows, key=lambda row: row["candidate_id"]),
    }
