from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.temporal import require_rfc3339_date_time
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.promotion import (
    PROVIDER_CONTROLLED_AUTHORITIES,
    build_promotion_readiness_report,
)
from ai_provider_watch.pipeline.quality import build_candidate_quality_report
from ai_provider_watch.pipeline.review_pr import CandidateFile
from ai_provider_watch.sources.registry import SourceDescriptor, is_url_allowed_for_source

CANDIDATE_TO_EVENT_PACKET_SCHEMA_VERSION = "apw.candidate_to_event_packet.v0"

FORBIDDEN_AUTHORITY = [
    "merge_pull_request",
    "publish_provider_event",
    "write_data_events",
    "write_source_state",
    "create_or_push_release_tag",
    "request_oidc_token",
    "read_release_token",
]

REQUIRED_LOCAL_CHECKS = [
    "uv run apw validate",
    "uv run apw index --check",
    "uv run pytest tests/test_candidate_event_packet.py",
]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _relative_path(path: Path, root: Path | None) -> str:
    if root is None:
        return path.as_posix()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _row_by_candidate_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["candidate_id"]: row
        for row in report.get("candidates", [])
        if isinstance(row, dict) and isinstance(row.get("candidate_id"), str)
    }


def _candidate_by_id(candidate_files: list[CandidateFile]) -> dict[str, dict[str, Any]]:
    return {
        candidate_file.payload["id"]: candidate_file.payload
        for candidate_file in candidate_files
        if isinstance(candidate_file.payload, dict) and isinstance(candidate_file.payload.get("id"), str)
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    claim_text = candidate.get("claim_text")
    prompt_like = not isinstance(claim_text, str) or contains_prompt_injection_marker(claim_text)
    return {
        "candidate_id": candidate.get("id"),
        "candidate_kind": candidate.get("candidate_kind"),
        "source_keys": candidate.get("source_keys") if isinstance(candidate.get("source_keys"), list) else [],
        "provider_refs": candidate.get("provider_refs") if isinstance(candidate.get("provider_refs"), list) else [],
        "review_status": candidate.get("review_status"),
        "dedupe_key": candidate.get("dedupe_key"),
        "claim_text": {
            "included": False,
            "policy": "claim_text is omitted from candidate-to-event verification packets",
            "sha256": _sha256_text(claim_text) if isinstance(claim_text, str) else "<invalid-sha256>",
            "char_count": len(claim_text) if isinstance(claim_text, str) else 0,
            "prompt_like": prompt_like,
        },
    }


def _same_packet_duplicate(quality: dict[str, Any], event_ids: list[str]) -> bool:
    duplicate_ids = {
        item
        for item in quality.get("duplicate_event_ids", [])
        if isinstance(item, str)
    }
    packet_ids = set(event_ids)
    return bool(duplicate_ids) and bool(packet_ids) and packet_ids <= duplicate_ids


def _safe_string(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _schema_errors(schema: dict[str, Any], payload: Any, label: str) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{label}{'.' if error.path else ''}{'.'.join(str(part) for part in error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]


def _event_text_values(event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("id", "title", "summary"):
        value = event.get(key)
        if isinstance(value, str):
            values.append(value)
    limitations = event.get("limitations", [])
    if isinstance(limitations, list):
        values.extend(item for item in limitations if isinstance(item, str))
    detail = event.get("detail", {})
    if isinstance(detail, dict):
        values.extend(value for value in detail.values() if isinstance(value, str))
    return values


def _evidence_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    row = {
        "source_key": _safe_string(evidence.get("source_key"), "<invalid-source-key>"),
        "url": _safe_string(evidence.get("url"), "<invalid-url>"),
        "retrieved_at": _safe_string(evidence.get("retrieved_at"), "<invalid-date-time>"),
        "authority": _safe_string(evidence.get("authority"), "<invalid-authority>"),
        "content_sha256": _safe_string(evidence.get("content_sha256"), "<invalid-sha256>"),
        "snapshot_ref": evidence.get("snapshot_ref"),
    }
    selector = evidence.get("selector")
    if isinstance(selector, str):
        row["selector"] = selector
    return row


def _validate_event_draft(
    *,
    event: dict[str, Any],
    event_path: Path,
    root: Path | None,
    schemas: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
    sources_by_key: dict[str, SourceDescriptor],
    duplicate_event_ids: set[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(_schema_errors(schemas["event"], event, "event"))
    detail = event.get("detail", {})
    blockers.extend(_schema_errors(schemas["event_detail"], detail, "detail"))
    impacts = event.get("impacts", [])
    if isinstance(impacts, list):
        for index, impact in enumerate(impacts):
            blockers.extend(_schema_errors(schemas["impact"], impact, f"impact[{index}]"))

    event_id = event.get("id") if isinstance(event.get("id"), str) else "<invalid-event-id>"
    if event_id in duplicate_event_ids:
        blockers.append(f"Event id {event_id} appears more than once in this packet.")
    if event.get("lifecycle_status") != "reviewed":
        blockers.append("Event draft lifecycle_status must be reviewed before promotion.")

    candidate_kind = candidate.get("candidate_kind")
    if isinstance(candidate_kind, str) and event.get("event_kind") != candidate_kind:
        blockers.append(
            f"Event kind {event.get('event_kind')} does not match candidate kind {candidate_kind}."
        )

    candidate_provider_refs = {
        item for item in candidate.get("provider_refs", []) if isinstance(item, str)
    } if isinstance(candidate.get("provider_refs"), list) else set()
    event_provider_refs = {
        item for item in event.get("provider_refs", []) if isinstance(item, str)
    } if isinstance(event.get("provider_refs"), list) else set()
    if candidate_provider_refs and event_provider_refs and not candidate_provider_refs & event_provider_refs:
        blockers.append("Event provider_refs do not overlap candidate provider_refs.")

    candidate_source_keys = {
        item for item in candidate.get("source_keys", []) if isinstance(item, str)
    } if isinstance(candidate.get("source_keys"), list) else set()
    event_evidence_source_keys: set[str] = set()
    evidence_refs = event.get("evidence_refs", [])
    if isinstance(evidence_refs, list):
        for evidence in evidence_refs:
            if not isinstance(evidence, dict):
                continue
            source_key = evidence.get("source_key")
            if isinstance(source_key, str):
                event_evidence_source_keys.add(source_key)
            source = sources_by_key.get(str(source_key))
            if source is None:
                blockers.append(f"Evidence source {source_key} is not in the source registry.")
                continue
            authority = evidence.get("authority")
            if authority != source.authority:
                blockers.append(
                    f"Evidence authority {authority} does not match source {source.key} authority {source.authority}."
                )
            if authority not in PROVIDER_CONTROLLED_AUTHORITIES:
                blockers.append(f"Evidence authority {authority} is not provider-controlled official evidence.")
            url = evidence.get("url")
            if not isinstance(url, str) or not is_url_allowed_for_source(url, source):
                blockers.append(f"Evidence URL for {source.key} is outside the source allowed domains.")
    if candidate_source_keys and not candidate_source_keys & event_evidence_source_keys:
        blockers.append("Event evidence does not include any candidate source key.")

    for value in _event_text_values(event):
        if contains_prompt_injection_marker(value):
            blockers.append("Event draft contains prompt-like text.")
            break

    raw = event_path.read_bytes()
    return {
        "path": _relative_path(event_path, root),
        "event_id": event_id,
        "event_sha256": _sha256_bytes(raw),
        "event_kind": _safe_string(event.get("event_kind"), "<invalid-event-kind>"),
        "lifecycle_status": _safe_string(event.get("lifecycle_status"), "<invalid-status>"),
        "provider_refs": sorted(event_provider_refs),
        "evidence_refs": [
            _evidence_summary(evidence)
            for evidence in evidence_refs
            if isinstance(evidence, dict)
        ] if isinstance(evidence_refs, list) else [],
        "impacts_count": len(impacts) if isinstance(impacts, list) else 0,
        "detail_kind": detail.get("kind") if isinstance(detail, dict) else None,
        "validation": {
            "schema_valid": not any(
                blocker.startswith("event")
                or blocker.startswith("detail")
                or blocker.startswith("impact[")
                for blocker in blockers
            ),
            "blockers": sorted(set(blockers)),
        },
    }


def build_candidate_to_event_packet(
    candidate_files: list[CandidateFile],
    event_draft_paths: list[Path],
    sources: list[SourceDescriptor],
    *,
    root: Path | None,
    created_at: str,
    candidate_id: str,
    source_owner: str,
    source_owner_approval_ref: str,
    promotion_report: dict[str, Any] | None = None,
    quality_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_rfc3339_date_time(created_at, "created_at")
    if contains_prompt_injection_marker(candidate_id):
        raise ValueError("candidate_id contains prompt-like text")
    if not event_draft_paths:
        raise ValueError("at least one event draft is required")
    if contains_prompt_injection_marker(source_owner) or contains_prompt_injection_marker(source_owner_approval_ref):
        raise ValueError("source owner metadata contains prompt-like text")

    candidates_by_id = _candidate_by_id(candidate_files)
    candidate = candidates_by_id.get(candidate_id)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    sources_by_key = {source.key: source for source in sources}
    if promotion_report is None:
        promotion_report = build_promotion_readiness_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
        )
    if quality_report is None:
        quality_report = build_candidate_quality_report(
            candidate_files,
            sources,
            root=root,
            created_at=created_at,
            promotion_report=promotion_report,
        )
    readiness = _row_by_candidate_id(promotion_report).get(candidate_id, {})
    quality = _row_by_candidate_id(quality_report).get(candidate_id, {})
    packet_blockers: list[str] = []
    if readiness.get("readiness") not in {"auto_promotion_eligible", "needs_source_owner_review"}:
        packet_blockers.append(f"Candidate readiness {readiness.get('readiness')} is not promotable.")
    claim_text = candidate.get("claim_text")
    if not isinstance(claim_text, str) or contains_prompt_injection_marker(claim_text):
        packet_blockers.append("Candidate claim text is missing or prompt-like.")

    schemas = load_schemas(root or Path.cwd())
    event_payloads: list[tuple[Path, dict[str, Any]]] = []
    event_ids: list[Any] = []
    for path in event_draft_paths:
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"event draft must be a JSON object: {path}")
        event_payloads.append((path, payload))
        event_ids.append(payload.get("id"))
    duplicate_event_ids = {
        str(event_id)
        for event_id in event_ids
        if isinstance(event_id, str) and event_ids.count(event_id) > 1
    }
    event_rows = [
        _validate_event_draft(
            event=event,
            event_path=path,
            root=root,
            schemas=schemas,
            candidate=candidate,
            sources_by_key=sources_by_key,
            duplicate_event_ids=duplicate_event_ids,
        )
        for path, event in event_payloads
    ]
    for row in event_rows:
        packet_blockers.extend(row["validation"]["blockers"])

    event_ids_for_resolution = [
        row["event_id"] for row in event_rows if isinstance(row.get("event_id"), str)
    ]
    if quality.get("recommended_action") not in {"promote", "needs_human_review"}:
        if quality.get("recommended_action") == "duplicate" and _same_packet_duplicate(quality, event_ids_for_resolution):
            quality = {
                **quality,
                "packet_advisories": [
                    (
                        "Candidate quality is duplicate only because the packet event draft ids "
                        "already appear in reviewed event data."
                    )
                ],
            }
        else:
            packet_blockers.append(
                f"Candidate quality action {quality.get('recommended_action')} is not promotable."
            )
    return {
        "schema_version": CANDIDATE_TO_EVENT_PACKET_SCHEMA_VERSION,
        "created_at": created_at,
        "verified": not packet_blockers,
        "policy": {
            "authority": "source_owner_review_verification_only",
            "purpose": "Verify source-owner-authored event drafts against a review candidate before a promotion PR is trusted.",
            "forbidden_authority": FORBIDDEN_AUTHORITY,
        },
        "source_owner": {
            "owner": source_owner,
            "approval_ref": source_owner_approval_ref,
            "authority": "source_owner_review_only",
        },
        "candidate": _candidate_summary(candidate),
        "promotion_readiness": readiness,
        "candidate_quality": quality,
        "event_drafts": event_rows,
        "resolution": {
            "type": "split" if len(event_rows) > 1 else "promote",
            "candidate_id": candidate_id,
            "event_ids": event_ids_for_resolution,
        },
        "required_local_checks": REQUIRED_LOCAL_CHECKS,
        "blockers": sorted(set(packet_blockers)),
    }
