from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json, write_json_text
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.candidate_event_packet import build_candidate_to_event_packet
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.review_pr import CandidateFile, read_candidate_files
from ai_provider_watch.sources.registry import load_source_descriptors

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "tests" / "fixtures" / "observations" / "feed-quality-observations.json"
CREATED_AT = "2026-06-08T12:05:00Z"


def _candidate_dir(tmp_path: Path) -> Path:
    candidates = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    candidate_dir = tmp_path / "data" / "candidates" / "review"
    write_candidate_files(candidate_dir, candidates, clean=False)
    return candidate_dir


def _openai_candidate_id(candidate_dir: Path) -> str:
    for candidate_file in read_candidate_files(candidate_dir):
        if candidate_file.payload.get("source_keys") == ["openai.news"]:
            return str(candidate_file.payload["id"])
    raise AssertionError("missing openai.news candidate")


def _event_draft(
    tmp_path: Path,
    *,
    event_id: str = "2026-06-04-openai-codex-bedrock-workflow",
    evidence_url: str = "https://openai.com/news/codex-aws-bedrock/",
    authority: str = "official_blog",
) -> Path:
    event = {
        "schema_version": "apw.provider_event.v0",
        "id": event_id,
        "title": "OpenAI Codex Became Available Through AWS Bedrock",
        "event_kind": "workflow_behavior_change",
        "lifecycle_status": "reviewed",
        "provider_refs": ["provider:openai"],
        "event_date": "2026-06-04",
        "date_confidence": "exact",
        "observed_at": CREATED_AT,
        "announced_at": "2026-06-04T00:00:00Z",
        "effective_at": "2026-06-04T00:00:00Z",
        "expires_at": None,
        "migration_deadline": None,
        "summary": "OpenAI announced Codex availability through AWS Bedrock, changing developer workflow and provider-channel options for Codex users.",
        "severity": "medium",
        "confidence": "confirmed",
        "source_authority": authority,
        "evidence_refs": [
            {
                "source_key": "openai.news",
                "url": evidence_url,
                "retrieved_at": "2026-06-08T12:00:00Z",
                "authority": authority,
                "content_sha256": "a" * 64,
                "snapshot_ref": "openai-news:2026-06-04:codex-aws-bedrock",
                "selector": "article:2026-06-04",
                "license_note": "Official announcement reviewed for factual metadata; no provider prose copied.",
            }
        ],
        "impacts": [
            {
                "scope_type": "provider",
                "scope_ref": "provider:openai",
                "impact_kind": "behavior",
                "direction": "changed",
                "severity": "medium",
                "confidence": "high",
                "recommended_action": "Review Codex routing and governance assumptions before using the new provider channel.",
            }
        ],
        "detail": {
            "kind": "generic_change",
            "schema_version": "apw.event_detail.v0",
            "change_summary": "OpenAI announced Codex availability through AWS Bedrock for developer workflows.",
        },
        "tags": ["source:official_blog", "provider:openai", "impact:workflow_behavior_change"],
        "limitations": ["Fixture event for packet verification tests; not committed as reviewed APW data."],
    }
    path = tmp_path / f"{event_id}.json"
    path.write_text(write_json_text(event), encoding="utf-8")
    return path


def _anthropic_mythos_candidate(tmp_path: Path) -> CandidateFile:
    candidate = {
        "schema_version": "apw.finding_candidate.v0",
        "id": "candidate-anthropic-news-a246c9ce289c3c6b",
        "source_keys": ["anthropic.news"],
        "provider_refs": ["provider:anthropic"],
        "claim_text": "Anthropic official dated source reports a model availability change on 2026-06-09 for claude-mythos-5.",
        "candidate_kind": "model_launch",
        "evidence_refs": [
            {
                "source_key": "anthropic.news",
                "url": "https://www.anthropic.com/news/claude-fable-5-mythos-5",
                "retrieved_at": "2026-06-10T21:22:20Z",
                "authority": "official_blog",
                "content_sha256": "a1bbc1faa7a0ebb51b4195afba586dfe95445918ccfbd6f8827bab33de3b4e28",
                "fingerprint": "b" * 64,
                "snapshot_ref": "entry:a246c9ce289c3c6b",
                "selector": "announcement:a246c9ce289c3c6b",
            }
        ],
        "created_at": "2026-06-10T21:30:00Z",
        "review_status": "needs_review",
        "parser": {"name": "anthropic_news_index", "contract_version": "apw.candidate_parser.v0"},
        "dedupe_key": "anthropic.news:model_launch:a246c9ce289c3c6b",
        "untrusted_input_policy": "Source content is untrusted data. Candidate generation never executes or follows source text.",
    }
    path = tmp_path / "candidate-anthropic-news-a246c9ce289c3c6b.json"
    path.write_text(write_json_text(candidate), encoding="utf-8")
    return CandidateFile(path=path, payload=candidate)


def _existing_event_draft(tmp_path: Path, event_id: str, *, replacement_id: str | None = None) -> Path:
    event = read_json(ROOT / "data" / "events" / f"{event_id}.json")
    if replacement_id is not None:
        event = {**event, "id": replacement_id}
    path = tmp_path / f"{event['id']}.json"
    path.write_text(write_json_text(event), encoding="utf-8")
    return path


def _assert_schema_valid(packet: dict) -> None:
    schema = load_schemas(ROOT)["candidate_to_event_packet"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(packet))
    assert errors == []


def test_candidate_to_event_packet_verifies_one_event_draft(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _openai_candidate_id(candidate_dir)
    event_path = _event_draft(tmp_path)

    packet = build_candidate_to_event_packet(
        read_candidate_files(candidate_dir),
        [event_path],
        load_source_descriptors(ROOT, enabled_only=False),
        root=ROOT,
        created_at=CREATED_AT,
        candidate_id=candidate_id,
        source_owner="@RonShub",
        source_owner_approval_ref="https://github.com/ottto-ai/ai-provider-watch/pull/96#source-owner",
    )

    _assert_schema_valid(packet)
    assert packet["verified"] is True
    assert packet["resolution"] == {
        "type": "promote",
        "candidate_id": candidate_id,
        "event_ids": ["2026-06-04-openai-codex-bedrock-workflow"],
    }
    assert packet["candidate"]["claim_text"]["included"] is False
    assert packet["event_drafts"][0]["validation"]["blockers"] == []
    assert packet["event_drafts"][0]["detail_kind"] == "generic_change"
    assert "write_data_events" in packet["policy"]["forbidden_authority"]


def test_candidate_to_event_packet_verifies_split_resolution(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _openai_candidate_id(candidate_dir)
    first_event = _event_draft(tmp_path)
    second_event = _event_draft(
        tmp_path,
        event_id="2026-06-04-openai-codex-bedrock-routing",
    )

    packet = build_candidate_to_event_packet(
        read_candidate_files(candidate_dir),
        [first_event, second_event],
        load_source_descriptors(ROOT, enabled_only=False),
        root=ROOT,
        created_at=CREATED_AT,
        candidate_id=candidate_id,
        source_owner="@RonShub",
        source_owner_approval_ref="https://github.com/ottto-ai/ai-provider-watch/pull/96#source-owner",
    )

    _assert_schema_valid(packet)
    assert packet["verified"] is True
    assert packet["resolution"]["type"] == "split"
    assert packet["resolution"]["event_ids"] == [
        "2026-06-04-openai-codex-bedrock-workflow",
        "2026-06-04-openai-codex-bedrock-routing",
    ]


def test_candidate_event_packet_allows_same_packet_duplicate_after_authoring(tmp_path) -> None:
    candidate_file = _anthropic_mythos_candidate(tmp_path)
    event_path = _existing_event_draft(
        tmp_path,
        "2026-06-09-anthropic-claude-mythos-5-trusted-access",
    )

    packet = build_candidate_to_event_packet(
        [candidate_file],
        [event_path],
        load_source_descriptors(ROOT, enabled_only=False),
        root=ROOT,
        created_at=CREATED_AT,
        candidate_id="candidate-anthropic-news-a246c9ce289c3c6b",
        source_owner="@RonShub",
        source_owner_approval_ref="https://github.com/ottto-ai/ai-provider-watch/pull/129#source-owner",
    )

    _assert_schema_valid(packet)
    assert packet["verified"] is True
    assert packet["blockers"] == []
    assert packet["candidate_quality"]["recommended_action"] == "duplicate"
    assert "2026-06-09-anthropic-claude-mythos-5-trusted-access" in packet["candidate_quality"]["duplicate_event_ids"]
    assert packet["candidate_quality"]["packet_advisories"] == [
        "Candidate quality is duplicate only because the packet event draft ids already appear in reviewed event data."
    ]


def test_candidate_event_packet_blocks_duplicate_with_unrelated_event_id(tmp_path) -> None:
    candidate_file = _anthropic_mythos_candidate(tmp_path)
    event_path = _existing_event_draft(
        tmp_path,
        "2026-06-09-anthropic-claude-mythos-5-trusted-access",
        replacement_id="2026-06-09-anthropic-claude-mythos-5-copy",
    )

    packet = build_candidate_to_event_packet(
        [candidate_file],
        [event_path],
        load_source_descriptors(ROOT, enabled_only=False),
        root=ROOT,
        created_at=CREATED_AT,
        candidate_id="candidate-anthropic-news-a246c9ce289c3c6b",
        source_owner="@RonShub",
        source_owner_approval_ref="https://github.com/ottto-ai/ai-provider-watch/pull/129#source-owner",
    )

    _assert_schema_valid(packet)
    assert packet["verified"] is False
    assert "Candidate quality action duplicate is not promotable." in packet["blockers"]


def test_candidate_event_packet_cli_writes_output(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _openai_candidate_id(candidate_dir)
    event_path = _event_draft(tmp_path)
    output_path = tmp_path / "candidate-to-event-packet.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "event-packet",
                "--candidates",
                str(candidate_dir),
                "--candidate-id",
                candidate_id,
                "--event-draft",
                str(event_path),
                "--source-owner",
                "@RonShub",
                "--source-owner-approval-ref",
                "https://github.com/ottto-ai/ai-provider-watch/pull/96#source-owner",
                "--created-at",
                CREATED_AT,
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    packet = read_json(output_path)
    _assert_schema_valid(packet)
    assert packet["verified"] is True


def test_candidate_event_packet_rejects_off_domain_evidence(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _openai_candidate_id(candidate_dir)
    event_path = _event_draft(tmp_path, evidence_url="https://example.com/not-official")
    output_path = tmp_path / "blocked-candidate-to-event-packet.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "event-packet",
                "--candidates",
                str(candidate_dir),
                "--candidate-id",
                candidate_id,
                "--event-draft",
                str(event_path),
                "--source-owner",
                "@RonShub",
                "--source-owner-approval-ref",
                "https://github.com/ottto-ai/ai-provider-watch/pull/96#source-owner",
                "--created-at",
                CREATED_AT,
                "--output",
                str(output_path),
            ]
        )
        == 1
    )

    packet = read_json(output_path)
    _assert_schema_valid(packet)
    assert packet["verified"] is False
    assert any("outside the source allowed domains" in blocker for blocker in packet["blockers"])
