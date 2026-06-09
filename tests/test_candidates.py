from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.validation import load_schemas, validate
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    ensure_unique_candidate_ids,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.sources.registry import load_source_descriptors

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "tests" / "fixtures" / "observations" / "candidate-observations.json"
CREATED_AT = "2026-05-31T20:15:00Z"


def test_build_candidates_from_observation_claims() -> None:
    result = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert len(result.candidates) == 3
    assert result.skipped_observations == ["aws_bedrock.pricing"]
    assert {candidate["candidate_kind"] for candidate in result.candidates} == {
        "model_launch",
        "pricing_change",
        "status_incident",
    }

    for candidate in result.candidates:
        assert candidate["id"].startswith("candidate-")
        assert candidate["created_at"] == CREATED_AT
        assert candidate["review_status"] == "needs_review"
        assert candidate["parser"]["contract_version"] == "apw.candidate_parser.v0"
        assert "untrusted data" in candidate["untrusted_input_policy"]
        assert candidate["evidence_refs"][0]["content_sha256"]
        assert "quoted_excerpt" not in candidate["evidence_refs"][0]


def test_candidates_match_schema() -> None:
    schemas = load_schemas(ROOT)
    observations = read_json(OBSERVATIONS)
    observation_validator = Draft202012Validator(
        schemas["observation"], format_checker=FormatChecker()
    )
    for observation in observations["observations"]:
        assert not list(observation_validator.iter_errors(observation))

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )
    validator = Draft202012Validator(schemas["candidate"], format_checker=FormatChecker())
    for candidate in result.candidates:
        assert not list(validator.iter_errors(candidate))


def test_build_candidates_drops_nested_parser_payloads() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"][0]["candidate_claims"][0]["suggested_detail"] = {
        "raw_html": "<main>provider page</main>"
    }
    observations["observations"][0]["candidate_claims"][0]["suggested_impacts"] = [
        {"raw_text": "provider page"}
    ]

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    candidate = next(item for item in result.candidates if item["source_keys"] == ["openai.status"])
    assert "suggested_detail" not in candidate
    assert "suggested_impacts" not in candidate


def test_build_candidates_rejects_non_schema_claim_payloads() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["candidate_claims"] = [
        {"text": "This fallback field must not become a persisted candidate claim."},
        {"claim_text": {"raw_html": "<main>provider page</main>"}},
        {"claim_text": "short"},
        {
            "claim_text": "OpenAI status feed changed with a possible API incident update.",
            "candidate_kind": "status_incident",
        },
    ]

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert len(result.candidates) == 1
    assert result.candidates[0]["claim_text"] == (
        "OpenAI status feed changed with a possible API incident update."
    )


def test_build_candidates_marks_invalid_explicit_kind_unknown() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["candidate_claims"] = [
        {
            "claim_text": "OpenAI status feed changed with a possible API incident update.",
            "candidate_kind": "status_incident_typo",
        }
    ]

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates[0]["candidate_kind"] == "unknown"


def test_build_candidates_skips_malformed_observation_metadata() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["fingerprint"] = ""
    observations["observations"][0]["content_sha256"] = "not-a-sha"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_malformed_retrieved_at() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["retrieved_at"] = "not-a-date"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_schema_invalid_retrieved_at() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["retrieved_at"] = "2026-05-31T20:15+00:00"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_missing_final_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    del observations["observations"][0]["final_url"]

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_sanitizes_unbounded_snapshot_ref() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["snapshot_ref"] = "<html>" + ("x" * 5000)

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates[0]["evidence_refs"][0]["snapshot_ref"] is None


def test_build_candidates_keeps_pricing_row_selector_and_stable_id() -> None:
    observations = {
        "schema_version": "apw.source_observations.v0",
        "observations": [
            {
                "schema_version": "apw.observation.v0",
                "source_key": "openai.pricing",
                "retrieved_at": "2026-06-09T21:15:00Z",
                "final_url": "https://developers.openai.com/api/docs/pricing",
                "http_status": 200,
                "content_type": "text/html",
                "content_sha256": "a" * 64,
                "fingerprint": "b" * 64,
                "changed": True,
                "items": [],
                "raw_excerpt_hashes": [],
                "candidate_claims": [
                    {
                        "candidate_kind": "pricing_change",
                        "claim_text": (
                            "OpenAI official pricing table changed gpt-5.3-codex input tokens "
                            "price from $1.00 / 1M tokens to $1.25 / 1M tokens."
                        ),
                        "selector": "pricing:1234abcd5678ef90",
                        "snapshot_ref": "row:1234abcd5678ef90",
                    }
                ],
                "errors": [],
                "snapshot_ref": None,
            }
        ],
        "changed_source_keys": ["openai.pricing"],
    }

    first = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    observations["observations"][0]["fingerprint"] = "c" * 64
    second = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates

    assert first[0]["id"] == second[0]["id"]
    assert first[0]["evidence_refs"][0]["selector"] == "pricing:1234abcd5678ef90"
    assert first[0]["evidence_refs"][0]["snapshot_ref"] == "row:1234abcd5678ef90"


def test_build_candidates_skips_off_domain_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = "https://attacker.example/feed.atom"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_non_https_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = "javascript://status.openai.com/feed.atom"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_browser_ambiguous_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = (
        "https://attacker.example\\@status.openai.com/feed.atom"
    )

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_userinfo_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = (
        "https://token@status.openai.com/feed.atom"
    )

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_invalid_port_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = "https://status.openai.com:bad/feed.atom"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_whitespace_observation_url() -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [observations["observations"][0]]
    observations["observations"][0]["final_url"] = "https://status.openai.com/feed atom"

    result = build_candidates(
        observations,
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["openai.status"]


def test_build_candidates_skips_malformed_top_level_bundle() -> None:
    result = build_candidates(
        "not-an-observation-bundle",
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )

    assert result.candidates == []
    assert result.skipped_observations == ["<invalid-observation-bundle>"]


def test_candidate_generate_command_writes_review_files(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(OBSERVATIONS),
                "--output",
                str(tmp_path),
                "--created-at",
                CREATED_AT,
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_count"] == 3
    written = sorted(tmp_path.glob("*.json"))
    assert len(written) == 3
    assert read_json(written[0])["schema_version"] == "apw.finding_candidate.v0"


def test_candidate_generate_dry_run_does_not_write(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(OBSERVATIONS),
                "--output",
                str(tmp_path),
                "--created-at",
                CREATED_AT,
                "--dry-run",
            ]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)) == 3
    assert not list(tmp_path.glob("*.json"))


def test_candidate_generate_rejects_duplicate_ids(tmp_path, capsys) -> None:
    observations = read_json(OBSERVATIONS)
    observations["observations"] = [
        observations["observations"][0],
        observations["observations"][0],
    ]
    observations_path = tmp_path / "observations.json"
    observations_path.write_text(json.dumps(observations), encoding="utf-8")
    output_dir = tmp_path / "out"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(observations_path),
                "--output",
                str(output_dir),
                "--created-at",
                CREATED_AT,
                "--dry-run",
            ]
        )
        == 1
    )
    assert "duplicate candidate id(s)" in capsys.readouterr().err
    assert not output_dir.exists()


def test_write_candidate_files_rejects_duplicate_ids(tmp_path) -> None:
    candidates = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    duplicate_candidates = [candidates[0], candidates[0]]

    with pytest.raises(ValueError, match="duplicate candidate id"):
        ensure_unique_candidate_ids(duplicate_candidates)
    with pytest.raises(ValueError, match="duplicate candidate id"):
        write_candidate_files(tmp_path, duplicate_candidates, clean=False)
    assert not list(tmp_path.glob("*.json"))


def test_write_candidate_files_rejects_existing_files_without_clean(tmp_path) -> None:
    candidates = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    written = write_candidate_files(tmp_path, candidates, clean=False)
    first_path = written[0]
    first_path.write_text('{"review_status":"promoted"}\n', encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exist"):
        write_candidate_files(tmp_path, candidates, clean=False)

    assert read_json(first_path) == {"review_status": "promoted"}


def test_candidate_generate_rejects_existing_files_without_clean(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(OBSERVATIONS),
                "--output",
                str(tmp_path),
                "--created-at",
                CREATED_AT,
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(OBSERVATIONS),
                "--output",
                str(tmp_path),
                "--created-at",
                CREATED_AT,
            ]
        )
        == 1
    )
    assert "already exist" in capsys.readouterr().err


def test_candidate_generate_handles_malformed_top_level_bundle(tmp_path, capsys) -> None:
    observations_path = tmp_path / "observations.json"
    observations_path.write_text('"not-an-observation-bundle"', encoding="utf-8")
    output_dir = tmp_path / "out"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(observations_path),
                "--output",
                str(output_dir),
                "--created-at",
                CREATED_AT,
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_count"] == 0
    assert payload["skipped_observations"] == ["<invalid-observation-bundle>"]


def test_candidate_generate_rejects_invalid_created_at(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "generate",
                "--observations",
                str(OBSERVATIONS),
                "--output",
                str(tmp_path),
                "--created-at",
                "today",
            ]
        )
        == 1
    )
    assert "created_at must be an RFC 3339 date-time" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.json"))


def test_build_candidates_rejects_invalid_created_at() -> None:
    with pytest.raises(ValueError, match="created_at must be an RFC 3339 date-time"):
        build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at="2026-05-31T20:15:00",
        )


def test_build_candidates_rejects_schema_invalid_created_at() -> None:
    with pytest.raises(ValueError, match="created_at must be an RFC 3339 date-time"):
        build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at="2026-05-31T20:15+00:00",
        )


def test_observation_schema_rejects_overlong_string_claim() -> None:
    schemas = load_schemas(ROOT)
    observation = read_json(OBSERVATIONS)["observations"][0]
    observation["candidate_claims"] = ["x" * 2001]
    validator = Draft202012Validator(schemas["observation"], format_checker=FormatChecker())

    assert list(validator.iter_errors(observation))


def test_observation_schema_rejects_nested_candidate_payload() -> None:
    schemas = load_schemas(ROOT)
    observation = read_json(OBSERVATIONS)["observations"][0]
    observation["candidate_claims"] = [
        {
            "claim_text": "OpenAI status feed changed with a possible API incident update.",
            "candidate_kind": "status_incident",
            "suggested_detail": {"raw_html": "<main>provider page</main>"},
        }
    ]
    validator = Draft202012Validator(schemas["observation"], format_checker=FormatChecker())

    assert list(validator.iter_errors(observation))


def test_observation_schema_rejects_invalid_candidate_kind() -> None:
    schemas = load_schemas(ROOT)
    observation = read_json(OBSERVATIONS)["observations"][0]
    observation["candidate_claims"][0]["candidate_kind"] = "status_incident_typo"
    validator = Draft202012Validator(schemas["observation"], format_checker=FormatChecker())

    assert list(validator.iter_errors(observation))


def test_observation_schema_rejects_unbounded_evidence_metadata() -> None:
    schemas = load_schemas(ROOT)
    observation = read_json(OBSERVATIONS)["observations"][0]
    observation["fingerprint"] = "raw-html-is-not-a-fingerprint"
    observation["snapshot_ref"] = "<html>" + ("x" * 5000)
    validator = Draft202012Validator(schemas["observation"], format_checker=FormatChecker())

    assert list(validator.iter_errors(observation))


def test_candidate_schema_rejects_nested_parser_payload() -> None:
    schemas = load_schemas(ROOT)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["suggested_detail"] = {"raw_html": "<main>provider page</main>"}
    validator = Draft202012Validator(schemas["candidate"], format_checker=FormatChecker())

    assert list(validator.iter_errors(candidate))


def test_candidate_schema_rejects_unbounded_evidence_metadata() -> None:
    schemas = load_schemas(ROOT)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["fingerprint"] = "raw-html-is-not-a-fingerprint"
    candidate["evidence_refs"][0]["snapshot_ref"] = "<html>" + ("x" * 5000)
    validator = Draft202012Validator(schemas["candidate"], format_checker=FormatChecker())

    assert list(validator.iter_errors(candidate))


def test_validate_reports_malformed_candidate_evidence_without_crashing(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"] = ["not-an-object"]
    (candidate_dir / "bad-candidate.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("candidate at evidence_refs.0" in issue for issue in issues)


def test_validate_reports_malformed_candidate_evidence_source_key_without_crashing(
    tmp_path,
) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["source_key"] = []
    (candidate_dir / "bad-source-key.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("candidate at evidence_refs.0.source_key" in issue for issue in issues)


def test_validate_reports_malformed_candidate_shape_without_crashing(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "not-an-object.json").write_text("[]", encoding="utf-8")

    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["provider_refs"] = 1
    candidate["source_keys"] = 1
    candidate["evidence_refs"] = 1
    (candidate_dir / "bad-fields.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("not-an-object.json: candidate" in issue for issue in issues)
    assert any("bad-fields.json: candidate at provider_refs" in issue for issue in issues)
    assert any("bad-fields.json: candidate at source_keys" in issue for issue in issues)
    assert any("bad-fields.json: candidate at evidence_refs" in issue for issue in issues)


def test_validate_reports_malformed_candidate_created_at(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["created_at"] = "today"
    (candidate_dir / "bad-created-at.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("candidate created_at must be RFC 3339 date-time" in issue for issue in issues)


def test_validate_reports_malformed_candidate_evidence_retrieved_at(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["retrieved_at"] = "2026-05-31T20:15:00"
    (candidate_dir / "bad-retrieved-at.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("evidence_refs.0.retrieved_at must be RFC 3339 date-time" in issue for issue in issues)


def test_validate_reports_off_domain_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "https://attacker.example/feed.atom"
    (candidate_dir / "off-domain.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_non_https_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "file://status.openai.com/feed.atom"
    (candidate_dir / "bad-scheme.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_browser_ambiguous_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = (
        "https://attacker.example\\@status.openai.com/feed.atom"
    )
    (candidate_dir / "ambiguous-url.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_userinfo_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "https://token@status.openai.com/feed.atom"
    (candidate_dir / "userinfo-url.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_malformed_candidate_evidence_url_without_crashing(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "https://[not-ip]/"
    (candidate_dir / "malformed-url.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_invalid_port_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "https://status.openai.com:bad/feed.atom"
    (candidate_dir / "invalid-port-url.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_whitespace_candidate_evidence_url(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["url"] = "https://status.openai.com/feed atom"
    (candidate_dir / "whitespace-url.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_malformed_source_allowed_domain_item_with_candidate(
    tmp_path,
) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    registry_path = tmp_path / "sources" / "registry.json"
    registry = read_json(registry_path)
    for source in registry["sources"]:
        if source["key"] == "openai.status":
            source["allowed_domains"] = [123]
            break
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = next(
        item
        for item in build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at=CREATED_AT,
        ).candidates
        if item["source_keys"] == ["openai.status"]
    )
    (candidate_dir / "bad-source-domain.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("allowed_domains" in issue for issue in issues)
    assert any("outside allowed domains" in issue for issue in issues)


def test_validate_reports_candidate_evidence_authority_mismatch(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    candidate["evidence_refs"][0]["authority"] = "community_hint"
    (candidate_dir / "bad-authority.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("evidence authority does not match source" in issue for issue in issues)


def test_validate_reports_candidate_evidence_source_mismatch(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = next(
        item
        for item in build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at=CREATED_AT,
        ).candidates
        if item["source_keys"] == ["openai.status"]
    )
    candidate["evidence_refs"][0]["source_key"] = "anthropic.pricing"
    (candidate_dir / "bad-evidence-source.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("is not declared in source_keys" in issue for issue in issues)


def test_validate_reports_candidate_provider_ref_mismatch(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = next(
        item
        for item in build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at=CREATED_AT,
        ).candidates
        if item["source_keys"] == ["openai.status"]
    )
    candidate["provider_refs"] = ["provider:anthropic"]
    (candidate_dir / "bad-provider-ref.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("is not declared by candidate evidence sources" in issue for issue in issues)


def test_validate_reports_unused_candidate_source_key_bypass(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = next(
        item
        for item in build_candidates(
            read_observation_bundle(OBSERVATIONS),
            load_source_descriptors(ROOT, enabled_only=False),
            created_at=CREATED_AT,
        ).candidates
        if item["source_keys"] == ["openai.status"]
    )
    candidate["source_keys"].append("anthropic.pricing")
    candidate["provider_refs"] = ["provider:anthropic"]
    (candidate_dir / "unused-source-key.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("source_keys must match evidence source keys" in issue for issue in issues)
    assert any("is not declared by candidate evidence sources" in issue for issue in issues)


def test_validate_reports_duplicate_candidate_ids(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    candidate_dir = tmp_path / "data" / "candidates"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidate = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates[0]
    (candidate_dir / "one.json").write_text(json.dumps(candidate), encoding="utf-8")
    (candidate_dir / "two.json").write_text(json.dumps(candidate), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any(f"duplicate candidate id {candidate['id']}" in issue for issue in issues)
