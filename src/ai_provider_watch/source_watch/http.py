from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json, write_json_text
from ai_provider_watch.source_watch.parsers import ParsedSourcePayload, parse_source_payload
from ai_provider_watch.source_watch.scopes import scoped_source_content
from ai_provider_watch.sources.registry import SourceDescriptor

USER_AGENT = "ai-provider-watch-source-refresh/0.1"


@dataclass(frozen=True)
class SourceObservation:
    source_key: str
    retrieved_at: str
    final_url: str
    http_status: int
    content_type: str | None
    content_sha256: str
    fingerprint: str
    changed: bool
    parsed: ParsedSourcePayload

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "apw.observation.v0",
            "source_key": self.source_key,
            "retrieved_at": self.retrieved_at,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "content_sha256": self.content_sha256,
            "fingerprint": self.fingerprint,
            "changed": self.changed,
            "items": self.parsed.items,
            "raw_excerpt_hashes": self.parsed.raw_excerpt_hashes,
            "candidate_claims": self.parsed.candidate_claims,
            "errors": self.parsed.errors,
            "snapshot_ref": self.parsed.snapshot_ref,
        }


def normalize_bytes(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text).strip()
    return text.encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_fingerprint_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "apw.source_fingerprints.v0", "sources": {}}
    return read_json(path)


def build_fingerprint_state(observations: list[SourceObservation]) -> dict[str, Any]:
    return {
        "schema_version": "apw.source_fingerprints.v0",
        "sources": {
            observation.source_key: {
                "fingerprint": observation.fingerprint,
                "content_sha256": observation.content_sha256,
                "final_url": observation.final_url,
                "http_status": observation.http_status,
                "retrieved_at": observation.retrieved_at,
            }
            for observation in sorted(observations, key=lambda item: item.source_key)
        },
    }


def fingerprint_bytes(source: SourceDescriptor, raw: bytes) -> bytes:
    scoped = scoped_source_content(source, raw)
    return raw if scoped.errors else scoped.raw


def fetch_source(
    source: SourceDescriptor,
    previous_state: dict[str, Any],
    *,
    timeout: float = 20.0,
    limit_bytes: int = 1_000_000,
) -> SourceObservation:
    request = urllib.request.Request(source.url, headers={"User-Agent": USER_AGENT})
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(limit_bytes + 1)
        if len(raw) > limit_bytes:
            raw = raw[:limit_bytes]
        content_type = response.headers.get("content-type")
        final_url = response.geturl()
        http_status = int(response.status)

    content_sha = _sha256(raw)
    fingerprint = _sha256(normalize_bytes(fingerprint_bytes(source, raw)))
    previous = previous_state.get("sources", {}).get(source.key, {}).get("fingerprint")
    changed = previous != fingerprint
    parsed = parse_source_payload(source, raw, changed=changed)
    return SourceObservation(
        source_key=source.key,
        retrieved_at=retrieved_at,
        final_url=final_url,
        http_status=http_status,
        content_type=content_type,
        content_sha256=content_sha,
        fingerprint=fingerprint,
        changed=changed,
        parsed=parsed,
    )


def write_observations(path: Path, observations: list[SourceObservation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "apw.source_observations.v0",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "observations": [observation.to_json() for observation in observations],
        "changed_source_keys": [
            observation.source_key for observation in observations if observation.changed
        ],
    }
    path.write_text(write_json_text(payload), encoding="utf-8")


def write_fingerprint_state(path: Path, observations: list[SourceObservation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_json_text(build_fingerprint_state(observations)), encoding="utf-8")


def observations_as_json(observations: list[SourceObservation]) -> str:
    return json.dumps([observation.to_json() for observation in observations], indent=2) + "\n"
