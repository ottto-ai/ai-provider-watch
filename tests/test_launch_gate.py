from __future__ import annotations

import shutil
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.validation import load_schemas
from ai_provider_watch.pipeline.launch_gate import build_v1_launch_gate

ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-06-10T00:00:00Z"


def test_v1_launch_gate_matches_schema_and_requires_external_smoke() -> None:
    report = build_v1_launch_gate(
        ROOT,
        created_at=CREATED_AT,
        package_version="0.1.1",
    )
    schema = load_schemas(ROOT)["v1_launch_gate"]

    assert not list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    assert report["schema_version"] == "apw.v1_launch_gate.v0"
    assert report["generated_at"] == CREATED_AT
    assert report["status"] == "manual_required"
    assert report["summary"]["local_fail_count"] == 0
    assert report["summary"]["local_pass_count"] == report["summary"]["local_check_count"]
    assert report["package"]["name"] == "ai-provider-watch"
    assert report["package"]["version"] == "0.1.1"
    assert "data/feeds/source-catalog.json" in report["required_feed_artifacts"]
    assert "data/feeds/operations.json" in report["required_feed_artifacts"]
    assert {step["id"] for step in report["external_smoke_steps"]} >= {
        "pypi_install_fresh_venv",
        "installed_package_data_read_path",
        "downstream_repo_impact_fixture",
        "agent_dashboard_fixture",
        "feed_artifact_consumption",
    }
    assert any("apw operations report --summary" in step["command"] for step in report["external_smoke_steps"])
    for step in report["external_smoke_steps"]:
        boundary = step["trust_boundary"]
        assert any(
            phrase in boundary
            for phrase in ["no provider credentials", "untrusted", "read-only", "public"]
        )


def test_v1_launch_gate_fails_when_required_artifact_is_missing(tmp_path) -> None:
    for dirname in ["data", "docs", "examples", "schemas", "tests"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)
    for filename in ["README.md", "action.yml"]:
        shutil.copy2(ROOT / filename, tmp_path / filename)
    shutil.copytree(ROOT / ".codex-plugin", tmp_path / ".codex-plugin")
    shutil.copy2(ROOT / ".mcp.json", tmp_path / ".mcp.json")

    (tmp_path / "data" / "feeds" / "operations.json").unlink()

    report = build_v1_launch_gate(tmp_path, created_at=CREATED_AT)

    assert report["status"] == "fail"
    assert report["summary"]["local_fail_count"] >= 1
    failing = {check["id"]: check for check in report["local_checks"] if check["status"] == "fail"}
    assert "required_feed_artifacts" in failing
