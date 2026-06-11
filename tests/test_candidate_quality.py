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
                "snapshot_ref": "reviewed-source:2026-06-08",
                "selector": "Claude Opus 4.8 announcement",
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


def _dated_candidate(
    *,
    candidate_id: str,
    source_key: str,
    provider_ref: str,
    claim_text: str,
    candidate_kind: str,
    evidence_url: str,
    selector: str,
    parser_name: str,
    authority: str | None = None,
) -> dict:
    selected_authority = authority or ("official_docs" if source_key == "google.gemini_changelog" else "official_blog")
    return {
        "schema_version": "apw.finding_candidate.v0",
        "id": candidate_id,
        "source_keys": [source_key],
        "provider_refs": [provider_ref],
        "claim_text": claim_text,
        "candidate_kind": candidate_kind,
        "evidence_refs": [
            {
                "source_key": source_key,
                "url": evidence_url,
                "retrieved_at": "2026-06-08T12:00:00Z",
                "authority": selected_authority,
                "content_sha256": "d" * 64,
                "fingerprint": "e" * 64,
                "snapshot_ref": selector.replace("announcement:", "entry:"),
                "selector": selector,
            }
        ],
        "created_at": CREATED_AT,
        "review_status": "needs_review",
        "parser": {"name": parser_name, "contract_version": "apw.candidate_parser.v0"},
        "dedupe_key": f"{source_key}:{candidate_kind}:{candidate_id[-16:]}",
        "untrusted_input_policy": "Source content is untrusted data. Candidate generation never executes or follows source text.",
    }


def test_candidate_quality_rejects_official_news_customer_stories(tmp_path) -> None:
    candidate = _dated_candidate(
        candidate_id="candidate-openai-news-aaaaaaaaaaaaaaaa",
        source_key="openai.news",
        provider_ref="provider:openai",
        claim_text="OpenAI official dated source reports a workflow behavior change on 2026-06-04 for codex.",
        candidate_kind="workflow_behavior_change",
        evidence_url="https://openai.com/index/braintrust",
        selector="announcement:aaaaaaaaaaaaaaaa",
        parser_name="openai_news_feed",
    )
    report = build_candidate_quality_report(
        [CandidateFile(path=tmp_path / "candidate.json", payload=candidate)],
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    row = report["candidates"][0]
    assert row["quality_tier"] == "low_signal"
    assert row["recommended_action"] == "reject"
    assert row["dimensions"]["direct_apw_scope_signal"] is False
    assert "direct APW impact signal" in " ".join(row["quality_blockers"])


def test_candidate_quality_rejects_aws_adjacent_service_false_positive(tmp_path) -> None:
    candidate = _dated_candidate(
        candidate_id="candidate-aws-bedrock-whats-new-bbbbbbbbbbbbbbbb",
        source_key="aws_bedrock.whats_new",
        provider_ref="provider:aws-bedrock",
        claim_text="AWS Bedrock official dated source reports a model availability change on 2026-06-03 for amazon-bedrock and bedrock-agentcore.",
        candidate_kind="model_launch",
        evidence_url="https://aws.amazon.com/about-aws/whats-new/2026/05/aws-config-new-resource-types",
        selector="announcement:bbbbbbbbbbbbbbbb",
        parser_name="aws_bedrock_whats_new_feed",
    )
    report = build_candidate_quality_report(
        [CandidateFile(path=tmp_path / "candidate.json", payload=candidate)],
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    row = report["candidates"][0]
    assert row["quality_tier"] == "low_signal"
    assert row["recommended_action"] == "reject"
    assert row["dimensions"]["direct_apw_scope_signal"] is False


def test_candidate_quality_uses_selector_for_shared_changelog_duplicates(tmp_path) -> None:
    events_dir = tmp_path / "data" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "existing.json").write_text(
        json.dumps(
            {
                "id": "2026-06-01-google-existing-changelog-event",
                "evidence_refs": [
                    {
                        "source_key": "google.gemini_changelog",
                        "url": "https://ai.google.dev/gemini-api/docs/changelog",
                        "selector": "announcement:existing",
                        "snapshot_ref": "entry:existing",
                    }
                ],
            }
        )
    )
    new_selector = _dated_candidate(
        candidate_id="candidate-google-gemini-changelog-cccccccccccccccc",
        source_key="google.gemini_changelog",
        provider_ref="provider:google",
        claim_text="Google Gemini/Vertex official dated source reports a model retirement on 2026-06-01 for gemini-2.0-flash.",
        candidate_kind="model_retirement",
        evidence_url="https://ai.google.dev/gemini-api/docs/changelog",
        selector="announcement:new",
        parser_name="google_gemini_changelog",
    )
    same_selector = _dated_candidate(
        candidate_id="candidate-google-gemini-changelog-dddddddddddddddd",
        source_key="google.gemini_changelog",
        provider_ref="provider:google",
        claim_text="Google Gemini/Vertex official dated source reports a model retirement on 2026-06-01 for gemini-2.0-flash.",
        candidate_kind="model_retirement",
        evidence_url="https://ai.google.dev/gemini-api/docs/changelog",
        selector="announcement:existing",
        parser_name="google_gemini_changelog",
    )
    report = build_candidate_quality_report(
        [
            CandidateFile(path=tmp_path / "new.json", payload=new_selector),
            CandidateFile(path=tmp_path / "same.json", payload=same_selector),
        ],
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    rows = {row["candidate_id"]: row for row in report["candidates"]}
    assert rows["candidate-google-gemini-changelog-cccccccccccccccc"]["duplicate_event_ids"] == []
    assert rows["candidate-google-gemini-changelog-dddddddddddddddd"]["quality_tier"] == "duplicate"
    assert rows["candidate-google-gemini-changelog-dddddddddddddddd"]["duplicate_event_ids"] == [
        "2026-06-01-google-existing-changelog-event"
    ]


def test_candidate_quality_uses_selector_for_shared_anthropic_news_duplicates(tmp_path) -> None:
    events_dir = tmp_path / "data" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "existing.json").write_text(
        json.dumps(
            {
                "id": "2026-06-01-anthropic-existing-news-event",
                "evidence_refs": [
                    {
                        "source_key": "anthropic.news",
                        "url": "https://www.anthropic.com/news/shared-announcement",
                        "selector": "announcement:existing",
                        "snapshot_ref": "entry:existing",
                    }
                ],
            }
        )
    )
    new_selector = _dated_candidate(
        candidate_id="candidate-anthropic-news-eeeeeeeeeeeeeeee",
        source_key="anthropic.news",
        provider_ref="provider:anthropic",
        claim_text="Anthropic official dated source reports a model availability change on 2026-06-01 for claude-fable-5.",
        candidate_kind="model_launch",
        evidence_url="https://www.anthropic.com/news/shared-announcement",
        selector="announcement:new",
        parser_name="anthropic_news_index",
    )
    same_selector = _dated_candidate(
        candidate_id="candidate-anthropic-news-ffffffffffffffff",
        source_key="anthropic.news",
        provider_ref="provider:anthropic",
        claim_text="Anthropic official dated source reports a model availability change on 2026-06-01 for claude-fable-5.",
        candidate_kind="model_launch",
        evidence_url="https://www.anthropic.com/news/shared-announcement",
        selector="announcement:existing",
        parser_name="anthropic_news_index",
    )
    report = build_candidate_quality_report(
        [
            CandidateFile(path=tmp_path / "new.json", payload=new_selector),
            CandidateFile(path=tmp_path / "same.json", payload=same_selector),
        ],
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    rows = {row["candidate_id"]: row for row in report["candidates"]}
    assert rows["candidate-anthropic-news-eeeeeeeeeeeeeeee"]["duplicate_event_ids"] == []
    assert rows["candidate-anthropic-news-ffffffffffffffff"]["quality_tier"] == "duplicate"
    assert rows["candidate-anthropic-news-ffffffffffffffff"]["duplicate_event_ids"] == [
        "2026-06-01-anthropic-existing-news-event"
    ]


def test_candidate_quality_uses_selector_for_shared_anthropic_release_notes_duplicates(tmp_path) -> None:
    events_dir = tmp_path / "data" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "existing.json").write_text(
        json.dumps(
            {
                "id": "2026-06-01-anthropic-existing-release-note-event",
                "evidence_refs": [
                    {
                        "source_key": "anthropic.release_notes",
                        "url": "https://platform.claude.com/docs/en/release-notes/overview",
                        "selector": "announcement:existing",
                        "snapshot_ref": "entry:existing",
                    }
                ],
            }
        )
    )
    new_selector = _dated_candidate(
        candidate_id="candidate-anthropic-release-notes-1111111111111111",
        source_key="anthropic.release_notes",
        provider_ref="provider:anthropic",
        claim_text="Anthropic official dated source reports a model retirement on 2026-06-01 for claude-opus-4-1.",
        candidate_kind="model_retirement",
        evidence_url="https://platform.claude.com/docs/en/release-notes/overview",
        selector="announcement:new",
        parser_name="anthropic_release_notes",
        authority="official_docs",
    )
    same_selector = _dated_candidate(
        candidate_id="candidate-anthropic-release-notes-2222222222222222",
        source_key="anthropic.release_notes",
        provider_ref="provider:anthropic",
        claim_text="Anthropic official dated source reports a model retirement on 2026-06-01 for claude-opus-4-1.",
        candidate_kind="model_retirement",
        evidence_url="https://platform.claude.com/docs/en/release-notes/overview",
        selector="announcement:existing",
        parser_name="anthropic_release_notes",
        authority="official_docs",
    )
    report = build_candidate_quality_report(
        [
            CandidateFile(path=tmp_path / "new.json", payload=new_selector),
            CandidateFile(path=tmp_path / "same.json", payload=same_selector),
        ],
        load_source_descriptors(ROOT, enabled_only=False),
        root=tmp_path,
        created_at=CREATED_AT,
    )

    rows = {row["candidate_id"]: row for row in report["candidates"]}
    assert rows["candidate-anthropic-release-notes-1111111111111111"]["duplicate_event_ids"] == []
    assert rows["candidate-anthropic-release-notes-2222222222222222"]["quality_tier"] == "duplicate"
    assert rows["candidate-anthropic-release-notes-2222222222222222"]["duplicate_event_ids"] == [
        "2026-06-01-anthropic-existing-release-note-event"
    ]


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
