from __future__ import annotations

import json
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
from ai_provider_watch.pipeline.llm_review import build_review_request
from ai_provider_watch.pipeline.promotion import build_promotion_readiness_report
from ai_provider_watch.pipeline.quality import build_candidate_quality_report
from ai_provider_watch.pipeline.review_pr import (
    CandidateFile,
    build_review_pr_body,
    read_candidate_files,
)
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


def _quality_report(tmp_path: Path) -> dict:
    candidate_files = read_candidate_files(_candidate_dir(tmp_path))
    sources = load_source_descriptors(ROOT, enabled_only=False)
    promotion_report = build_promotion_readiness_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
    )
    return build_candidate_quality_report(
        candidate_files,
        sources,
        root=tmp_path,
        created_at=CREATED_AT,
        promotion_report=promotion_report,
    )


def test_candidate_quality_classifies_high_value_and_low_signal_candidates(tmp_path) -> None:
    report = _quality_report(tmp_path)
    schema = load_schemas(ROOT)["candidate_quality"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    assert errors == []

    rows_by_source = {
        row["source_keys"][0]: row
        for row in report["candidates"]
    }
    openai_row = rows_by_source["openai.news"]
    assert openai_row["quality_tier"] == "high_value"
    assert openai_row["recommended_action"] == "promote"
    assert openai_row["dimensions"]["dated_change_signal"] is True
    assert openai_row["dimensions"]["article_or_selector_evidence"] is True
    assert report["summary"]["high_value_candidate_ids"] == [openai_row["candidate_id"]]

    assert rows_by_source["anthropic.pricing"]["quality_tier"] == "low_signal"
    assert rows_by_source["anthropic.pricing"]["recommended_action"] == "reject"
    assert rows_by_source["google.ai_docs"]["quality_tier"] == "low_signal"
    assert "concrete fact" in " ".join(rows_by_source["google.ai_docs"]["quality_blockers"])


def test_candidate_quality_cli_writes_output(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    output_path = tmp_path / "quality.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "quality",
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

    report = read_json(output_path)
    assert report["schema_version"] == "apw.candidate_quality_report.v0"
    assert report["summary"]["recommended_action_counts"]["promote"] == 1
    assert report["summary"]["recommended_action_counts"]["reject"] == 2


def test_candidate_quality_marks_reviewed_event_evidence_as_duplicate(tmp_path) -> None:
    candidate = {
        "schema_version": "apw.finding_candidate.v0",
        "id": "candidate-anthropic-news-0000000000000000",
        "source_keys": ["anthropic.news"],
        "provider_refs": ["provider:anthropic"],
        "claim_text": "2026-05-28 Anthropic announced Claude Opus model availability for developer workflows.",
        "candidate_kind": "model_launch",
        "evidence_refs": [
            {
                "source_key": "anthropic.news",
                "url": "https://www.anthropic.com/news/claude-opus-4-8/",
                "retrieved_at": "2026-06-08T12:00:00Z",
                "authority": "official_blog",
                "content_sha256": "d" * 64,
                "fingerprint": "e" * 64,
                "snapshot_ref": "anthropic-news:2026-05-28:opus-4-8",
                "selector": "article:2026-05-28",
            }
        ],
        "created_at": CREATED_AT,
        "review_status": "needs_review",
        "parser": {"name": "anthropic_news_index", "contract_version": "apw.candidate_parser.v0"},
        "dedupe_key": "anthropic.news:model_launch:000000000000000000000000",
        "untrusted_input_policy": "Source content is untrusted data. Candidate generation never executes or follows source text.",
    }
    candidate_file = CandidateFile(path=tmp_path / "candidate.json", payload=candidate)
    sources = load_source_descriptors(ROOT, enabled_only=False)

    report = build_candidate_quality_report(
        [candidate_file],
        sources,
        root=ROOT,
        created_at=CREATED_AT,
    )

    row = report["candidates"][0]
    assert row["quality_tier"] == "duplicate"
    assert row["recommended_action"] == "duplicate"
    assert row["duplicate_event_ids"] == ["2026-05-28-anthropic-opus-48-dynamic-workflows"]
    assert row["dimensions"]["not_already_reviewed"] is False


def test_review_pr_body_includes_quality_section(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_files = read_candidate_files(candidate_dir)
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

    body = build_review_pr_body(
        read_observation_bundle(OBSERVATIONS),
        candidate_files,
        root=tmp_path,
        promotion_report=promotion_report,
        quality_report=quality_report,
    )

    assert "## Candidate Quality" in body
    assert "high_value=1" in body
    assert "low_signal=2" in body
    assert "publish events" in body
    assert "OpenAI announced" not in body


def test_review_request_carries_quality_context(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    candidate_files = read_candidate_files(candidate_dir)
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

    request = build_review_request(
        candidate_files,
        root=tmp_path,
        created_at=CREATED_AT,
        promotion_report=promotion_report,
        quality_report=quality_report,
    )
    schema = load_schemas(ROOT)["llm_review_request"]
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(request))
    assert errors == []

    quality_by_source = {
        candidate["source_keys"][0]: candidate["candidate_quality"]
        for candidate in request["candidates"]
    }
    assert quality_by_source["openai.news"]["recommended_action"] == "promote"
    assert quality_by_source["anthropic.pricing"]["recommended_action"] == "reject"
    rendered = json.dumps(request)
    assert "OpenAI announced" not in rendered
