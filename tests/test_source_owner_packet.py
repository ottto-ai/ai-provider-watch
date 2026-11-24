from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json, write_json_text
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.review_pr import read_candidate_files
from ai_provider_watch.pipeline.source_owner_packet import build_source_owner_packet
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


def _write_source_state(tmp_path: Path) -> None:
    state_path = tmp_path / "data" / "source-state" / "fingerprints.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        write_json_text(
            {
                "schema_version": "apw.source_fingerprints.v0",
                "sources": {
                    "openai.news": {
                        "content_sha256": "a" * 64,
                        "final_url": "https://openai.com/news/rss.xml",
                        "fingerprint": "1" * 64,
                        "http_status": 200,
                        "retrieved_at": "2026-06-08T12:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_source_owner_packet_selects_high_value_candidates(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    _write_source_state(tmp_path)
    packet = build_source_owner_packet(
        read_candidate_files(candidate_dir),
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    schema = load_schemas(ROOT)["source_owner_packet"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(packet))
    assert errors == []
    assert packet["schema_version"] == "apw.source_owner_packet.v0"
    assert packet["candidate_count"] == 1
    assert packet["source_candidate_count"] == 3
    assert packet["summary"]["dropped_candidate_count"] == 2
    assert packet["summary"]["recommended_action_counts"] == {"promote": 1}

    row = packet["candidates"][0]
    assert row["source_keys"] == ["openai.news"]
    assert row["quality"]["quality_tier"] == "high_value"
    assert row["quality"]["recommended_action"] == "promote"
    assert row["readiness"]["readiness"] == "auto_promotion_eligible"
    assert row["source_context"][0]["source_state"]["known"] is True
    assert row["source_context"][0]["source_state"]["retrieved_at"] == "2026-06-08T12:00:00Z"
    assert row["untrusted_candidate_claim"]["classification"] == "untrusted_data"
    assert "Codex availability" in row["untrusted_candidate_claim"]["text"]
    assert row["suggested_provider_event"]["publication_status"] == "draft_only_not_event_data"
    assert row["suggested_provider_event"]["envelope"]["lifecycle_status"] == "candidate"
    assert row["suggested_provider_event"]["detail_stub"]["completion_policy"] == (
        "source_owner_must_replace_stub_before_promotion"
    )
    assert "write_data_events" in packet["policy"]["forbidden_authority"]
    assert "create_or_push_release_tag" in packet["policy"]["forbidden_authority"]


def test_source_owner_packet_can_include_human_review_actions(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    packet = build_source_owner_packet(
        read_candidate_files(candidate_dir),
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
        recommended_actions={"promote", "reject"},
    )

    assert packet["candidate_count"] == 3
    assert packet["summary"]["recommended_action_counts"] == {"promote": 1, "reject": 2}
    assert {row["quality"]["recommended_action"] for row in packet["candidates"]} == {
        "promote",
        "reject",
    }


def test_candidate_packet_cli_writes_schema_valid_output(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    output_path = tmp_path / "source-owner-packet.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "packet",
                "--candidates",
                str(candidate_dir),
                "--created-at",
                CREATED_AT,
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    packet = read_json(output_path)
    schema = load_schemas(ROOT)["source_owner_packet"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(packet))
    assert errors == []
    assert packet["candidate_count"] == 1
    assert packet["summary"]["selected_candidate_ids"][0].startswith("candidate-openai-news-")
    assert packet["candidates"][0]["source_keys"] == ["openai.news"]


def test_candidate_packet_cli_prints_json_without_output(tmp_path, capsys) -> None:
    candidate_dir = _candidate_dir(tmp_path)

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "packet",
                "--candidates",
                str(candidate_dir),
                "--created-at",
                CREATED_AT,
            ]
        )
        == 0
    )

    packet = json.loads(capsys.readouterr().out)
    assert packet["schema_version"] == "apw.source_owner_packet.v0"
    assert packet["policy"]["authority"] == "source_owner_review_only"
