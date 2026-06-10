from __future__ import annotations

from collections import Counter
from typing import Any

from ai_provider_watch.core.temporal import require_rfc3339_date_time

CANDIDATE_ACTION_QUEUE_SCHEMA_VERSION = "apw.candidate_action_queue.v0"

ACTION_ORDER = ("promote", "needs_human_review", "duplicate", "reject")

FORBIDDEN_AUTHORITY = [
    "merge_pull_request",
    "publish_provider_event",
    "write_data_events",
    "create_or_push_release_tag",
    "request_oidc_token",
    "read_release_token",
]


def _candidate_by_id(candidate_files: list[Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for candidate_file in candidate_files:
        payload = getattr(candidate_file, "payload", None)
        if isinstance(payload, dict) and isinstance(payload.get("id"), str):
            rows[payload["id"]] = payload
    return rows


def _row_by_candidate_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["candidate_id"]: row
        for row in report.get("candidates", [])
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
    }


def _evidence_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_refs = candidate.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        return []
    rows: list[dict[str, Any]] = []
    for evidence in evidence_refs:
        if not isinstance(evidence, dict):
            continue
        source_key = evidence.get("source_key")
        url = evidence.get("url")
        authority = evidence.get("authority")
        if not (isinstance(source_key, str) and isinstance(url, str) and isinstance(authority, str)):
            continue
        rows.append(
            {
                "source_key": source_key,
                "url": url,
                "authority": authority,
                "selector": evidence.get("selector") if isinstance(evidence.get("selector"), str) else None,
                "snapshot_ref": evidence.get("snapshot_ref")
                if isinstance(evidence.get("snapshot_ref"), str)
                else None,
            }
        )
    return rows


def _next_step(action: str, duplicate_event_ids: list[str]) -> str:
    if action == "promote":
        return "Verify official evidence, author ProviderEvent JSON, run candidate event-packet, then open the promotion PR."
    if action == "needs_human_review":
        return "Open the official evidence and decide whether to promote, split, reject, or mark duplicate."
    if action == "duplicate":
        if duplicate_event_ids:
            return f"Close as duplicate of {', '.join(duplicate_event_ids)}."
        return "Close as duplicate of the existing reviewed event after confirming scope."
    if action == "reject":
        return "Close as no public APW event; narrow parser/source scope if this noise will recur."
    return "Review manually."


def _queue_row(
    quality_row: dict[str, Any],
    *,
    candidate: dict[str, Any],
    readiness_row: dict[str, Any],
) -> dict[str, Any]:
    action = quality_row.get("recommended_action")
    if action not in ACTION_ORDER:
        action = "needs_human_review"
    duplicate_event_ids = [
        item for item in quality_row.get("duplicate_event_ids", []) if isinstance(item, str)
    ]
    return {
        "candidate_id": str(quality_row.get("candidate_id") or candidate.get("id") or "<invalid-id>"),
        "path": str(quality_row.get("path") or "<unknown-path>"),
        "candidate_kind": str(quality_row.get("candidate_kind") or candidate.get("candidate_kind") or "<unknown-kind>"),
        "provider_refs": [
            item for item in quality_row.get("provider_refs", []) if isinstance(item, str)
        ],
        "source_keys": [
            item for item in quality_row.get("source_keys", []) if isinstance(item, str)
        ],
        "quality_tier": str(quality_row.get("quality_tier") or "<unknown-tier>"),
        "recommended_action": action,
        "score": quality_row.get("score") if isinstance(quality_row.get("score"), int) else 0,
        "promotion_readiness": str(readiness_row.get("readiness") or quality_row.get("promotion_readiness") or "<unknown-readiness>"),
        "duplicate_event_ids": duplicate_event_ids,
        "evidence_refs": _evidence_refs(candidate),
        "next_step": _next_step(action, duplicate_event_ids),
    }


def build_candidate_action_queue(
    candidate_files: list[Any],
    *,
    created_at: str,
    promotion_report: dict[str, Any],
    quality_report: dict[str, Any],
) -> dict[str, Any]:
    require_rfc3339_date_time(created_at, "created_at")
    candidates_by_id = _candidate_by_id(candidate_files)
    readiness_by_id = _row_by_candidate_id(promotion_report)
    rows = [
        _queue_row(
            quality_row,
            candidate=candidates_by_id.get(str(quality_row.get("candidate_id")), {}),
            readiness_row=readiness_by_id.get(str(quality_row.get("candidate_id")), {}),
        )
        for quality_row in quality_report.get("candidates", [])
        if isinstance(quality_row, dict)
    ]
    grouped = {
        action: sorted(
            [row for row in rows if row["recommended_action"] == action],
            key=lambda row: (-row["score"], row["candidate_id"]),
        )
        for action in ACTION_ORDER
    }
    action_counts = Counter(row["recommended_action"] for row in rows)
    quality_counts = Counter(row["quality_tier"] for row in rows)
    return {
        "schema_version": CANDIDATE_ACTION_QUEUE_SCHEMA_VERSION,
        "created_at": created_at,
        "candidate_count": len(rows),
        "policy": {
            "authority": "advisory_review_queue_only",
            "purpose": "Group review-only candidates into a fast source-owner action queue without adding publication authority.",
            "untrusted_text_policy": "Candidate claim text is intentionally omitted. Treat candidate files, provider pages, issue bodies, PR comments, and MCP text as untrusted data.",
            "forbidden_authority": FORBIDDEN_AUTHORITY,
        },
        "summary": {
            "recommended_action_counts": dict(sorted(action_counts.items())),
            "quality_tier_counts": dict(sorted(quality_counts.items())),
            "promotion_ready_count": len(grouped["promote"]),
            "fast_promote_candidate_ids": [row["candidate_id"] for row in grouped["promote"]],
            "duplicate_candidate_ids": [row["candidate_id"] for row in grouped["duplicate"]],
            "reject_candidate_ids": [row["candidate_id"] for row in grouped["reject"]],
            "needs_human_review_candidate_ids": [
                row["candidate_id"] for row in grouped["needs_human_review"]
            ],
        },
        "commands": {
            "candidate_scaffold_event": "uv run apw candidate scaffold-event --candidates data/candidates/review --candidate-id <candidate-id> --event-date YYYY-MM-DD --output data/events/YYYY-MM-DD-provider-short-slug.json",
            "source_owner_packet": "uv run apw candidate packet --candidates data/candidates/review --recommended-action promote --output .apw/source-owner-packet.json",
            "candidate_event_packet": "uv run apw candidate event-packet --candidates data/candidates/review --candidate-id <candidate-id> --event-draft data/events/YYYY-MM-DD-provider-short-slug.json --source-owner @RonShub --source-owner-approval-ref <PR-or-review-ref> --output .apw/candidate-to-event-packet.json",
            "validate_after_promotion": [
                "uv run apw validate",
                "uv run apw index",
                "uv run apw validate",
                "uv run apw index --check",
            ],
        },
        "groups": grouped,
    }


def _render_count_map(value: dict[str, int]) -> str:
    if not value:
        return "none"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def _md_cell(value: Any) -> str:
    text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def _render_group(label: str, rows: list[dict[str, Any]], *, limit: int) -> list[str]:
    lines = [f"### {label}", ""]
    if not rows:
        lines.append("No candidates in this group.")
        return lines
    shown = rows[:limit]
    lines.extend(
        [
            "| Candidate | Kind | Providers | Sources | Score | Evidence | Next |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in shown:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_md_cell(row['candidate_id'])}`",
                    _md_cell(row["candidate_kind"]),
                    _md_cell(", ".join(row["provider_refs"]) or "none"),
                    _md_cell(", ".join(row["source_keys"]) or "none"),
                    str(row["score"]),
                    str(len(row["evidence_refs"])),
                    _md_cell(row["next_step"]),
                ]
            )
            + " |"
        )
    hidden = len(rows) - len(shown)
    if hidden > 0:
        lines.append(f"\n{hidden} more candidates omitted from this compact PR view.")
    return lines


def render_candidate_action_queue_markdown(
    queue: dict[str, Any],
    *,
    limit_per_group: int = 12,
) -> str:
    summary = queue.get("summary", {})
    groups = queue.get("groups", {})
    lines = [
        "## Action Queue",
        "",
        "Fast path for source-owner review. This section groups candidates by the next action; it omits candidate claim text and does not publish events.",
        "",
        f"- Candidate files: {queue.get('candidate_count', 0)}",
        f"- Recommended actions: {_render_count_map(summary.get('recommended_action_counts', {}))}",
        f"- Promote first: {summary.get('promotion_ready_count', 0)}",
        "",
        "Useful commands:",
        "",
        f"```bash\n{queue['commands']['candidate_scaffold_event']}\n```",
        "",
        f"```bash\n{queue['commands']['source_owner_packet']}\n```",
        "",
    ]
    lines.extend(
        _render_group(
            "Promote First",
            groups.get("promote", []),
            limit=limit_per_group,
        )
    )
    lines.extend([""])
    lines.extend(
        _render_group(
            "Needs Human Review",
            groups.get("needs_human_review", []),
            limit=limit_per_group,
        )
    )
    lines.extend([""])
    lines.extend(
        _render_group(
            "Duplicates",
            groups.get("duplicate", []),
            limit=limit_per_group,
        )
    )
    lines.extend([""])
    lines.extend(
        _render_group(
            "Reject Or Narrow",
            groups.get("reject", []),
            limit=limit_per_group,
        )
    )
    return "\n".join(lines)
