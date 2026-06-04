from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import ai_provider_watch.cli as cli
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


def test_wheel_contains_read_only_apw_data(tmp_path) -> None:
    import subprocess

    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path)], cwd=ROOT, check=True)
    wheel = next(tmp_path.glob("ai_provider_watch-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        latest = json.loads(
            archive.read("ai_provider_watch/_data/data/feeds/latest.json").decode("utf-8")
        )

    assert "ai_provider_watch/_data/schemas/event.schema.json" in names
    assert "ai_provider_watch/_data/schemas/repo-impact.schema.json" in names
    assert "ai_provider_watch/_data/registries/providers.json" in names
    assert "ai_provider_watch/_data/sources/registry.json" in names
    assert any(item["id"] == "2026-06-01-google-vertex-gemini-2-0-flash-retirement" for item in latest)
