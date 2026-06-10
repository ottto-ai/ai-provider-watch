from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import ai_provider_watch.cli as cli
import ai_provider_watch.mcp.server as mcp_server
from ai_provider_watch.core import io

ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "2024-01-04-openai-gpt3-completions-retirement"


def _make_package_data_root(path: Path) -> None:
    (path / "schemas").mkdir(parents=True)
    (path / "data" / "events").mkdir(parents=True)
    (path / "registries").mkdir(parents=True)
    (path / "sources").mkdir(parents=True)
    (path / "sources" / "registry.json").write_text('{"sources": []}\n', encoding="utf-8")


def test_repo_root_falls_back_to_bundled_package_data(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "_data"
    _make_package_data_root(bundled)
    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.chdir(outside)
    monkeypatch.setattr(io, "package_data_root", lambda: bundled)

    assert io.repo_root() == bundled


def test_mcp_server_root_falls_back_to_bundled_package_data(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "_data"
    _make_package_data_root(bundled)
    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.chdir(outside)
    monkeypatch.delenv("APW_REPO_ROOT", raising=False)
    monkeypatch.setattr(io, "package_data_root", lambda: bundled)

    assert mcp_server._server_root() == bundled


def test_explicit_package_data_root_is_supported(tmp_path) -> None:
    bundled = tmp_path / "_data"
    _make_package_data_root(bundled)

    assert io.repo_root(bundled) == bundled


def test_explicit_missing_root_does_not_fall_back_to_package_data(monkeypatch, tmp_path) -> None:
    bundled = tmp_path / "_data"
    _make_package_data_root(bundled)
    monkeypatch.setattr(io, "package_data_root", lambda: bundled)

    with pytest.raises(FileNotFoundError):
        io.repo_root(tmp_path / "not-a-checkout")


def test_incomplete_data_root_is_rejected(tmp_path) -> None:
    bundled = tmp_path / "_data"
    (bundled / "schemas").mkdir(parents=True)
    (bundled / "data" / "events").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        io.repo_root(bundled)


def test_package_data_relative_output_writes_to_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(io, "package_data_root", lambda: ROOT)
    monkeypatch.setattr(cli, "package_data_root", lambda: ROOT)

    assert (
        cli.main(
            [
                "notify",
                "webhook",
                "--since",
                "2024-01-01",
                "--risk",
                "medium",
                "--event-id",
                EVENT_ID,
                "--created-at",
                "2026-06-02T00:00:00Z",
                "--output",
                ".apw/webhook.json",
            ]
        )
        == 0
    )

    assert (tmp_path / ".apw" / "webhook.json").is_file()


def test_package_data_write_commands_require_checkout(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(io, "package_data_root", lambda: ROOT)
    monkeypatch.setattr(cli, "package_data_root", lambda: ROOT)

    assert cli.main(["index"]) == 1
    assert "index requires an APW checkout" in capsys.readouterr().err
    assert cli.main(["release", "automation-readiness"]) == 1
    assert "release automation-readiness requires an APW checkout" in capsys.readouterr().err


def test_wheel_contains_read_only_apw_data(tmp_path) -> None:
    import subprocess

    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], cwd=ROOT, check=True)
    wheel = next(tmp_path.glob("ai_provider_watch-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        latest = json.loads(
            archive.read("ai_provider_watch/_data/data/feeds/latest.json").decode("utf-8")
        )
        json_feed = json.loads(
            archive.read("ai_provider_watch/_data/data/feeds/feed.json").decode("utf-8")
        )

    assert "ai_provider_watch/_data/schemas/event.schema.json" in names
    assert "ai_provider_watch/_data/schemas/json-feed.schema.json" in names
    assert "ai_provider_watch/_data/schemas/source-coverage.schema.json" in names
    assert "ai_provider_watch/_data/schemas/candidate-quality.schema.json" in names
    assert "ai_provider_watch/_data/schemas/candidate-to-event-packet.schema.json" in names
    assert "ai_provider_watch/_data/schemas/source-owner-packet.schema.json" in names
    assert "ai_provider_watch/_data/schemas/repo-impact.schema.json" in names
    assert "ai_provider_watch/_data/schemas/adoption-scenarios.schema.json" in names
    assert "ai_provider_watch/_data/schemas/release-evidence-index.schema.json" in names
    assert "ai_provider_watch/_data/schemas/release-publication-packet.schema.json" in names
    assert "ai_provider_watch/_data/schemas/release-verification.schema.json" in names
    assert "ai_provider_watch/_data/schemas/release-automation-readiness.schema.json" in names
    assert "ai_provider_watch/_data/schemas/agent-dashboard.schema.json" in names
    assert "ai_provider_watch/_data/schemas/operations-report.schema.json" in names
    assert "ai_provider_watch/_data/schemas/v1-launch-gate.schema.json" in names
    assert "ai_provider_watch/_data/README.md" in names
    assert "ai_provider_watch/_data/action.yml" in names
    assert "ai_provider_watch/_data/.mcp.json" in names
    assert "ai_provider_watch/_data/.codex-plugin/plugin.json" in names
    assert "ai_provider_watch/_data/docs/consumer-api.md" in names
    assert "ai_provider_watch/_data/docs/operations/release-automation-readiness.md" in names
    assert "ai_provider_watch/_data/docs/operations/v1-launch-gate.md" in names
    assert "ai_provider_watch/_data/docs/agent-consumption.md" in names
    assert "ai_provider_watch/_data/examples/adoption/scenarios.json" in names
    assert "ai_provider_watch/_data/tests/fixtures/downstream-repo/README.md" in names
    assert "ai_provider_watch/_data/.github/ISSUE_TEMPLATE/missing_event.yml" in names
    assert (
        "ai_provider_watch/_data/.github/ISSUE_TEMPLATE/provider_data_correction.yml"
        in names
    )
    assert "ai_provider_watch/_data/registries/providers.json" in names
    assert "ai_provider_watch/_data/data/feeds/coverage.json" in names
    assert "ai_provider_watch/_data/data/feeds/feed.json" in names
    assert "ai_provider_watch/_data/data/feeds/operations.json" in names
    assert "ai_provider_watch/_data/sources/registry.json" in names
    assert "ai_provider_watch/_data/sources/aws-bedrock/fixtures/whats-new-feed.xml" in names
    assert "ai_provider_watch/_data/sources/openai/fixtures/news-feed.xml" in names
    assert any(item["id"] == "2026-06-01-google-vertex-gemini-2-0-flash-retirement" for item in latest)
    assert json_feed["version"] == "https://jsonfeed.org/version/1.1"
    assert json_feed["items"][0]["_apw"]["schema_version"] == "apw.provider_event.v0"
