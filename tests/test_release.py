from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.release import (
    _is_working_tree_clean,
    build_release_automation_readiness,
    build_release_publication_packet,
    calver_release_id,
    parse_release_id_date,
    run_release_dry_run,
    verify_release_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
DUMMY_SHA = "0123456789abcdef0123456789abcdef01234567"
REVIEWED_EVENT_ID = "2026-06-04-openai-codex-compaction-latency"


def _assert_publication_packet_schema(packet: dict) -> None:
    schema = load_schemas(ROOT)["release_publication_packet"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(packet), key=lambda item: list(item.path))
    assert errors == []


def _packet_kwargs(report_path: Path) -> dict:
    return {
        "dry_run_report_path": report_path,
        "release_manager": "@RonShub",
        "source_owner": "@RonShub",
        "source_owner_approval_ref": "https://github.com/ottto-ai/ai-provider-watch/pull/1#source-owner",
        "release_manager_approval_ref": "https://github.com/ottto-ai/ai-provider-watch/pull/1#release-manager",
        "branch_protection_ref": "gh api repos/ottto-ai/ai-provider-watch/branches/main/protection",
        "ci_ref": "https://github.com/ottto-ai/ai-provider-watch/actions/runs/ci",
        "codeql_workflow_ref": "https://github.com/ottto-ai/ai-provider-watch/actions/runs/codeql",
        "code_scanning_ref": "code-scanning-analysis:123",
        "dependency_review_ref": "https://github.com/ottto-ai/ai-provider-watch/actions/runs/dependency-review",
        "scorecard_ref": "https://github.com/ottto-ai/ai-provider-watch/actions/runs/scorecard",
        "attestation_ref": "gh attestation verify .apw/apw-release-dry-run.tgz --repo ottto-ai/ai-provider-watch",
        "checksum_review_ref": "data/releases/data-2026.06.01/checksums.txt",
    }


def test_calver_release_id() -> None:
    assert calver_release_id(date(2026, 6, 1)) == "data-2026.06.01"
    assert parse_release_id_date("data-2026.06.01") == date(2026, 6, 1)
    assert parse_release_id_date("data-2026.06.01.1") == date(2026, 6, 1)
    assert parse_release_id_date("data-2026.06.01.12") == date(2026, 6, 1)


def test_release_dry_run_writes_report_and_release_artifacts(tmp_path) -> None:
    result = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    assert result.failed_checks == []
    assert result.report["release_id"] == "data-2026.06.01"
    assert result.report["source_commit"] == DUMMY_SHA
    assert "uv lock --check" in result.report["validation_commands"]
    assert "uv run apw source coverage --summary" in result.report["validation_commands"]
    assert "uv run apw source catalog --summary" in result.report["validation_commands"]
    assert "uv run apw operations report --summary" in result.report["validation_commands"]
    assert "uv run apw operations launch-gate --summary" in result.report["validation_commands"]
    assert "uv run apw release automation-readiness --summary" in result.report["validation_commands"]
    assert "actionlint .github/workflows/*.yml" in result.report["validation_commands"]
    assert result.report_path.exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert {check["name"] for check in report["checks"]} >= {
        "release_id_calver",
        "schema_and_repo_validation",
        "source_coverage_report",
        "source_catalog",
        "operations_report",
        "v1_launch_gate",
        "release_automation_readiness",
        "generated_dev_artifacts_current",
        "release_manifest_schema",
        "release_checksums",
        "license_layout",
        "dependency_lock",
        "codeql_workflow",
        "dependency_review_workflow",
        "release_workflow_guardrails",
        "data_publisher_noop_workflow",
        "source_refresh_token_boundary",
        "scorecard_workflow",
        "source_ownership",
        "maintainer_release_docs",
        "release_evidence_index_schema",
        "dry_run_report_schema",
    }
    assert {check["name"] for check in report["external_required_checks"]} == {
        "Artifact checksum review",
        "Artifact attestation verification",
        "Branch protection",
        "CI test workflow",
        "CodeQL analyze workflow",
        "CodeQL code-scanning analysis",
        "Dependency Review",
        "Maintainer release approval",
        "OpenSSF Scorecard",
        "Protected data publisher",
        "Repository security settings",
        "Release token separation",
        "Signed data tag",
    }
    manifest_path = (
        result.output_dir
        / "artifacts"
        / "data"
        / "releases"
        / "data-2026.06.01"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["release_id"] == "data-2026.06.01"
    assert manifest["source_commit"] == DUMMY_SHA
    assert "data/feeds/coverage.json" in manifest["checksums"]
    assert "data/feeds/source-catalog.json" in manifest["checksums"]
    assert "data/feeds/feed.json" in manifest["checksums"]
    assert "data/feeds/events.json" in manifest["checksums"]
    assert "data/feeds/operations.json" in manifest["checksums"]
    assert "data/releases/data-2026.06.01/evidence-index.json" in manifest["checksums"]
    evidence_index_path = (
        result.output_dir
        / "artifacts"
        / "data"
        / "releases"
        / "data-2026.06.01"
        / "evidence-index.json"
    )
    evidence_index = json.loads(evidence_index_path.read_text(encoding="utf-8"))
    schema = load_schemas(ROOT)["release_evidence_index"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(evidence_index)) == []
    assert evidence_index["schema_version"] == "apw.release_evidence_index.v0"
    assert any(item["name"] == "source catalog" for item in evidence_index["local_verification"])
    assert any(item["name"] == "operations report" for item in evidence_index["local_verification"])
    assert any(item["name"] == "v1 launch gate" for item in evidence_index["local_verification"])
    assert any(item["name"] == "OpenSSF Scorecard" for item in evidence_index["external_evidence"])
    assert evidence_index["token_boundary"]["no_release_tokens_in_untrusted_lanes"] is True


def test_release_dry_run_supports_same_day_revision_release_id(tmp_path) -> None:
    result = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        release_id="data-2026.06.01.1",
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    assert result.failed_checks == []
    assert result.report["release_id"] == "data-2026.06.01.1"
    assert result.report_path == tmp_path / "data-2026.06.01.1" / "dry-run-report.json"
    manifest_path = (
        result.output_dir
        / "artifacts"
        / "data"
        / "releases"
        / "data-2026.06.01.1"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["release_id"] == "data-2026.06.01.1"
    assert "data/releases/data-2026.06.01.1/evidence-index.json" in manifest["checksums"]


def test_release_automation_readiness_reports_signing_equivalence_blocker() -> None:
    report = build_release_automation_readiness(
        ROOT,
        created_at="2026-06-10T00:00:00Z",
    )

    schema = load_schemas(ROOT)["release_automation_readiness"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(report)) == []
    assert report["schema_version"] == "apw.release_automation_readiness.v0"
    assert report["status"] == "blocked"
    assert report["summary"]["blocking_decision"] == "signing_equivalence_not_approved"
    assert report["summary"]["fail_count"] == 0
    assert report["summary"]["decision_blocker_count"] == 2
    assert {check["id"] for check in report["checks"]} >= {
        "data_publisher_noop_or_packet_only",
        "release_dry_run_attestation_only",
        "untrusted_lanes_have_no_release_authority",
        "manual_signed_tag_baseline_documented",
        "future_automation_graduation_tests_documented",
    }
    assert {blocker["id"] for blocker in report["decision_blockers"]} == {
        "protected_environment_verification",
        "signing_equivalence",
    }
    assert report["token_boundary"]["publisher_has_release_authority"] is False
    assert report["token_boundary"]["no_release_tokens_in_untrusted_lanes"] is True


def test_release_publication_packet_requires_reviewed_inputs(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    packet = build_release_publication_packet(
        ROOT,
        **_packet_kwargs(dry_run.report_path),
        reviewed_event_ids=[REVIEWED_EVENT_ID],
    )

    _assert_publication_packet_schema(packet)
    assert packet["publication_decision"] == "publish"
    assert packet["release_id"] == "data-2026.06.01"
    assert packet["source_commit"] == DUMMY_SHA
    assert packet["reviewed_inputs"]["reviewed_event_ids"] == [REVIEWED_EVENT_ID]
    assert packet["reviewed_inputs"]["source_owner"] == "@RonShub"
    assert packet["required_external_evidence"]["dependency_review_ref"]
    assert packet["required_external_evidence"]["scorecard_ref"]
    assert packet["signing"]["mechanism"] == "manual_release_manager_signed_git_tag"
    assert packet["signing"]["tag_name"] == "data-2026.06.01"
    assert packet["token_boundary"]["publisher_workflow_mode"] == "protected_main_noop_or_packet_only"
    assert packet["token_boundary"]["no_release_tokens_in_untrusted_lanes"] is True


def test_release_publication_packet_supports_same_day_revision_tag(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        release_id="data-2026.06.01.1",
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    packet = build_release_publication_packet(
        ROOT,
        **_packet_kwargs(dry_run.report_path),
        reviewed_event_ids=[REVIEWED_EVENT_ID],
    )

    _assert_publication_packet_schema(packet)
    assert packet["release_id"] == "data-2026.06.01.1"
    assert packet["signing"]["tag_name"] == "data-2026.06.01.1"


def test_release_verify_checks_dry_run_artifacts(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    result = verify_release_artifacts(
        ROOT,
        dry_run_report_path=dry_run.report_path,
        expected_release_id="data-2026.06.01",
        expected_source_commit=DUMMY_SHA,
    )

    assert result.failed_checks == []
    assert result.report["verified"] is True
    assert result.report["release_id"] == "data-2026.06.01"
    assert {check["name"] for check in result.report["checks"]} >= {
        "dry_run_report_schema",
        "dry_run_report_checks",
        "release_artifact_files",
        "release_manifest_and_checksums",
        "publication_packet",
    }
    assert any(artifact["path"] == "data/feeds/feed.json" for artifact in result.report["verified_artifacts"])
    assert any(
        artifact["path"] == "data/feeds/operations.json"
        for artifact in result.report["verified_artifacts"]
    )
    assert any(
        artifact["path"] == "data/feeds/source-catalog.json"
        for artifact in result.report["verified_artifacts"]
    )


def test_release_verify_checks_publication_packet(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )
    packet = build_release_publication_packet(
        ROOT,
        **_packet_kwargs(dry_run.report_path),
        reviewed_event_ids=[REVIEWED_EVENT_ID],
    )
    packet_path = tmp_path / "publication-packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    result = verify_release_artifacts(
        ROOT,
        dry_run_report_path=dry_run.report_path,
        publication_packet_path=packet_path,
        require_publish_packet=True,
    )

    assert result.failed_checks == []
    assert result.report["publication_packet_path"].endswith("publication-packet.json")
    assert result.report["verified"] is True


def test_release_verify_detects_tampered_artifact(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )
    events_path = dry_run.output_dir / "artifacts" / "data" / "feeds" / "events.json"
    events_path.write_text("[]\n", encoding="utf-8")

    result = verify_release_artifacts(ROOT, dry_run_report_path=dry_run.report_path)

    assert result.report["verified"] is False
    assert any(check.name == "release_artifact_files" for check in result.failed_checks)


def test_release_publication_packet_supports_no_event_skip_packet(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    packet = build_release_publication_packet(
        ROOT,
        **_packet_kwargs(dry_run.report_path),
        reviewed_event_ids=[],
        allow_no_reviewed_events=True,
        no_reviewed_events_reason="No source-owner-reviewed ProviderEvent changes landed for this release date.",
    )

    _assert_publication_packet_schema(packet)
    assert packet["publication_decision"] == "skip"
    assert packet["reviewed_inputs"]["reviewed_event_ids"] == []
    assert "No source-owner-reviewed" in packet["reviewed_inputs"]["no_reviewed_events_reason"]


def test_release_publication_packet_rejects_missing_reviewed_event_or_failed_dry_run(tmp_path) -> None:
    dry_run = run_release_dry_run(
        ROOT,
        release_date=date(2026, 6, 1),
        output_dir=tmp_path,
        source_commit=DUMMY_SHA,
    )

    with pytest.raises(ValueError, match="at least one --reviewed-event"):
        build_release_publication_packet(
            ROOT,
            **_packet_kwargs(dry_run.report_path),
            reviewed_event_ids=[],
        )

    with pytest.raises(ValueError, match="reviewed event id"):
        build_release_publication_packet(
            ROOT,
            **_packet_kwargs(dry_run.report_path),
            reviewed_event_ids=["missing-event"],
        )

    failed_report = json.loads(dry_run.report_path.read_text(encoding="utf-8"))
    failed_report["checks"][0]["status"] = "fail"
    failed_path = tmp_path / "failed-report.json"
    failed_path.write_text(json.dumps(failed_report), encoding="utf-8")
    with pytest.raises(ValueError, match="failed checks"):
        build_release_publication_packet(
            ROOT,
            **_packet_kwargs(failed_path),
            reviewed_event_ids=[REVIEWED_EVENT_ID],
        )


def test_release_dry_run_rejects_non_calver_release_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="release_id must match data-YYYY.MM.DD"):
        run_release_dry_run(
            ROOT,
            release_date=date(2026, 6, 1),
            release_id="../dev",
            output_dir=tmp_path,
            source_commit=DUMMY_SHA,
        )
    with pytest.raises(ValueError, match="release_id must match data-YYYY.MM.DD"):
        parse_release_id_date("data-2026.06.01.0")
    with pytest.raises(ValueError, match="release_id must match data-YYYY.MM.DD"):
        parse_release_id_date("data-2026.06.01.01")
    assert not any(tmp_path.iterdir())


def test_release_dry_run_rejects_invalid_or_mismatched_release_id_dates(tmp_path) -> None:
    with pytest.raises(ValueError, match="valid calendar date"):
        parse_release_id_date("data-2026.99.99")

    with pytest.raises(ValueError, match="release_id date must match release_date"):
        run_release_dry_run(
            ROOT,
            release_date=date(2026, 6, 1),
            release_id="data-2026.05.31",
            output_dir=tmp_path,
            source_commit=DUMMY_SHA,
        )
    assert not any(tmp_path.iterdir())


def test_working_tree_clean_check_rejects_untracked_files(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text(".apw/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=APW Test",
            "-c",
            "user.email=apw-test@example.invalid",
            "commit",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert _is_working_tree_clean(tmp_path)
    (tmp_path / ".apw").mkdir()
    (tmp_path / ".apw" / "ignored.json").write_text("{}", encoding="utf-8")
    assert _is_working_tree_clean(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "untracked-event.json").write_text("{}", encoding="utf-8")
    assert not _is_working_tree_clean(tmp_path)
