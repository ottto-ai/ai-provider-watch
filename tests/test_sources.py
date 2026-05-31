from __future__ import annotations

from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.source_watch.http import build_fingerprint_state, normalize_bytes
from ai_provider_watch.source_watch.parsers import parse_source_payload
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


def test_changed_enabled_sources_emit_sanitized_candidate_claims() -> None:
    for source in load_source_descriptors(ROOT):
        parsed = parse_source_payload(
            source,
            b"<html><body>provider text must not be copied</body></html>",
            changed=True,
        )

        assert len(parsed.candidate_claims) == 1
        claim = parsed.candidate_claims[0]
        assert claim["candidate_kind"] in source.impact_hints or claim["candidate_kind"] == "unknown"
        assert source.provider_refs[0].split(":", 1)[1].split("-", 1)[0].lower() in claim["claim_text"].lower()
        assert "provider text must not be copied" not in claim["claim_text"]
        assert parsed.raw_excerpt_hashes == []


def test_unchanged_source_emits_no_candidate_claims() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.pricing")

    parsed = parse_source_payload(source, b"<html>pricing changed</html>", changed=False)

    assert parsed.candidate_claims == []


def test_atom_status_parser_hashes_entry_text_without_copying_it() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.status")
    raw = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:status.openai.com,2026:incident-1</id>
    <title>Major incident title should not be copied</title>
    <updated>2026-05-31T20:00:00Z</updated>
  </entry>
</feed>
"""

    parsed = parse_source_payload(source, raw, changed=True)

    assert parsed.errors == []
    assert parsed.items == [
        {
            "kind": "atom_entry",
            "title_sha256": "f875ffa988c1d5a0a916527c8e5e3c37d83f84a322c591cdee7af731dfcc4a90",
            "id_sha256": "355e4179b91d8153d0595225abccd791d8b8dfec2dc8761ced2d92fd44b18f94",
            "updated": "2026-05-31T20:00:00Z",
        }
    ]
    rendered = str(parsed.items) + str(parsed.candidate_claims)
    assert "Major incident title" not in rendered


def test_atom_status_parser_hashes_invalid_updated_text() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.status")
    raw = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:status.openai.com,2026:incident-1</id>
    <title>Major incident title should not be copied</title>
    <updated>not a timestamp with provider text that should not be copied</updated>
  </entry>
</feed>
"""

    parsed = parse_source_payload(source, raw, changed=True)

    assert parsed.items == [
        {
            "kind": "atom_entry",
            "title_sha256": "f875ffa988c1d5a0a916527c8e5e3c37d83f84a322c591cdee7af731dfcc4a90",
            "id_sha256": "355e4179b91d8153d0595225abccd791d8b8dfec2dc8761ced2d92fd44b18f94",
            "updated_sha256": "ce32dc2d0e6438e724de716efed28f3d00843d77974f3513559cef521c56f855",
        }
    ]
    rendered = str(parsed.items) + str(parsed.candidate_claims)
    assert "provider text" not in rendered


def test_atom_status_parser_rejects_dtd_entities() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.status")
    raw = b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE feed [
  <!ENTITY xxe "provider text must not expand">
]>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>&xxe;</id>
    <title>&xxe;</title>
  </entry>
</feed>
"""

    parsed = parse_source_payload(source, raw, changed=True)

    assert parsed.items == []
    assert parsed.errors == ["atom parser failed: EntitiesForbidden"]
    assert parsed.candidate_claims == [
        {
            "candidate_kind": "status_incident",
            "claim_text": (
                "OpenAI status source changed and needs maintainer review for a possible "
                "status incident or recovery."
            ),
        }
    ]
