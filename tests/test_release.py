from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from ai_provider_watch.pipeline.release import (
    _is_working_tree_clean,
    calver_release_id,
    parse_release_id_date,
    run_release_dry_run,
)

ROOT = Path(__file__).resolve().parents[1]
DUMMY_SHA = "0123456789abcdef0123456789abcdef01234567"


def test_calver_release_id() -> None:
    assert calver_release_id(date(2026, 6, 1)) == "data-2026.06.01"
    assert parse_release_id_date("data-2026.06.01") == date(2026, 6, 1)


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
    assert "actionlint .github/workflows/*.yml" in result.report["validation_commands"]
    assert result.report_path.exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert {check["name"] for check in report["checks"]} >= {
        "release_id_calver",
        "schema_and_repo_validation",
        "generated_dev_artifacts_current",
        "release_manifest_schema",
        "release_checksums",
        "license_layout",
        "dependency_lock",
        "codeql_workflow",
        "dependency_review_workflow",
        "release_workflow_guardrails",
        "source_refresh_token_boundary",
        "source_ownership",
        "maintainer_release_docs",
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
    assert "data/feeds/events.json" in manifest["checksums"]


def test_release_dry_run_rejects_non_calver_release_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="release_id must match data-YYYY.MM.DD"):
        run_release_dry_run(
            ROOT,
            release_date=date(2026, 6, 1),
            release_id="../dev",
            output_dir=tmp_path,
            source_commit=DUMMY_SHA,
        )
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
