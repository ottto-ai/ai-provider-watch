from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.candidates import KNOWN_CANDIDATE_KINDS

CANDIDATE_ID_PATTERN = re.compile(r"^candidate-[a-z0-9][a-z0-9-]*-[a-f0-9]{16}$")
SOURCE_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*[a-z0-9]$|^[a-z0-9]$")
PROVIDER_REF_PATTERN = re.compile(r"^provider:[a-z0-9][a-z0-9_-]*$")
RELATIVE_JSON_PATH_PATTERN = re.compile(r"^(?:[A-Za-z0-9._+-]+/)*[A-Za-z0-9._+-]+\.json$")
FINGERPRINT_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class CandidateFile:
    path: Path
    payload: dict[str, Any]


def read_candidate_files(candidate_dir: Path) -> list[CandidateFile]:
    if not candidate_dir.exists():
        return []
    candidates: list[CandidateFile] = []
    for path in sorted(candidate_dir.rglob("*.json")):
        payload = read_json(path)
        candidates.append(
            CandidateFile(
                path=path,
                payload=payload if isinstance(payload, dict) else {"id": "<invalid>"},
            )
        )
    return candidates


def _observations(bundle: Any) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    observations = bundle.get("observations", [])
    return [item for item in observations if isinstance(item, dict)] if isinstance(observations, list) else []


def _changed_source_keys(bundle: Any, observations: list[dict[str, Any]]) -> list[str]:
    if isinstance(bundle, dict):
        changed_source_keys = bundle.get("changed_source_keys", [])
        if isinstance(changed_source_keys, list):
            return sorted({item for item in changed_source_keys if isinstance(item, str)})
    return sorted(
        {
            str(observation.get("source_key"))
            for observation in observations
            if observation.get("changed") is True and observation.get("source_key")
        }
    )


def _candidate_path(path: Path, root: Path) -> str:
    try:
        rendered = path.relative_to(root).as_posix()
    except ValueError:
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


def _safe_values(value: Any, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, list):
        return "<invalid>"
    safe = [_safe_scalar(item, pattern, "<invalid>") for item in value]
    return ", ".join(safe) if safe else "<empty>"


def _safe_candidate_kind(value: Any) -> str:
    if not isinstance(value, str):
        return "<invalid-kind>"
    if contains_prompt_injection_marker(value):
        return "<invalid-kind>"
    return value if value in KNOWN_CANDIDATE_KINDS else "<invalid-kind>"


def _safe_source_key(value: Any) -> str:
    return _safe_scalar(value, SOURCE_KEY_PATTERN, "<invalid-source>")


def _safe_fingerprint_prefix(value: Any) -> str:
    if not isinstance(value, str) or not FINGERPRINT_PATTERN.fullmatch(value):
        return "`<invalid>`"
    return f"`{value[:12]}`"


def _safe_http_status(value: Any) -> str:
    if isinstance(value, int) and 100 <= value <= 599:
        return str(value)
    if isinstance(value, str) and value.isdigit():
        status = int(value)
        if 100 <= status <= 599:
            return value
    return "<invalid>"


def _safe_validation_output(value: str) -> str:
    output = value.strip() or "Validation output was not supplied."
    if contains_prompt_injection_marker(output):
        return "Validation output omitted because it contained prompt-like text."
    return output


def _candidate_rows(candidate_files: list[CandidateFile], root: Path) -> list[str]:
    rows: list[str] = []
    for candidate_file in candidate_files:
        candidate = candidate_file.payload
        source_keys = candidate.get("source_keys", [])
        provider_refs = candidate.get("provider_refs", [])
        evidence_refs = candidate.get("evidence_refs", [])
        rows.append(
            "| "
            + " | ".join(
                [
                    _candidate_path(candidate_file.path, root),
                    _safe_scalar(candidate.get("id"), CANDIDATE_ID_PATTERN, "<invalid-id>"),
                    _safe_candidate_kind(candidate.get("candidate_kind")),
                    _safe_values(source_keys, SOURCE_KEY_PATTERN),
                    _safe_values(provider_refs, PROVIDER_REF_PATTERN),
                    str(len(evidence_refs) if isinstance(evidence_refs, list) else 0),
                ]
            )
            + " |"
        )
    return rows


def _promotion_rows(promotion_report: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    candidates = promotion_report.get("candidates", [])
    if not isinstance(candidates, list):
        return rows
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        blockers = candidate.get("promotion_blockers", [])
        rows.append(
            "| "
            + " | ".join(
                [
                    _safe_scalar(candidate.get("candidate_id"), CANDIDATE_ID_PATTERN, "<invalid-id>"),
                    _safe_scalar(
                        candidate.get("readiness"),
                        re.compile(r"^[a-z_]{3,40}$"),
                        "<invalid-readiness>",
                    ),
                    _safe_scalar(
                        candidate.get("recommendation"),
                        re.compile(r"^[a-z_]{3,40}$"),
                        "<invalid-recommendation>",
                    ),
                    str(candidate.get("score") if isinstance(candidate.get("score"), int) else 0),
                    str(len(blockers) if isinstance(blockers, list) else 0),
                ]
            )
            + " |"
        )
    return rows


def _quality_rows(quality_report: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    candidates = quality_report.get("candidates", [])
    if not isinstance(candidates, list):
        return rows
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        blockers = candidate.get("quality_blockers", [])
        rows.append(
            "| "
            + " | ".join(
                [
                    _safe_scalar(candidate.get("candidate_id"), CANDIDATE_ID_PATTERN, "<invalid-id>"),
                    _safe_scalar(
                        candidate.get("quality_tier"),
                        re.compile(r"^[a-z_]{3,40}$"),
                        "<invalid-tier>",
                    ),
                    _safe_scalar(
                        candidate.get("recommended_action"),
                        re.compile(r"^[a-z_]{3,40}$"),
                        "<invalid-action>",
                    ),
                    str(candidate.get("score") if isinstance(candidate.get("score"), int) else 0),
                    str(len(blockers) if isinstance(blockers, list) else 0),
                ]
            )
            + " |"
        )
    return rows


def build_review_pr_body(
    observation_bundle: Any,
    candidate_files: list[CandidateFile],
    *,
    root: Path,
    validation_output: str = "",
    promotion_report: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
) -> str:
    observations = _observations(observation_bundle)
    changed_source_keys = _changed_source_keys(observation_bundle, observations)
    candidate_count_by_source: Counter[str] = Counter()
    candidate_count_by_kind: Counter[str] = Counter()
    for candidate_file in candidate_files:
        candidate = candidate_file.payload
        for source_key in candidate.get("source_keys", []):
            if isinstance(source_key, str):
                candidate_count_by_source[_safe_source_key(source_key)] += 1
        candidate_count_by_kind[_safe_candidate_kind(candidate.get("candidate_kind"))] += 1

    lines = [
        "# Candidate Review",
        "",
        "This draft PR was generated by the deterministic official-source refresh workflow.",
        "Provider source text is untrusted data; this body intentionally omits raw source text and candidate claim text.",
        "",
        "## Summary",
        "",
        f"- Observation count: {len(observations)}",
        f"- Changed source keys: {len(changed_source_keys)}",
        f"- Candidate files: {len(candidate_files)}",
        f"- Candidate kinds: {_render_counter(candidate_count_by_kind)}",
        "",
        "## Changed Sources",
        "",
    ]
    if changed_source_keys:
        lines.extend([f"- `{_safe_source_key(source_key)}`" for source_key in changed_source_keys])
    else:
        lines.append("- None reported.")

    lines.extend(
        [
            "",
            "## Observation Summary",
            "",
            "| Source | Changed | HTTP | Candidate claims | Errors | Fingerprint |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for observation in observations:
        source_key = _safe_source_key(observation.get("source_key"))
        claims = observation.get("candidate_claims", [])
        errors = observation.get("errors", [])
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{source_key}`",
                    "yes" if observation.get("changed") is True else "no",
                    _safe_http_status(observation.get("http_status")),
                    str(len(claims) if isinstance(claims, list) else 0),
                    str(len(errors) if isinstance(errors, list) else 0),
                    _safe_fingerprint_prefix(observation.get("fingerprint")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Candidate Files",
            "",
        ]
    )
    if candidate_files:
        lines.extend(
            [
                "| Path | ID | Kind | Sources | Providers | Evidence refs |",
                "| --- | --- | --- | --- | --- | ---: |",
                *_candidate_rows(candidate_files, root),
            ]
        )
    else:
        lines.append("No candidate files were generated in this run.")

    lines.extend(["", "## Promotion Readiness", ""])
    if promotion_report:
        summary = promotion_report.get("summary", {})
        readiness_counts = summary.get("readiness_counts", {}) if isinstance(summary, dict) else {}
        recommendation_counts = summary.get("recommendation_counts", {}) if isinstance(summary, dict) else {}
        lines.extend(
            [
                "This is advisory source-owner context. It does not publish events, merge PRs, create tags, request OIDC, or read release tokens.",
                "",
                f"- Readiness: {_render_mapping(readiness_counts)}",
                f"- Recommendations: {_render_mapping(recommendation_counts)}",
                "",
            ]
        )
        rows = _promotion_rows(promotion_report)
        if rows:
            lines.extend(
                [
                    "| Candidate | Readiness | Recommendation | Score | Blockers |",
                    "| --- | --- | --- | ---: | ---: |",
                    *rows,
                    "",
                ]
            )
        else:
            lines.append("No promotion-readiness rows were available.")
    else:
        lines.append("Promotion-readiness report was not supplied.")

    lines.extend(["", "## Candidate Quality", ""])
    if quality_report:
        summary = quality_report.get("summary", {})
        quality_tier_counts = summary.get("quality_tier_counts", {}) if isinstance(summary, dict) else {}
        recommended_action_counts = summary.get("recommended_action_counts", {}) if isinstance(summary, dict) else {}
        lines.extend(
            [
                "This ranks review-only candidates by developer relevance, evidence specificity, and source-owner decision quality. It is advisory and cannot publish events.",
                "",
                f"- Quality tiers: {_render_mapping(quality_tier_counts)}",
                f"- Recommended actions: {_render_mapping(recommended_action_counts)}",
                "",
            ]
        )
        rows = _quality_rows(quality_report)
        if rows:
            lines.extend(
                [
                    "| Candidate | Quality tier | Recommended action | Score | Blockers |",
                    "| --- | --- | --- | ---: | ---: |",
                    *rows,
                    "",
                ]
            )
        else:
            lines.append("No candidate-quality rows were available.")
    else:
        lines.append("Candidate-quality report was not supplied.")

    lines.extend(
        [
            "",
            "## Validation",
            "",
            "```text",
            _safe_validation_output(validation_output),
            "```",
            "",
            "## Reviewer Checklist",
            "",
            "- [ ] Confirm source fingerprint changes are expected and official.",
            "- [ ] Review each candidate JSON file against its official evidence URL before promotion.",
            "- [ ] Keep provider prose, raw HTML, screenshots, and social/community text out of committed event data.",
            "- [ ] Promote only reviewed factual changes to `data/events/`; candidates are not published provider events.",
            "- [ ] Do not merge if candidate evidence points outside allowed domains or validation output is stale.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def _render_mapping(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    rendered: list[str] = []
    for key in sorted(value):
        count = value[key]
        if isinstance(key, str) and isinstance(count, int):
            rendered.append(f"{key}={count}")
    return ", ".join(rendered) if rendered else "none"
