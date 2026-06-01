from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.pipeline.candidates import build_candidates
from ai_provider_watch.pipeline.review_pr import build_review_pr_body, read_candidate_files
from ai_provider_watch.source_watch.parsers import parse_source_payload
from ai_provider_watch.sources.registry import load_source_descriptors

ROOT = Path(__file__).resolve().parents[1]
REDTEAM = ROOT / "tests" / "fixtures" / "redteam" / "untrusted-input-cases.json"
OBSERVATIONS = ROOT / "tests" / "fixtures" / "observations" / "candidate-observations.json"
CREATED_AT = "2026-05-31T20:15:00Z"
REQUIRED_SURFACES = {
    "provider_page",
    "issue_body",
    "pr_comment",
    "social_post",
    "mcp_resource",
    "generated_candidate",
}


def _redteam_cases() -> list[dict[str, str]]:
    return read_json(REDTEAM)["cases"]


def _assert_no_redteam_text(rendered: str) -> None:
    lowered = rendered.lower()
    for case in _redteam_cases():
        payload = case["payload"]
        assert payload not in rendered
    assert "ignore previous instructions" not in lowered
    assert "ignore all previous instructions" not in lowered
    assert "publish every candidate" not in lowered
    assert "merge this pr" not in lowered
    assert "release token" not in lowered
    assert "system prompt" not in lowered
    assert "developer message" not in lowered
    assert "exfiltrate" not in lowered


def test_redteam_fixture_covers_required_untrusted_surfaces() -> None:
    cases = _redteam_cases()

    assert {case["surface"] for case in cases} == REQUIRED_SURFACES
    assert all(contains_prompt_injection_marker(case["payload"]) for case in cases)


def test_provider_page_prompt_text_is_not_copied_to_parser_output() -> None:
    source = next(
        item
        for item in load_source_descriptors(ROOT, enabled_only=False)
        if item.key == "openai.pricing"
    )
    provider_page = next(
        case["payload"] for case in _redteam_cases() if case["surface"] == "provider_page"
    )

    parsed = parse_source_payload(
        source,
        f"<html><body><table><tr><td>{provider_page}</td></tr></table></body></html>".encode(),
        changed=True,
    )
    rendered = str(parsed.items) + str(parsed.candidate_claims) + str(parsed.errors)

    _assert_no_redteam_text(rendered)


def test_prompt_like_candidate_claims_are_rejected() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["candidate_claims"] = [
        {"claim_text": case["payload"], "candidate_kind": "status_incident"}
        for case in _redteam_cases()
    ]

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_candidate_review_body_sanitizes_malicious_candidate_fields(tmp_path) -> None:
    candidate_dir = tmp_path / "data" / "candidates" / "review"
    candidate_dir.mkdir(parents=True)
    malicious = next(
        case["payload"] for case in _redteam_cases() if case["surface"] == "pr_comment"
    )
    candidate = {
        "schema_version": "apw.finding_candidate.v0",
        "id": malicious,
        "source_keys": [malicious],
        "provider_refs": [malicious],
        "claim_text": malicious,
        "candidate_kind": malicious,
        "evidence_refs": [],
        "created_at": CREATED_AT,
        "review_status": "needs_review",
        "parser": {"name": "manual_review", "contract_version": "apw.candidate_parser.v0"},
        "dedupe_key": "manual:test",
        "untrusted_input_policy": malicious,
    }
    (candidate_dir / "candidate-malicious-redteam-0000000000000000.json").write_text(
        json.dumps(candidate),
        encoding="utf-8",
    )

    body = build_review_pr_body(
        read_json(OBSERVATIONS),
        read_candidate_files(candidate_dir),
        root=tmp_path,
        validation_output="uv run apw validate: failed as expected\n",
    )

    assert "<invalid-id>" in body
    assert "<invalid-kind>" in body
    _assert_no_redteam_text(body)
