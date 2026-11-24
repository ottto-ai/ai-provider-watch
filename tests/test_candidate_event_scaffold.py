# SPDX-FileCopyrightText: AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.review_pr import read_candidate_files
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


def _promote_candidate_id(candidate_dir: Path) -> str:
    candidates = read_candidate_files(candidate_dir)
    for candidate_file in candidates:
        candidate_id = candidate_file.payload.get("id")
        if isinstance(candidate_id, str) and candidate_id.startswith("candidate-openai-news-"):
            return candidate_id
    raise AssertionError("openai news candidate not found")


def _assert_schema_valid(name: str, payload: object) -> None:
    schema = load_schemas(ROOT)[name]
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda item: list(item.path),
    )
    assert errors == []


def test_candidate_scaffold_event_writes_schema_valid_draft(tmp_path, capsys) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _promote_candidate_id(candidate_dir)
    output = tmp_path / "event.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "scaffold-event",
                "--candidates",
                str(candidate_dir),
                "--candidate-id",
                candidate_id,
                "--event-date",
                "2026-06-08",
                "--title",
                "OpenAI Codex Availability Candidate",
                "--scope-ref",
                "surface:openai/codex",
                "--impact-kind",
                "availability",
                "--direction",
                "added",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == ""
    event = read_json(output)
    assert event["lifecycle_status"] == "reviewed"
    assert event["provider_refs"] == ["provider:openai"]
    assert event["event_kind"] == "workflow_behavior_change"
    assert event["detail"]["kind"] == "generic_change"
    assert event["evidence_refs"][0]["source_key"] == "openai.news"
    assert event["evidence_refs"][0]["content_sha256"]
    assert event["impacts"][0]["scope_ref"] == "surface:openai/codex"
    assert event["impacts"][0]["impact_kind"] == "availability"
    assert f"candidate:{candidate_id}" in event["tags"]
    assert "Draft generated from a review-only candidate" in event["limitations"][0]
    _assert_schema_valid("event", event)
    _assert_schema_valid("event_detail", event["detail"])
    _assert_schema_valid("impact", event["impacts"][0])


def test_candidate_scaffold_event_can_render_event_scaffold_command(tmp_path, capsys) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_id = _promote_candidate_id(candidate_dir)

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "scaffold-event",
                "--candidates",
                str(candidate_dir),
                "--candidate-id",
                candidate_id,
                "--event-date",
                "2026-06-08",
                "--format",
                "command",
                "--event-output",
                "data/events/2026-06-08-openai-codex-availability.json",
            ]
        )
        == 0
    )

    rendered = capsys.readouterr().out
    assert "uv \\" in rendered
    assert "apw \\" in rendered
    assert "event \\" in rendered
    assert "scaffold \\" in rendered
    assert "--source-key \\" in rendered
    assert "openai.news \\" in rendered
    assert "--output \\" in rendered
    assert "data/events/2026-06-08-openai-codex-availability.json" in rendered


def test_candidate_scaffold_event_rejects_missing_candidate(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "scaffold-event",
                "--candidates",
                str(tmp_path / "empty"),
                "--candidate-id",
                "candidate-openai-news-0000000000000000",
            ]
        )
        == 1
    )

    assert "candidate not found" in capsys.readouterr().err
