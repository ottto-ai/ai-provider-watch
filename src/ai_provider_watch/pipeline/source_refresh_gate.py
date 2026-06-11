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


def build_source_refresh_review_gate(
    observation_bundle: dict[str, Any],
    candidate_generation: dict[str, Any],
) -> dict[str, Any]:
    changed_source_keys = _string_list(observation_bundle.get("changed_source_keys"))
    candidate_count = _candidate_count(candidate_generation)
    review_needed = bool(changed_source_keys or candidate_count)
    if candidate_count:
        recommendation = "open_candidate_review_pr"
        reason = "reviewable_source_or_candidate_changes"
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
    }


def build_source_refresh_review_gate_from_files(
    observations_path: Path,
    candidate_generation_path: Path,
) -> dict[str, Any]:
    observation_bundle = read_json(observations_path)
    candidate_generation = read_json(candidate_generation_path)
    if not isinstance(observation_bundle, dict):
        observation_bundle = {}
    if not isinstance(candidate_generation, dict):
        candidate_generation = {}
    return build_source_refresh_review_gate(observation_bundle, candidate_generation)


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
        ]
    ) + "\n"


def write_github_output(path: Path, gate: dict[str, Any]) -> None:
    lines = [
        f"review_needed={str(bool(gate.get('review_needed'))).lower()}",
        f"recommendation={gate.get('recommendation')}",
        f"reason={gate.get('reason')}",
        f"changed_source_count={gate.get('changed_source_count', 0)}",
        f"candidate_count={gate.get('candidate_count', 0)}",
    ]
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
