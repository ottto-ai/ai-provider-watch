from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json

SCHEMA_VERSION = "apw.source_refresh_review_gate.v0"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def _candidate_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    raw_count = value.get("candidate_count", 0)
    if isinstance(raw_count, bool):
        return 0
    if isinstance(raw_count, int):
        return max(raw_count, 0)
    return 0


def _count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(count, bool) or not isinstance(count, int):
            continue
        result[key] = max(count, 0)
    return dict(sorted(result.items()))


def _quality_summary(quality_report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(quality_report, dict):
        return {
            "candidate_count": None,
            "quality_tier_counts": {},
            "recommended_action_counts": {},
            "classified_candidate_count": 0,
            "high_value_candidate_count": 0,
            "reviewable_candidate_count": 0,
            "has_reviewable_candidates": None,
        }
    summary = quality_report.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    action_counts = _count_map(summary.get("recommended_action_counts"))
    tier_counts = _count_map(summary.get("quality_tier_counts"))
    high_value_ids = _string_list(summary.get("high_value_candidate_ids"))
    reviewable_ids = _string_list(summary.get("reviewable_candidate_ids"))
    promotable_action_count = sum(
        action_counts.get(action, 0)
        for action in ("promote", "needs_human_review")
    )
    reviewable_tier_count = sum(tier_counts.get(tier, 0) for tier in ("high_value", "reviewable"))
    reviewable_candidate_count = max(len(reviewable_ids), promotable_action_count, reviewable_tier_count)
    classified_candidate_count = max(sum(action_counts.values()), sum(tier_counts.values()))
    return {
        "candidate_count": _candidate_count(quality_report),
        "quality_tier_counts": tier_counts,
        "recommended_action_counts": action_counts,
        "classified_candidate_count": classified_candidate_count,
        "high_value_candidate_count": len(high_value_ids),
        "reviewable_candidate_count": reviewable_candidate_count,
        "has_reviewable_candidates": reviewable_candidate_count > 0,
    }


def build_source_refresh_review_gate(
    observation_bundle: dict[str, Any],
    candidate_generation: dict[str, Any],
    candidate_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    changed_source_keys = _string_list(observation_bundle.get("changed_source_keys"))
    candidate_count = _candidate_count(candidate_generation)
    quality = _quality_summary(candidate_quality)
    quality_candidate_count = quality["candidate_count"]
    quality_count_matches = (
        quality_candidate_count is None
        or not candidate_count
        or quality_candidate_count == candidate_count
    )
    has_reviewable_candidates = quality["has_reviewable_candidates"]
    quality_classifies_all_candidates = (
        candidate_count > 0
        and isinstance(quality["classified_candidate_count"], int)
        and quality["classified_candidate_count"] >= candidate_count
    )
    suppress_non_reviewable_candidates = (
        candidate_count > 0
        and candidate_quality is not None
        and quality_count_matches
        and quality_classifies_all_candidates
        and has_reviewable_candidates is False
    )
    review_candidate_count = 0 if suppress_non_reviewable_candidates else candidate_count
    review_needed = bool(changed_source_keys or review_candidate_count)
    if candidate_count and not quality_count_matches:
        recommendation = "open_candidate_review_pr"
        reason = "candidate_quality_count_mismatch"
    elif review_candidate_count:
        recommendation = "open_candidate_review_pr"
        reason = "reviewable_source_or_candidate_changes"
    elif suppress_non_reviewable_candidates and changed_source_keys:
        recommendation = "open_source_state_refresh_pr"
        reason = "source_fingerprint_changes_with_only_non_reviewable_candidates"
    elif suppress_non_reviewable_candidates:
        recommendation = "skip_candidate_review_pr"
        reason = "only_non_reviewable_candidates_without_source_changes"
    elif changed_source_keys:
        recommendation = "open_source_state_refresh_pr"
        reason = "source_fingerprint_changes_without_candidates"
    else:
        recommendation = "skip_candidate_review_pr"
        reason = "no_changed_sources_or_candidates"

    return {
        "schema_version": SCHEMA_VERSION,
        "review_needed": review_needed,
        "recommendation": recommendation,
        "reason": reason,
        "changed_source_count": len(changed_source_keys),
        "changed_source_keys": changed_source_keys,
        "candidate_count": candidate_count,
        "review_candidate_count": review_candidate_count,
        "suppressed_candidate_count": candidate_count - review_candidate_count,
        "candidate_quality_candidate_count": quality_candidate_count,
        "candidate_quality_tier_counts": quality["quality_tier_counts"],
        "candidate_quality_action_counts": quality["recommended_action_counts"],
        "high_value_candidate_count": quality["high_value_candidate_count"],
        "reviewable_candidate_count": quality["reviewable_candidate_count"],
    }


def build_source_refresh_review_gate_from_files(
    observations_path: Path,
    candidate_generation_path: Path,
    candidate_quality_path: Path | None = None,
) -> dict[str, Any]:
    observation_bundle = read_json(observations_path)
    candidate_generation = read_json(candidate_generation_path)
    candidate_quality = read_json(candidate_quality_path) if candidate_quality_path is not None else None
    if not isinstance(observation_bundle, dict):
        observation_bundle = {}
    if not isinstance(candidate_generation, dict):
        candidate_generation = {}
    if not isinstance(candidate_quality, dict):
        candidate_quality = None
    return build_source_refresh_review_gate(observation_bundle, candidate_generation, candidate_quality)


def render_source_refresh_review_gate_summary(gate: dict[str, Any]) -> str:
    changed_source_keys = gate.get("changed_source_keys", [])
    changed_list = ", ".join(changed_source_keys) if changed_source_keys else "none"
    return "\n".join(
        [
            f"review_needed: {str(bool(gate.get('review_needed'))).lower()}",
            f"recommendation: {gate.get('recommendation')}",
            f"reason: {gate.get('reason')}",
            f"changed_source_count: {gate.get('changed_source_count', 0)}",
            f"changed_source_keys: {changed_list}",
            f"candidate_count: {gate.get('candidate_count', 0)}",
            f"review_candidate_count: {gate.get('review_candidate_count', gate.get('candidate_count', 0))}",
            f"suppressed_candidate_count: {gate.get('suppressed_candidate_count', 0)}",
        ]
    ) + "\n"


def write_github_output(path: Path, gate: dict[str, Any]) -> None:
    lines = [
        f"review_needed={str(bool(gate.get('review_needed'))).lower()}",
        f"recommendation={gate.get('recommendation')}",
        f"reason={gate.get('reason')}",
        f"changed_source_count={gate.get('changed_source_count', 0)}",
        f"candidate_count={gate.get('candidate_count', 0)}",
        f"review_candidate_count={gate.get('review_candidate_count', gate.get('candidate_count', 0))}",
        f"suppressed_candidate_count={gate.get('suppressed_candidate_count', 0)}",
    ]
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
