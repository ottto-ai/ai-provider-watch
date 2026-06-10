from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.candidate_queue import (
    build_candidate_action_queue,
    render_candidate_action_queue_markdown,
)
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.promotion import build_promotion_readiness_report
from ai_provider_watch.pipeline.quality import build_candidate_quality_report
from ai_provider_watch.pipeline.review_pr import build_review_pr_body, read_candidate_files
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


def _queue(tmp_path: Path) -> dict:
    candidate_files = read_candidate_files(_candidate_dir(tmp_path))
    sources = load_source_descriptors(ROOT, enabled_only=False)
    promotion_report = build_promotion_readiness_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
    )
    quality_report = build_candidate_quality_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
        promotion_report=promotion_report,
    )
    return build_candidate_action_queue(
        candidate_files,
        created_at=CREATED_AT,
        promotion_report=promotion_report,
        quality_report=quality_report,
    )


def test_candidate_action_queue_groups_next_actions(tmp_path) -> None:
    queue = _queue(tmp_path)
    schema = load_schemas(ROOT)["candidate_action_queue"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(queue))

    assert errors == []
    assert queue["schema_version"] == "apw.candidate_action_queue.v0"
    assert queue["candidate_count"] == 3
    assert queue["summary"]["recommended_action_counts"] == {"promote": 1, "reject": 2}
    assert queue["summary"]["promotion_ready_count"] == 1
    assert queue["groups"]["promote"][0]["candidate_id"].startswith("candidate-openai-news-")
    assert queue["groups"]["promote"][0]["evidence_refs"][0]["source_key"] == "openai.news"
    assert queue["groups"]["reject"][0]["next_step"].startswith("Close as no public APW event")
    assert "write_data_events" in queue["policy"]["forbidden_authority"]
    assert "Codex availability" not in json.dumps(queue)


def test_candidate_action_queue_markdown_is_compact_and_actionable(tmp_path) -> None:
    rendered = render_candidate_action_queue_markdown(_queue(tmp_path), limit_per_group=1)

    assert "## Action Queue" in rendered
    assert "### Promote First" in rendered
    assert "uv run apw candidate packet" in rendered
    assert "candidate-openai-news-" in rendered
    assert "1 more candidates omitted" in rendered
    assert "Codex availability" not in rendered


def test_candidate_queue_cli_writes_json_and_markdown(tmp_path, capsys) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    json_output = tmp_path / "queue.json"
    markdown_output = tmp_path / "queue.md"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "queue",
                "--candidates",
                str(candidate_dir),
                "--created-at",
                CREATED_AT,
                "--output",
                str(json_output),
            ]
        )
        == 0
    )
    assert read_json(json_output)["summary"]["promotion_ready_count"] == 1

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "queue",
                "--candidates",
                str(candidate_dir),
                "--created-at",
                CREATED_AT,
                "--markdown",
                "--limit-per-group",
                "1",
                "--output",
                str(markdown_output),
            ]
        )
        == 0
    )
    assert "Promote First" in markdown_output.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_review_pr_body_includes_action_queue_without_claim_text(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_files = read_candidate_files(candidate_dir)
    sources = load_source_descriptors(ROOT, enabled_only=False)
    observations = read_observation_bundle(OBSERVATIONS)
    promotion_report = build_promotion_readiness_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
    )
    quality_report = build_candidate_quality_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
        promotion_report=promotion_report,
    )

    body = build_review_pr_body(
        observations,
        candidate_files,
        root=tmp_path,
        validation_output="uv run apw validate: pass",
        promotion_report=promotion_report,
        quality_report=quality_report,
    )

    assert "## Action Queue" in body
    assert "### Promote First" in body
    assert "uv run apw candidate packet" in body
    assert "Codex availability" not in body
