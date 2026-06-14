from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch import __version__
from ai_provider_watch.core.feeds import APW_HOME_URL, JSON_FEED_VERSION, SEVERITY_RANK, load_events
from ai_provider_watch.core.io import read_json, write_json_text, write_ndjson_text
from ai_provider_watch.pipeline.review_pr import CandidateFile, read_candidate_files
from ai_provider_watch.pipeline.source_catalog import build_source_catalog

LIVE_EVENT_SCHEMA_VERSION = "apw.live_event.v0"
LIVE_FEED_SCHEMA_VERSION = "apw.live_feed.v0"
LIVE_HEALTH_SCHEMA_VERSION = "apw.live_health.v0"
LIVE_PROVENANCE_SCHEMA_VERSION = "apw.live_provenance.v0"
LIVE_CADENCE_MINUTES = 15
DEFAULT_LIVE_BASE_URL = "https://ai-provider-watch.ottto.net/v1"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_LIMIT_BYTES = 5_000_000
LIVE_ARTIFACTS = {
    "latest": "latest.json",
    "events": "events.json",
    "events.ndjson": "events.ndjson",
    "feed": "feed.json",
    "rss": "rss.xml",
    "atom": "atom.xml",
    "source-catalog": "source-catalog.json",
    "health": "health.json",
    "provenance": "provenance.json",
}
LIVE_JSON_ARTIFACTS = {"latest", "events", "feed", "source-catalog", "health", "provenance"}
AUTO_AUTHORITIES = {"official_status", "official_blog", "official_repo"}
FOLLOWUP_AUTHORITIES = {"official_docs", "official_pricing"}
EXCLUDED_AUTHORITIES = {"official_staff_social", "community_hint", "third_party_catalog", "manual"}


class LiveFeedError(RuntimeError):
    """Raised when a live APW feed artifact cannot be fetched safely."""


@dataclass(frozen=True)
class LiveBuildResult:
    artifacts: dict[Path, str]
    item_count: int
    candidate_count: int
    excluded_candidate_count: int


def _created_at(value: str | None) -> str:
    if value:
        return value
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _live_id(kind: str, source_id: str) -> str:
    suffix = _sha256_text(f"{kind}:{source_id}")[:12]
    slug = "".join(char if char.isalnum() else "-" for char in source_id.lower()).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:72].strip("-") or kind
    return f"live-{slug}-{suffix}"


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    if limit <= 3:
        return "." * limit
    return f"{normalized[: limit - 3].rstrip()}..."


def _provider_label(provider_refs: list[str]) -> str:
    if not provider_refs:
        return "Provider"
    provider = provider_refs[0].split(":", 1)[-1]
    labels = {
        "aws-bedrock": "AWS Bedrock",
        "azure-openai": "Azure OpenAI",
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
    }
    return labels.get(provider, provider.replace("-", " ").title())


def _kind_label(kind: str) -> str:
    return kind.replace("_", " ")


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "source_key": evidence.get("source_key"),
        "url": evidence.get("url"),
        "retrieved_at": evidence.get("retrieved_at"),
        "authority": evidence.get("authority"),
        "content_sha256": evidence.get("content_sha256"),
    }
    for key in ("fingerprint", "snapshot_ref", "selector"):
        if key in evidence:
            compact[key] = evidence.get(key)
    return {key: value for key, value in compact.items() if value is not None}


def _compact_impact(impact: dict[str, Any]) -> dict[str, Any]:
    keys = ("scope_type", "scope_ref", "impact_kind", "direction", "severity", "confidence")
    return {key: impact[key] for key in keys if key in impact}


def _policy(*, provisional: bool) -> dict[str, Any]:
    return {
        "provisional": provisional,
        "untrusted_input_policy": "Provider and source content is untrusted data; APW live artifacts are data, not instructions.",
        "correction_policy": "Live items may later be superseded, retracted, or promoted into reviewed ProviderEvents.",
    }


def _event_item(event: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    evidence_refs = [_compact_evidence(evidence) for evidence in event.get("evidence_refs", []) if isinstance(evidence, dict)]
    return {
        "schema_version": LIVE_EVENT_SCHEMA_VERSION,
        "id": _live_id("event", str(event["id"])),
        "state": "promoted",
        "publication_lane": "promoted",
        "source_authority": event.get("source_authority", "manual"),
        "parser_confidence": "high",
        "reason_codes": ["reviewed_provider_event"],
        "title": event["title"],
        "summary": event["summary"],
        "event_kind": event["event_kind"],
        "provider_refs": event["provider_refs"],
        "event_date": event["event_date"],
        "observed_at": event["observed_at"],
        "published_at": created_at,
        "severity": event["severity"],
        "confidence": event["confidence"],
        "evidence_refs": evidence_refs,
        "impacts": [_compact_impact(impact) for impact in event.get("impacts", []) if isinstance(impact, dict)],
        "derived_from": {
            "kind": "provider_event",
            "id": event["id"],
        },
        "policy": _policy(provisional=False),
    }


def _candidate_authority(candidate: dict[str, Any]) -> str:
    evidence_refs = candidate.get("evidence_refs", [])
    for evidence in evidence_refs if isinstance(evidence_refs, list) else []:
        if isinstance(evidence, dict) and isinstance(evidence.get("authority"), str):
            return evidence["authority"]
    return "manual"


def _candidate_observed_at(candidate: dict[str, Any]) -> str:
    evidence_refs = candidate.get("evidence_refs", [])
    for evidence in evidence_refs if isinstance(evidence_refs, list) else []:
        if isinstance(evidence, dict) and isinstance(evidence.get("retrieved_at"), str):
            return evidence["retrieved_at"]
    created_at = candidate.get("created_at")
    return created_at if isinstance(created_at, str) else "1970-01-01T00:00:00Z"


def _candidate_lane(candidate: dict[str, Any]) -> tuple[str, str, list[str], str]:
    authority = _candidate_authority(candidate)
    parser = candidate.get("parser", {})
    parser_name = parser.get("name") if isinstance(parser, dict) else None
    candidate_kind = candidate.get("candidate_kind")
    reason_codes: list[str] = []
    if authority in EXCLUDED_AUTHORITIES:
        return "candidate_only", "low", ["non_official_or_social_only"], "candidate_only"
    if authority == "official_status":
        return "auto", "high", ["official_status_source"], "automated"
    if authority in AUTO_AUTHORITIES:
        return "auto", "high", ["dated_official_entry"], "automated"
    if authority == "official_docs" and isinstance(parser_name, str):
        if any(token in parser_name for token in ("changelog", "release_notes", "whats_new")):
            return "auto", "high", ["dated_official_entry"], "automated"
        if candidate_kind in {"model_deprecation", "model_retirement"}:
            return "auto", "medium", ["lifecycle_date_row"], "automated"
        reason_codes.append("scoped_docs_delta")
    if authority == "official_pricing":
        reason_codes.append("pricing_row_delta")
    if authority in FOLLOWUP_AUTHORITIES:
        return "needs_followup", "medium", reason_codes or ["official_source_delta"], "needs_followup"
    return "needs_followup", "low", ["unclassified_official_source"], "needs_followup"


def _candidate_severity(kind: str) -> str:
    if kind in {"model_retirement", "model_deprecation", "pricing_change", "quota_change", "rate_limit_change"}:
        return "medium"
    if kind in {"api_contract_change", "default_model_change", "token_accounting_change", "status_incident"}:
        return "medium"
    if kind in {"model_launch", "regional_availability_change", "status_recovery"}:
        return "low"
    return "info"


def _candidate_item(candidate: dict[str, Any], *, created_at: str) -> dict[str, Any] | None:
    lane, parser_confidence, reason_codes, state = _candidate_lane(candidate)
    if lane == "candidate_only":
        return None
    candidate_id = str(candidate.get("id", "candidate-unknown-0000000000000000"))
    kind = str(candidate.get("candidate_kind", "unknown"))
    provider_refs = [
        item for item in candidate.get("provider_refs", []) if isinstance(item, str)
    ] or ["provider:unknown"]
    claim_text = str(candidate.get("claim_text", "")).strip()
    title = _truncate(claim_text, 140) if len(claim_text) >= 8 else f"{_provider_label(provider_refs)} {_kind_label(kind)}"
    summary = _truncate(
        claim_text
        or f"{_provider_label(provider_refs)} has a provisional {_kind_label(kind)} live signal from official source metadata.",
        420,
    )
    observed_at = _candidate_observed_at(candidate)
    confidence = "high" if lane == "auto" else "medium"
    return {
        "schema_version": LIVE_EVENT_SCHEMA_VERSION,
        "id": _live_id("candidate", candidate_id),
        "state": state,
        "publication_lane": lane,
        "source_authority": _candidate_authority(candidate),
        "parser_confidence": parser_confidence,
        "reason_codes": sorted(set(reason_codes)),
        "title": title,
        "summary": summary,
        "event_kind": kind,
        "provider_refs": provider_refs,
        "event_date": observed_at[:10],
        "observed_at": observed_at,
        "published_at": created_at,
        "severity": _candidate_severity(kind),
        "confidence": confidence,
        "evidence_refs": [
            _compact_evidence(evidence)
            for evidence in candidate.get("evidence_refs", [])
            if isinstance(evidence, dict)
        ],
        "derived_from": {
            "kind": "finding_candidate",
            "id": candidate_id,
        },
        "policy": _policy(provisional=True),
    }


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item.get("observed_at", ""),
            SEVERITY_RANK.get(str(item.get("severity", "info")), 0),
            item.get("id", ""),
        ),
        reverse=True,
    )


def _live_feed(items: list[dict[str, Any]], *, created_at: str, feed_kind: str) -> dict[str, Any]:
    return {
        "schema_version": LIVE_FEED_SCHEMA_VERSION,
        "generated_at": created_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "feed_kind": feed_kind,
        "cadence_minutes": LIVE_CADENCE_MINUTES,
        "item_count": len(items),
        "items": items,
        "policy": {
            "mode": "provisional_live_news",
            "review_posture": "lenient high-recall live lane; audited repository promotion remains stricter",
            "source_posture": "official source-controlled evidence only; community and social-only evidence stay candidate-only",
        },
    }


def _media_type(path: str) -> str:
    if path.endswith("feed.json"):
        return "application/feed+json"
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".ndjson"):
        return "application/x-ndjson"
    if path.endswith(".xml"):
        return "application/xml"
    return "application/octet-stream"


def _artifact_summary(path: Path, text: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "media_type": _media_type(str(path)),
        "sha256": _sha256_text(text),
        "bytes": len(text.encode("utf-8")),
    }


def _rss_pub_date(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return format_datetime(parsed.astimezone(UTC), usegmt=True)


def _rss(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items[:50]:
        rows.append(
            "    <item>\n"
            f"      <guid isPermaLink=\"false\">{escape(item['id'])}</guid>\n"
            f"      <title>{escape(item['title'])}</title>\n"
            f"      <description>{escape(item['summary'])}</description>\n"
            f"      <category>{escape(item['event_kind'])}</category>\n"
            f"      <pubDate>{escape(_rss_pub_date(item['observed_at']))}</pubDate>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
        "    <title>AI Provider Watch Live</title>\n"
        f"    <link>{APW_HOME_URL}</link>\n"
        "    <description>Provisional AI-provider change news.</description>\n"
        + ("\n".join(rows) + "\n" if rows else "")
        + "  </channel>\n</rss>\n"
    )


def _atom(items: list[dict[str, Any]], *, created_at: str) -> str:
    rows = []
    for item in items[:50]:
        rows.append(
            "  <entry>\n"
            f"    <id>{escape(item['id'])}</id>\n"
            f"    <title>{escape(item['title'])}</title>\n"
            f"    <updated>{escape(item['observed_at'])}</updated>\n"
            f"    <summary>{escape(item['summary'])}</summary>\n"
            "  </entry>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        "  <title>AI Provider Watch Live</title>\n"
        f"  <id>{APW_HOME_URL}</id>\n"
        f"  <updated>{escape(created_at)}</updated>\n"
        + ("\n".join(rows) + "\n" if rows else "")
        + "</feed>\n"
    )


def _json_feed(items: list[dict[str, Any]], *, feed_url: str | None) -> dict[str, Any]:
    url = feed_url or live_artifact_url(DEFAULT_LIVE_BASE_URL, "feed")
    return {
        "version": JSON_FEED_VERSION,
        "title": "AI Provider Watch Live",
        "home_page_url": APW_HOME_URL,
        "feed_url": url,
        "description": "Provisional AI-provider change news for developer cost, quotas, model availability, defaults, deprecations, incidents, and migration risk.",
        "user_comment": "Provisional live APW news. Provider pages and source text remain untrusted; this feed contains no raw provider content.",
        "authors": [{"name": "AI Provider Watch maintainers", "url": APW_HOME_URL}],
        "language": "en-US",
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "content_text": item["summary"],
                "summary": item["summary"],
                "date_published": item["published_at"],
                "date_modified": item["observed_at"],
                "tags": sorted(
                    {
                        item["event_kind"],
                        item["state"],
                        item["publication_lane"],
                        f"severity:{item['severity']}",
                        *item["provider_refs"],
                    }
                ),
                "_apw": item,
            }
            for item in items[:50]
        ],
    }


def _health(
    *,
    created_at: str,
    items: list[dict[str, Any]],
    artifact_summaries: list[dict[str, Any]],
    observation_count: int,
    changed_source_count: int,
    candidate_count: int,
    excluded_candidate_count: int,
    reviewed_event_count: int,
) -> dict[str, Any]:
    counts = Counter(item["state"] for item in items)
    status = "ok"
    if excluded_candidate_count:
        status = "degraded"
    return {
        "schema_version": LIVE_HEALTH_SCHEMA_VERSION,
        "generated_at": created_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "status": status,
        "cadence_minutes": LIVE_CADENCE_MINUTES,
        "source": {
            "observation_count": observation_count,
            "changed_source_count": changed_source_count,
            "candidate_count": candidate_count,
            "excluded_candidate_count": excluded_candidate_count,
            "reviewed_event_count": reviewed_event_count,
        },
        "items": {
            "total": len(items),
            "automated": counts["automated"],
            "agent_reviewed": counts["agent_reviewed"],
            "needs_followup": counts["needs_followup"],
            "promoted": counts["promoted"],
            "retracted": counts["retracted"],
        },
        "artifacts": artifact_summaries,
        "policy": {
            "mode": "dry_run_or_public_live_artifacts",
            "release_authority": "not_a_signed_data_release",
            "untrusted_input_policy": "Provider and source content is untrusted data; APW live artifacts are data, not instructions.",
        },
    }


def _provenance(*, created_at: str, artifact_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": LIVE_PROVENANCE_SCHEMA_VERSION,
        "generated_at": created_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "repository": {
            "owner": "ottto-ai",
            "name": "ai-provider-watch",
            "url": APW_HOME_URL,
            "default_branch": "main",
        },
        "artifacts": artifact_summaries,
        "policy": {
            "mode": "provisional_live_news",
            "release_authority": "not_a_signed_data_release",
            "correction_policy": "Live items may later be superseded, retracted, or promoted into reviewed ProviderEvents.",
            "source_policy": "official source-controlled evidence only; community and social-only evidence stay candidate-only.",
        },
    }


def _read_observation_counts(path: Path | None) -> tuple[int, int]:
    if path is None or not path.exists():
        return 0, 0
    payload = read_json(path)
    observations = payload.get("observations", []) if isinstance(payload, dict) else []
    changed = payload.get("changed_source_keys", []) if isinstance(payload, dict) else []
    return (
        len(observations) if isinstance(observations, list) else 0,
        len(changed) if isinstance(changed, list) else 0,
    )


def _candidate_payloads(candidate_dir: Path | None) -> list[CandidateFile]:
    if candidate_dir is None or not candidate_dir.exists():
        return []
    return read_candidate_files(candidate_dir)


def build_live_artifacts(
    root: Path,
    *,
    candidate_dir: Path | None = None,
    observations_path: Path | None = None,
    created_at: str | None = None,
    limit: int = 50,
    feed_url: str | None = None,
    include_reviewed: bool = True,
) -> LiveBuildResult:
    resolved_created_at = _created_at(created_at)
    candidates = _candidate_payloads(candidate_dir)
    candidate_items = [
        item
        for item in (
            _candidate_item(candidate_file.payload, created_at=resolved_created_at)
            for candidate_file in candidates
        )
        if item is not None
    ]
    reviewed_events = load_events(root) if include_reviewed else []
    reviewed_items = [
        _event_item(event, created_at=resolved_created_at)
        for event in reviewed_events[:limit]
    ]
    items = _sort_items([*candidate_items, *reviewed_items])[:limit]
    latest_feed = _live_feed(items, created_at=resolved_created_at, feed_kind="latest")
    events_feed = _live_feed(_sort_items([*candidate_items, *reviewed_items]), created_at=resolved_created_at, feed_kind="events")
    artifacts: dict[Path, str] = {
        Path("latest.json"): write_json_text(latest_feed),
        Path("events.json"): write_json_text(events_feed),
        Path("events.ndjson"): write_ndjson_text(events_feed["items"]),
        Path("feed.json"): write_json_text(_json_feed(items, feed_url=feed_url)),
        Path("rss.xml"): _rss(items),
        Path("atom.xml"): _atom(items, created_at=resolved_created_at),
        Path("source-catalog.json"): write_json_text(
            build_source_catalog(root, created_at=resolved_created_at)
        ),
    }
    observation_count, changed_source_count = _read_observation_counts(observations_path)
    summaries_without_health = [_artifact_summary(path, text) for path, text in sorted(artifacts.items())]
    health = _health(
        created_at=resolved_created_at,
        items=items,
        artifact_summaries=summaries_without_health,
        observation_count=observation_count,
        changed_source_count=changed_source_count,
        candidate_count=len(candidates),
        excluded_candidate_count=len(candidates) - len(candidate_items),
        reviewed_event_count=len(reviewed_events),
    )
    artifacts[Path("health.json")] = write_json_text(health)
    summaries_with_health = [_artifact_summary(path, text) for path, text in sorted(artifacts.items())]
    artifacts[Path("provenance.json")] = write_json_text(
        _provenance(created_at=resolved_created_at, artifact_summaries=summaries_with_health)
    )
    return LiveBuildResult(
        artifacts=artifacts,
        item_count=len(items),
        candidate_count=len(candidates),
        excluded_candidate_count=len(candidates) - len(candidate_items),
    )


def write_live_artifacts(output_dir: Path, artifacts: dict[Path, str]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for relative_path, text in sorted(artifacts.items()):
        path = output_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def load_live_feed(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"live feed is not a JSON object: {path}")
    return payload


def live_artifact_url(base_url: str, artifact: str) -> str:
    path = LIVE_ARTIFACTS.get(artifact)
    if path is None:
        allowed = ", ".join(sorted(LIVE_ARTIFACTS))
        raise ValueError(f"unknown live artifact {artifact!r}; expected one of: {allowed}")
    normalized_base = base_url.strip()
    if not normalized_base:
        raise ValueError("live base URL is required")
    parsed = urlparse(normalized_base)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("live base URL must be an https URL")
    return urljoin(f"{normalized_base.rstrip('/')}/", path)


def fetch_live_text(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = DEFAULT_LIMIT_BYTES,
) -> str:
    normalized_url = url.strip()
    parsed = urlparse(normalized_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("live URL must be an https URL")
    request = Request(
        normalized_url,
        headers={
            "Accept": "application/json, application/feed+json, application/xml, text/plain, */*",
            "User-Agent": f"ai-provider-watch/{__version__}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(limit_bytes + 1)
    except HTTPError as exc:
        raise LiveFeedError(f"live feed fetch failed: HTTP {exc.code} {normalized_url}") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise LiveFeedError(f"live feed fetch failed: {exc}") from exc
    if len(payload) > limit_bytes:
        raise LiveFeedError(f"live feed exceeds byte limit: {limit_bytes}")
    return payload.decode("utf-8")


def fetch_live_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = DEFAULT_LIMIT_BYTES,
) -> Any:
    text = fetch_live_text(url, timeout=timeout, limit_bytes=limit_bytes)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LiveFeedError(f"live feed is not valid JSON: {url}") from exc


def live_latest_from_feed(
    feed: dict[str, Any],
    *,
    provider: str | None = None,
    min_severity: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    items = feed.get("items", [])
    if not isinstance(items, list):
        raise ValueError("live feed items is not a JSON array")
    filtered = [item for item in items if isinstance(item, dict)]
    if provider:
        provider_ref = provider if provider.startswith("provider:") else f"provider:{provider}"
        filtered = [item for item in filtered if provider_ref in item.get("provider_refs", [])]
    if min_severity:
        floor = SEVERITY_RANK[min_severity]
        filtered = [item for item in filtered if SEVERITY_RANK.get(str(item.get("severity", "info")), 0) >= floor]
    return filtered[:limit]


def live_latest(path: Path, *, provider: str | None = None, min_severity: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    try:
        return live_latest_from_feed(
            load_live_feed(path),
            provider=provider,
            min_severity=min_severity,
            limit=limit,
        )
    except ValueError as exc:
        raise ValueError(f"{exc}: {path}") from exc


def _schema_errors(schema: dict[str, Any], payload: Any, label: str) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{label}{'.' + '.'.join(str(part) for part in error.path) if error.path else ''}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]


def validate_live_artifacts(root: Path, input_dir: Path) -> list[str]:
    schemas = {
        "live_event": read_json(root / "schemas" / "live-event.schema.json"),
        "live_feed": read_json(root / "schemas" / "live-feed.schema.json"),
        "live_health": read_json(root / "schemas" / "live-health.schema.json"),
        "live_provenance": read_json(root / "schemas" / "live-provenance.schema.json"),
        "source_catalog": read_json(root / "schemas" / "source-catalog.schema.json"),
    }
    errors: list[str] = []
    for name in ("latest", "events"):
        path = input_dir / LIVE_ARTIFACTS[name]
        if not path.exists():
            errors.append(f"missing live artifact: {path}")
            continue
        payload = read_json(path)
        errors.extend(_schema_errors(schemas["live_feed"], payload, name))
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if isinstance(items, list):
            for index, item in enumerate(items):
                errors.extend(_schema_errors(schemas["live_event"], item, f"{name}.items[{index}]"))
    for name, schema_key in (("health", "live_health"), ("provenance", "live_provenance")):
        path = input_dir / LIVE_ARTIFACTS[name]
        if not path.exists():
            errors.append(f"missing live artifact: {path}")
            continue
        errors.extend(_schema_errors(schemas[schema_key], read_json(path), name))
    source_catalog_path = input_dir / LIVE_ARTIFACTS["source-catalog"]
    if not source_catalog_path.exists():
        errors.append(f"missing live artifact: {source_catalog_path}")
    else:
        errors.extend(
            _schema_errors(
                schemas["source_catalog"],
                read_json(source_catalog_path),
                "source-catalog",
            )
        )
    ndjson_path = input_dir / LIVE_ARTIFACTS["events.ndjson"]
    if not ndjson_path.exists():
        errors.append(f"missing live artifact: {ndjson_path}")
    else:
        for line_number, line in enumerate(ndjson_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"events.ndjson line {line_number}: {exc}")
                continue
            errors.extend(_schema_errors(schemas["live_event"], item, f"events.ndjson[{line_number}]"))
    for name in ("feed", "rss", "atom"):
        path = input_dir / LIVE_ARTIFACTS[name]
        if not path.exists():
            errors.append(f"missing live artifact: {path}")
        elif not path.read_text(encoding="utf-8").strip():
            errors.append(f"empty live artifact: {path}")
    return errors
