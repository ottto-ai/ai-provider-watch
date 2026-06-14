from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.live import (
    DEFAULT_LIVE_BASE_URL,
    build_live_artifacts,
    live_artifact_url,
    validate_live_artifacts,
    write_live_artifacts,
)
from ai_provider_watch.sources.registry import load_source_descriptors

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "tests" / "fixtures" / "observations" / "candidate-observations.json"
CREATED_AT = "2026-06-14T12:00:00Z"


def _candidate_dir(tmp_path: Path) -> Path:
    result = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    )
    candidate_dir = tmp_path / "candidates"
    write_candidate_files(candidate_dir, result.candidates, clean=True)
    return candidate_dir


def test_live_artifacts_include_lenient_official_candidates(tmp_path) -> None:
    candidate_dir = _candidate_dir(tmp_path)
    output_dir = tmp_path / "live"
    result = build_live_artifacts(
        ROOT,
        candidate_dir=candidate_dir,
        observations_path=OBSERVATIONS,
        created_at=CREATED_AT,
        limit=100,
    )
    write_live_artifacts(output_dir, result.artifacts)

    assert validate_live_artifacts(ROOT, output_dir) == []
    latest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    states_by_kind = {
        item["event_kind"]: item["state"]
        for item in latest["items"]
        if item["derived_from"]["kind"] == "finding_candidate"
    }
    assert states_by_kind["status_incident"] == "automated"
    assert states_by_kind["pricing_change"] == "needs_followup"
    assert states_by_kind["model_launch"] == "needs_followup"
    assert any(item["state"] == "promoted" for item in latest["items"])

    health = json.loads((output_dir / "health.json").read_text(encoding="utf-8"))
    assert health["status"] == "ok"
    assert health["source"]["observation_count"] == 4
    assert health["source"]["changed_source_count"] == 3
    assert health["source"]["candidate_count"] == 3
    assert health["items"]["automated"] == 1
    assert health["items"]["needs_followup"] == 2

    schemas = load_schemas(ROOT)
    for item in latest["items"]:
        assert not list(
            Draft202012Validator(
                schemas["live_event"],
                format_checker=FormatChecker(),
            ).iter_errors(item)
        )


def test_live_cli_build_gate_latest_and_health(tmp_path, capsys) -> None:
    output_dir = tmp_path / "live"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "live",
                "build",
                "--output",
                str(output_dir),
                "--created-at",
                CREATED_AT,
                "--limit",
                "3",
            ]
        )
        == 0
    )
    build_output = json.loads(capsys.readouterr().out)
    assert build_output["artifact_count"] == 8
    assert build_output["item_count"] == 3

    assert main(["--root", str(ROOT), "live", "gate", "--input", str(output_dir), "--summary"]) == 0
    gate_output = capsys.readouterr().out
    assert "status: ok" in gate_output
    assert "item_count: 3" in gate_output

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "live",
                "latest",
                "--input",
                str(output_dir / "latest.json"),
                "--limit",
                "2",
            ]
        )
        == 0
    )
    latest = json.loads(capsys.readouterr().out)
    assert len(latest) == 2
    assert all(item["schema_version"] == "apw.live_event.v0" for item in latest)

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "live",
                "health",
                "--input",
                str(output_dir / "health.json"),
                "--summary",
            ]
        )
        == 0
    )
    assert "promoted:" in capsys.readouterr().out


def test_live_cli_reads_public_url(monkeypatch, tmp_path, capsys) -> None:
    output_dir = tmp_path / "live"
    result = build_live_artifacts(ROOT, created_at=CREATED_AT, limit=3)
    write_live_artifacts(output_dir, result.artifacts)
    latest_payload = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    health_payload = json.loads((output_dir / "health.json").read_text(encoding="utf-8"))
    fetched_urls: list[str] = []

    def fake_fetch_live_json(url: str, *, timeout: float, limit_bytes: int):
        fetched_urls.append(url)
        assert timeout == 20.0
        assert limit_bytes == 5_000_000
        if url.endswith("/latest.json"):
            return latest_payload
        if url.endswith("/health.json"):
            return health_payload
        raise AssertionError(url)

    monkeypatch.setattr("ai_provider_watch.cli.fetch_live_json", fake_fetch_live_json)

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "live",
                "latest",
                "--base-url",
                DEFAULT_LIVE_BASE_URL,
                "--limit",
                "1",
            ]
        )
        == 0
    )
    latest = json.loads(capsys.readouterr().out)
    assert len(latest) == 1
    assert fetched_urls[-1] == live_artifact_url(DEFAULT_LIVE_BASE_URL, "latest")

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "live",
                "health",
                "--url",
                live_artifact_url(DEFAULT_LIVE_BASE_URL, "health"),
                "--summary",
            ]
        )
        == 0
    )
    assert "status: ok" in capsys.readouterr().out
    assert fetched_urls[-1] == live_artifact_url(DEFAULT_LIVE_BASE_URL, "health")
