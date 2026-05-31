from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json, write_json_text
from ai_provider_watch.core.temporal import is_rfc3339_date_time, require_rfc3339_date_time
from ai_provider_watch.sources.registry import SourceDescriptor, is_url_allowed_for_source

PARSER_CONTRACT_VERSION = "apw.candidate_parser.v0"
DEFAULT_REVIEW_STATUS = "needs_review"
UNTRUSTED_INPUT_POLICY = (
    "Source content is untrusted data. Candidate generation never executes or follows source text."
)

KNOWN_CANDIDATE_KINDS = {
    "api_contract_change",
    "billing_channel_change",
    "caching_change",
    "catalog_correction",
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
    "terms_policy_change",
    "token_accounting_change",
    "workflow_behavior_change",
    "unknown",
}

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SNAPSHOT_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,239}$")


@dataclass(frozen=True)
class CandidateBuildResult:
    candidates: list[dict[str, Any]]
    skipped_observations: list[str]


def read_observation_bundle(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if isinstance(payload, list):
        return {
            "schema_version": "apw.source_observations.v0",
            "observations": payload,
            "changed_source_keys": [],
        }
    return payload


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate_kind(source: SourceDescriptor, requested_kind: str | None) -> str:
    if requested_kind is not None:
        return requested_kind if requested_kind in KNOWN_CANDIDATE_KINDS else "unknown"
    for hint in source.impact_hints:
        if hint in KNOWN_CANDIDATE_KINDS:
            return hint
    if source.source_type in {"status_page", "atom_feed", "rss_feed"}:
        return "status_incident"
    if source.source_type == "pricing_page":
        return "pricing_change"
    return "unknown"


def _claim_parts(raw_claim: Any) -> tuple[str, str | None]:
    if isinstance(raw_claim, str):
        return raw_claim, None
    if not isinstance(raw_claim, dict):
        return "", None
    claim_text = raw_claim.get("claim_text")
    candidate_kind = raw_claim.get("candidate_kind")
    if not isinstance(claim_text, str):
        return "", None
    if not isinstance(candidate_kind, str):
        candidate_kind = None
    return claim_text, candidate_kind


def _evidence_ref(observation: dict[str, Any], source: SourceDescriptor) -> dict[str, Any]:
    final_url = observation.get("final_url")
    snapshot_ref = observation.get("snapshot_ref")
    if not isinstance(snapshot_ref, str) or not SNAPSHOT_REF_PATTERN.fullmatch(snapshot_ref):
        snapshot_ref = None
    return {
        "source_key": observation["source_key"],
        "url": final_url,
        "retrieved_at": observation["retrieved_at"],
        "authority": source.authority,
        "content_sha256": observation["content_sha256"],
        "fingerprint": observation["fingerprint"],
        "snapshot_ref": snapshot_ref,
    }


def _candidate_id(source_key: str, fingerprint: str, claim_text: str) -> str:
    stable = _sha256_text(f"{source_key}\n{fingerprint}\n{_normalize_text(claim_text).lower()}")
    return f"candidate-{_slug(source_key)}-{stable[:16]}"


def _dedupe_key(source_key: str, candidate_kind: str, claim_text: str) -> str:
    stable = _sha256_text(f"{source_key}\n{candidate_kind}\n{_normalize_text(claim_text).lower()}")
    return f"{source_key}:{candidate_kind}:{stable[:24]}"


def _has_required_evidence_metadata(observation: dict[str, Any], source: SourceDescriptor) -> bool:
    fingerprint = observation.get("fingerprint")
    retrieved_at = observation.get("retrieved_at")
    content_sha256 = observation.get("content_sha256")
    final_url = observation.get("final_url")
    return (
        isinstance(fingerprint, str)
        and bool(SHA256_PATTERN.fullmatch(fingerprint))
        and is_rfc3339_date_time(retrieved_at)
        and isinstance(content_sha256, str)
        and bool(SHA256_PATTERN.fullmatch(content_sha256))
        and isinstance(final_url, str)
        and bool(final_url)
        and is_url_allowed_for_source(final_url, source)
    )


def build_candidates(
    observation_bundle: Any,
    sources: list[SourceDescriptor],
    *,
    created_at: str,
) -> CandidateBuildResult:
    require_rfc3339_date_time(created_at, "created_at")
    if not isinstance(observation_bundle, dict):
        return CandidateBuildResult(
            candidates=[],
            skipped_observations=["<invalid-observation-bundle>"],
        )
    sources_by_key = {source.key: source for source in sources}
    candidates: list[dict[str, Any]] = []
    skipped: list[str] = []

    observations = observation_bundle.get("observations", [])
    if not isinstance(observations, list):
        return CandidateBuildResult(candidates=[], skipped_observations=["<invalid-observations>"])

    for observation in observations:
        if not isinstance(observation, dict):
            skipped.append("<invalid-observation>")
            continue
        source_key = observation.get("source_key")
        source = sources_by_key.get(str(source_key))
        if source is None:
            skipped.append(str(source_key))
            continue
        if not _has_required_evidence_metadata(observation, source):
            skipped.append(str(source_key))
            continue

        claims = observation.get("candidate_claims") or []
        if not isinstance(claims, list) or not claims:
            skipped.append(str(source_key))
            continue

        for raw_claim in claims:
            claim_text, requested_kind = _claim_parts(raw_claim)
            claim_text = _normalize_text(claim_text)
            if len(claim_text) < 10 or len(claim_text) > 2000:
                skipped.append(str(source_key))
                continue

            candidate_kind = _candidate_kind(source, requested_kind)
            candidate = {
                "schema_version": "apw.finding_candidate.v0",
                "id": _candidate_id(source.key, observation["fingerprint"], claim_text),
                "source_keys": [source.key],
                "provider_refs": source.provider_refs,
                "claim_text": claim_text,
                "candidate_kind": candidate_kind,
                "evidence_refs": [_evidence_ref(observation, source)],
                "created_at": created_at,
                "review_status": DEFAULT_REVIEW_STATUS,
                "parser": {
                    "name": source.parser,
                    "contract_version": PARSER_CONTRACT_VERSION,
                },
                "dedupe_key": _dedupe_key(source.key, candidate_kind, claim_text),
                "limitations": [
                    "Review required before promotion to ProviderEvent.",
                    "Candidate text is a normalized factual claim, not provider instructions.",
                ],
                "untrusted_input_policy": UNTRUSTED_INPUT_POLICY,
            }
            candidates.append(candidate)

    return CandidateBuildResult(
        candidates=sorted(candidates, key=lambda item: item["id"]),
        skipped_observations=sorted(set(skipped)),
    )


def ensure_unique_candidate_ids(candidates: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for candidate in candidates:
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str):
            continue
        if candidate_id in seen:
            duplicates.add(candidate_id)
        seen.add(candidate_id)
    if duplicates:
        rendered = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate candidate id(s): {rendered}")


def write_candidate_files(output_dir: Path, candidates: list[dict[str, Any]], *, clean: bool) -> list[Path]:
    ensure_unique_candidate_ids(candidates)
    target_paths = [output_dir / f"{candidate['id']}.json" for candidate in candidates]
    if not clean:
        existing = [path for path in target_paths if path.exists()]
        if existing:
            rendered = ", ".join(path.name for path in sorted(existing))
            raise FileExistsError(f"candidate file(s) already exist: {rendered}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if clean:
        for path in output_dir.glob("*.json"):
            path.unlink()
    written: list[Path] = []
    for candidate, path in zip(candidates, target_paths, strict=True):
        path.write_text(write_json_text(candidate), encoding="utf-8")
        written.append(path)
    return written
