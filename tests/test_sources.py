from __future__ import annotations

from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.source_watch.http import build_fingerprint_state, normalize_bytes
from ai_provider_watch.sources.registry import load_source_descriptors, validate_source_packages

ROOT = Path(__file__).resolve().parents[1]


def test_source_packages_validate() -> None:
    assert [issue.render() for issue in validate_source_packages(ROOT)] == []


def test_source_registry_loads_enabled_sources() -> None:
    sources = load_source_descriptors(ROOT)
    assert len(sources) == 10
    assert sources[0].key == "anthropic.pricing"


def test_source_test_command(capsys) -> None:
    assert main(["--root", str(ROOT), "source", "test"]) == 0
    assert "ok: validated 5 source packages" in capsys.readouterr().out


def test_normalize_bytes_stabilizes_whitespace() -> None:
    assert normalize_bytes(b"<html>\n  hello\t world </html>") == b"<html> hello world </html>"


def test_empty_fingerprint_state_shape() -> None:
    assert build_fingerprint_state([]) == {
        "schema_version": "apw.source_fingerprints.v0",
        "sources": {},
    }
