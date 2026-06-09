from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.source_watch.http import SourceObservation
from ai_provider_watch.source_watch.parsers import ParsedSourcePayload

ROOT = Path(__file__).resolve().parents[1]


def test_latest_outputs_json(capsys) -> None:
    assert main(["--root", str(ROOT), "latest"]) == 0
    events = json.loads(capsys.readouterr().out)
    event_ids = {event["id"] for event in events}
    assert "2026-06-01-google-vertex-gemini-2-0-flash-retirement" in event_ids


def test_validate_command(capsys) -> None:
    assert main(["--root", str(ROOT), "validate"]) == 0
    assert "ok: validated" in capsys.readouterr().out


def test_freshness_outputs_json(capsys) -> None:
    assert main(["--root", str(ROOT), "freshness"]) == 0
    freshness = json.loads(capsys.readouterr().out)
    assert freshness["schema_version"] == "apw.feed_freshness.v0"
    assert freshness["release_id"] == "dev"
    assert freshness["release_artifacts"]["checksums_path"] == "data/releases/dev/checksums.txt"


def test_freshness_summary(capsys) -> None:
    assert main(["--root", str(ROOT), "freshness", "--summary"]) == 0
    output = capsys.readouterr().out
    assert "release_id: dev" in output
    assert "checksums_path: data/releases/dev/checksums.txt" in output


def test_source_coverage_outputs_json(capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "source",
                "coverage",
                "--created-at",
                "2026-06-08T12:00:00Z",
            ]
        )
        == 0
    )
    coverage = json.loads(capsys.readouterr().out)
    assert coverage["schema_version"] == "apw.source_coverage.v0"
    assert coverage["summary"]["source_count"] == 19
    assert coverage["summary"]["missing_enabled_source_count"] == 8
    assert coverage["candidate_backlog"]["by_status"] == {"needs_review": 9}


def test_source_coverage_summary(capsys) -> None:
    assert main(["--root", str(ROOT), "source", "coverage", "--summary"]) == 0
    output = capsys.readouterr().out
    assert "enabled_deterministic_source_count: 18" in output
    assert "missing_enabled_source_count: 8" in output
    assert "candidate_backlog_count: 9" in output


def test_source_fetch_excludes_disabled_source_by_default(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "source",
                "fetch",
                "--source",
                "openai.codex_docs",
                "--observations",
                str(tmp_path / "observations.json"),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["source_count"] == 0
    observations = json.loads((tmp_path / "observations.json").read_text(encoding="utf-8"))
    assert observations["observations"] == []


def test_source_fetch_include_disabled_is_smoke_only(tmp_path, monkeypatch, capsys) -> None:
    def fake_fetch(source, previous_state, *, timeout, limit_bytes):
        return SourceObservation(
            source_key=source.key,
            retrieved_at="2026-06-09T20:45:00Z",
            final_url=source.url,
            http_status=200,
            content_type="text/html",
            content_sha256="a" * 64,
            fingerprint="b" * 64,
            changed=True,
            parsed=ParsedSourcePayload(
                items=[],
                raw_excerpt_hashes=[],
                candidate_claims=[],
                errors=[],
                snapshot_ref=None,
            ),
        )

    monkeypatch.setattr("ai_provider_watch.cli.fetch_source", fake_fetch)

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "source",
                "fetch",
                "--include-disabled",
                "--source",
                "openai.codex_docs",
                "--observations",
                str(tmp_path / "observations.json"),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["source_count"] == 1
    observations = json.loads((tmp_path / "observations.json").read_text(encoding="utf-8"))
    assert observations["observations"][0]["source_key"] == "openai.codex_docs"


def test_source_fetch_include_disabled_rejects_write_state(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "source",
                "fetch",
                "--include-disabled",
                "--write-state",
                "--source",
                "openai.codex_docs",
                "--observations",
                str(tmp_path / "observations.json"),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "--include-disabled is maintainer-smoke only" in captured.err


def test_source_fetch_include_disabled_requires_source(capsys) -> None:
    assert main(["--root", str(ROOT), "source", "fetch", "--include-disabled"]) == 1

    captured = capsys.readouterr()
    assert "--include-disabled requires at least one --source" in captured.err


def test_release_dry_run_command(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "dry-run",
                "--release-date",
                "2026-06-01",
                "--source-commit",
                "0123456789abcdef0123456789abcdef01234567",
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["release_id"] == "data-2026.06.01"
    assert output["artifact_count"] > 0


def test_release_packet_command(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "dry-run",
                "--release-date",
                "2026-06-01",
                "--source-commit",
                "0123456789abcdef0123456789abcdef01234567",
                "--output",
                str(tmp_path / "dry-run"),
            ]
        )
        == 0
    )
    capsys.readouterr()

    report_path = tmp_path / "dry-run" / "data-2026.06.01" / "dry-run-report.json"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "packet",
                "--dry-run-report",
                str(report_path),
                "--release-manager",
                "@RonShub",
                "--source-owner",
                "@RonShub",
                "--source-owner-approval-ref",
                "https://github.com/ottto-ai/ai-provider-watch/pull/1#source-owner",
                "--release-manager-approval-ref",
                "https://github.com/ottto-ai/ai-provider-watch/pull/1#release-manager",
                "--branch-protection-ref",
                "gh api repos/ottto-ai/ai-provider-watch/branches/main/protection",
                "--ci-ref",
                "https://github.com/ottto-ai/ai-provider-watch/actions/runs/ci",
                "--codeql-workflow-ref",
                "https://github.com/ottto-ai/ai-provider-watch/actions/runs/codeql",
                "--code-scanning-ref",
                "code-scanning-analysis:123",
                "--dependency-review-ref",
                "https://github.com/ottto-ai/ai-provider-watch/actions/runs/dependency-review",
                "--attestation-ref",
                "gh attestation verify .apw/apw-release-dry-run.tgz --repo ottto-ai/ai-provider-watch",
                "--checksum-review-ref",
                "data/releases/data-2026.06.01/checksums.txt",
                "--reviewed-event",
                "2026-06-04-openai-codex-compaction-latency",
            ]
        )
        == 0
    )
    packet = json.loads(capsys.readouterr().out)
    assert packet["schema_version"] == "apw.release_publication_packet.v0"
    assert packet["publication_decision"] == "publish"
    assert packet["signing"]["tag_name"] == "data-2026.06.01"


def test_release_verify_command(tmp_path, capsys) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "dry-run",
                "--release-date",
                "2026-06-01",
                "--source-commit",
                "0123456789abcdef0123456789abcdef01234567",
                "--output",
                str(tmp_path / "dry-run"),
            ]
        )
        == 0
    )
    capsys.readouterr()

    report_path = tmp_path / "dry-run" / "data-2026.06.01" / "dry-run-report.json"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "release",
                "verify",
                "--dry-run-report",
                str(report_path),
                "--release-id",
                "data-2026.06.01",
                "--source-commit",
                "0123456789abcdef0123456789abcdef01234567",
            ]
        )
        == 0
    )
    verification = json.loads(capsys.readouterr().out)
    assert verification["schema_version"] == "apw.release_verification.v0"
    assert verification["verified"] is True
    assert any(artifact["path"] == "data/feeds/feed.json" for artifact in verification["verified_artifacts"])
