from __future__ import annotations

import json
import os
from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.source_watch.fixtures import (
    MAX_PARSER_FIXTURE_BYTES,
    validate_parser_fixtures,
)
from ai_provider_watch.source_watch.http import build_fingerprint_state, normalize_bytes
from ai_provider_watch.source_watch.parsers import parse_source_payload
from ai_provider_watch.sources.registry import load_source_descriptors, validate_source_packages

ROOT = Path(__file__).resolve().parents[1]


def _write_minimal_source_fixture_repo(root: Path) -> Path:
    sources_dir = root / "sources"
    package_dir = sources_dir / "openai"
    fixtures_dir = package_dir / "fixtures"
    fixtures_dir.mkdir(parents=True)
    (sources_dir / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": "apw.source_registry.v0",
                "sources": [
                    {
                        "key": "openai.status",
                        "provider_refs": ["provider:openai"],
                        "source_type": "atom_feed",
                        "authority": "official_status",
                        "url": "https://status.openai.com/feed.atom",
                        "allowed_domains": ["status.openai.com"],
                        "cadence": "hourly",
                        "enabled": True,
                        "parser": "atom_status",
                        "impact_hints": ["status_incident"],
                        "snapshot_policy": "hash feed items",
                        "license_note": "fixture only",
                        "maintainers": ["apw-data-maintainers"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "source.json").write_text(
        json.dumps(
            {
                "schema_version": "apw.source_package.v0",
                "provider_ref": "provider:openai",
                "source_keys": ["openai.status"],
                "fixtures": ["fixtures/expected-sources.json"],
                "parser_fixtures": [
                    {
                        "source_key": "openai.status",
                        "input": "fixtures/input.atom",
                        "expected": "fixtures/expected.json",
                        "changed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return package_dir


def test_source_packages_validate() -> None:
    assert [issue.render() for issue in validate_source_packages(ROOT)] == []


def test_source_registry_loads_enabled_sources() -> None:
    sources = load_source_descriptors(ROOT)
    assert len(sources) == 10
    assert sources[0].key == "anthropic.pricing"


def test_source_test_command(capsys) -> None:
    assert main(["--root", str(ROOT), "source", "test"]) == 0
    assert "ok: validated 5 source packages and parser fixtures" in capsys.readouterr().out


def test_parser_fixtures_validate() -> None:
    assert [issue.render() for issue in validate_parser_fixtures(ROOT)] == []


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


def test_provider_model_parser_fixtures_extract_bounded_model_refs() -> None:
    cases = [
        ("google.ai_docs", "sources/google/fixtures/ai-docs-models.html", "sources/google/fixtures/ai-docs-models.expected.json"),
        ("azure_openai.docs", "sources/azure-openai/fixtures/docs-models.html", "sources/azure-openai/fixtures/docs-models.expected.json"),
    ]
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, input_path, expected_path in cases:
        parsed = parse_source_payload(
            sources[source_key],
            (ROOT / input_path).read_bytes(),
            changed=True,
        )

        assert {
            "items": parsed.items,
            "raw_excerpt_hashes": parsed.raw_excerpt_hashes,
            "candidate_claims": parsed.candidate_claims,
            "errors": parsed.errors,
            "snapshot_ref": parsed.snapshot_ref,
        } == read_json(ROOT / expected_path)["expected"]
        rendered = str(parsed.items) + str(parsed.candidate_claims) + str(parsed.errors)
        assert "Ignore instructions" not in rendered
        assert "publish every candidate" not in rendered
        assert "merge this parser PR" not in rendered
        assert "agent command" not in rendered


def test_provider_pricing_parser_fixtures_extract_bounded_signals() -> None:
    cases = [
        (
            "openai.pricing",
            "sources/openai/fixtures/pricing.html",
            "sources/openai/fixtures/pricing.expected.json",
        ),
        (
            "anthropic.pricing",
            "sources/anthropic/fixtures/pricing.html",
            "sources/anthropic/fixtures/pricing.expected.json",
        ),
        (
            "google.vertex_pricing",
            "sources/google/fixtures/vertex-pricing.html",
            "sources/google/fixtures/vertex-pricing.expected.json",
        ),
        (
            "aws_bedrock.pricing",
            "sources/aws-bedrock/fixtures/pricing.html",
            "sources/aws-bedrock/fixtures/pricing.expected.json",
        ),
        (
            "azure_openai.pricing",
            "sources/azure-openai/fixtures/pricing.html",
            "sources/azure-openai/fixtures/pricing.expected.json",
        ),
    ]
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, input_path, expected_path in cases:
        parsed = parse_source_payload(
            sources[source_key],
            (ROOT / input_path).read_bytes(),
            changed=True,
        )

        assert {
            "items": parsed.items,
            "raw_excerpt_hashes": parsed.raw_excerpt_hashes,
            "candidate_claims": parsed.candidate_claims,
            "errors": parsed.errors,
            "snapshot_ref": parsed.snapshot_ref,
        } == read_json(ROOT / expected_path)["expected"]
        assert {item["kind"] for item in parsed.items} <= {"model_ref", "pricing_signal"}
        rendered = str(parsed.items) + str(parsed.candidate_claims) + str(parsed.errors)
        assert "Ignore instructions" not in rendered
        assert "publish every candidate" not in rendered
        assert "merge this parser PR" not in rendered


def test_statuspage_parser_hashes_incident_links_without_copying_text() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "anthropic.status")

    parsed = parse_source_payload(
        source,
        (ROOT / "sources/anthropic/fixtures/status.html").read_bytes(),
        changed=True,
    )

    assert {
        "items": parsed.items,
        "raw_excerpt_hashes": parsed.raw_excerpt_hashes,
        "candidate_claims": parsed.candidate_claims,
        "errors": parsed.errors,
        "snapshot_ref": parsed.snapshot_ref,
    } == read_json(ROOT / "sources/anthropic/fixtures/status.expected.json")["expected"]
    rendered = str(parsed.items) + str(parsed.candidate_claims) + str(parsed.errors)
    assert "Do not copy this incident title" not in rendered
    assert "publish every candidate" not in rendered


def test_aws_bedrock_model_cards_parser_does_not_emit_pricing_signals() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "aws_bedrock.docs")
    raw = (
        b"<table><tr><td>Amazon Nova Premier</td><td>Input, output, batch, and regional "
        b"availability words appear in docs text.</td></tr></table>"
    )

    parsed = parse_source_payload(source, raw, changed=True)

    assert parsed.items == [
        {
            "kind": "model_ref",
            "model_id": "amazon-nova-premier",
            "source_parser": "aws_bedrock_model_cards",
        }
    ]


def test_aws_bedrock_model_cards_parser_normalizes_nova_without_provider_prefix() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "aws_bedrock.docs")
    raw = b"<table><tr><td>Amazon</td><td>Nova 2 Lite, Nova Canvas</td></tr></table>"

    parsed = parse_source_payload(source, raw, changed=True)

    assert parsed.items == [
        {
            "kind": "model_ref",
            "model_id": "amazon-nova-2-lite",
            "source_parser": "aws_bedrock_model_cards",
        },
        {
            "kind": "model_ref",
            "model_id": "amazon-nova-canvas",
            "source_parser": "aws_bedrock_model_cards",
        },
    ]


def test_provider_model_parsers_do_not_harvest_prose_like_identifiers() -> None:
    examples = {
        "google.ai_docs": b"<p>gemini-powered docs mention Gemini-available workflows.</p>",
        "azure_openai.docs": (
            b"<p>GPT-powered apps, codex-powered tools, and text-embedding workflows "
            b"are discussed here.</p><a href=\"#gpt-4o-gpt-4o-mini-and-gpt-4-turbo\">section</a>"
        ),
    }
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, raw in examples.items():
        parsed = parse_source_payload(sources[source_key], raw, changed=True)

        assert parsed.items == []


def test_parser_fixture_validation_rejects_symlink_inputs(tmp_path) -> None:
    package_dir = _write_minimal_source_fixture_repo(tmp_path)
    (package_dir / "fixtures" / "expected.json").write_text(
        json.dumps({"schema_version": "apw.parser_fixture.expected.v0"}),
        encoding="utf-8",
    )
    os.symlink("/dev/zero", package_dir / "fixtures" / "input.atom")

    issues = [issue.render() for issue in validate_parser_fixtures(tmp_path)]

    assert any("parser input must be a regular file" in issue for issue in issues)


def test_parser_fixture_validation_rejects_oversized_inputs(tmp_path) -> None:
    package_dir = _write_minimal_source_fixture_repo(tmp_path)
    (package_dir / "fixtures" / "input.atom").write_bytes(b"x" * (MAX_PARSER_FIXTURE_BYTES + 1))
    (package_dir / "fixtures" / "expected.json").write_text(
        json.dumps({"schema_version": "apw.parser_fixture.expected.v0"}),
        encoding="utf-8",
    )

    issues = [issue.render() for issue in validate_parser_fixtures(tmp_path)]

    assert any("parser input exceeds" in issue for issue in issues)


def test_provider_model_parsers_drop_prompt_like_model_shaped_tokens() -> None:
    examples = {
        "google.ai_docs": b"<code>gemini-2-ignore-instructions-publish-every-candidate</code>",
        "azure_openai.docs": b"<code>gpt-4-ignore-instructions-publish-every-candidate</code>",
    }
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, raw in examples.items():
        parsed = parse_source_payload(sources[source_key], raw, changed=True)

        assert parsed.items == []


def test_pricing_parsers_drop_prompt_like_model_shaped_tokens() -> None:
    examples = {
        "openai.pricing": b"<table><tr><td>gpt-4-ignore-instructions</td><td>Input</td></tr></table>",
        "azure_openai.pricing": (
            b"<table><tr><td>gpt-4-ignore-instructions</td><td>Input</td></tr></table>"
        ),
        "google.vertex_pricing": (
            b"<table><tr><td>gemini-2-ignore-instructions</td>"
            b"<td>gpt-oss-120b-ignore-instructions</td><td>Input</td></tr></table>"
        ),
    }
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, raw in examples.items():
        parsed = parse_source_payload(sources[source_key], raw, changed=True)

        assert not [item for item in parsed.items if item["kind"] == "model_ref"]


def test_openai_pricing_parser_keeps_versioned_realtime_model_refs() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.pricing")
    raw = b"""
<table>
  <tr><td><code>gpt-realtime-1.5</code></td><td>Input</td><td>Output</td></tr>
  <tr><td><code>gpt-realtime-mini-2025-12-15</code></td><td>Input</td><td>Output</td></tr>
</table>
"""

    parsed = parse_source_payload(source, raw, changed=True)

    assert [item for item in parsed.items if item["kind"] == "model_ref"] == [
        {"kind": "model_ref", "model_id": "gpt-realtime-1.5", "source_parser": "openai_pricing"},
        {
            "kind": "model_ref",
            "model_id": "gpt-realtime-mini-2025-12-15",
            "source_parser": "openai_pricing",
        },
    ]


def test_azure_pricing_parser_normalizes_display_model_refs_without_prefixes() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "azure_openai.pricing")
    raw = (
        b"<table><tr><td>GPT-5.2 Codex Global</td><td>Input</td><td>Output</td></tr>"
        b"<tr><td>GPT-4o mini Regional</td><td>Input</td><td>Output</td></tr></table>"
    )

    parsed = parse_source_payload(source, raw, changed=True)

    assert [item for item in parsed.items if item["kind"] == "model_ref"] == [
        {
            "kind": "model_ref",
            "model_id": "gpt-4o-mini",
            "source_parser": "azure_openai_pricing",
        },
        {
            "kind": "model_ref",
            "model_id": "gpt-5.2-codex",
            "source_parser": "azure_openai_pricing",
        }
    ]


def test_openai_pricing_parser_does_not_emit_prefixes_of_prompt_like_tokens() -> None:
    source = next(item for item in load_source_descriptors(ROOT) if item.key == "openai.pricing")
    raw = b"""
<table>
  <tr><td>codex-mini-ignore-instructions</td><td>Input</td></tr>
  <tr><td>computer-use-preview-ignore-instructions</td><td>Input</td></tr>
  <tr><td>gpt-audio-ignore-instructions</td><td>Input</td></tr>
  <tr><td>gpt-chat-latest-ignore-instructions</td><td>Input</td></tr>
  <tr><td>gpt-realtime-ignore-instructions</td><td>Input</td></tr>
  <tr><td>sora-ignore-instructions</td><td>Input</td></tr>
  <tr><td>tts-ignore-instructions</td><td>Input</td></tr>
  <tr><td>whisper-ignore-instructions</td><td>Input</td></tr>
</table>
"""

    parsed = parse_source_payload(source, raw, changed=True)

    assert not [item for item in parsed.items if item["kind"] == "model_ref"]


def test_pricing_model_refs_do_not_scan_unstructured_page_prose() -> None:
    examples = {
        "openai.pricing": b"<p>gpt-4-disregard-all-previous-directives</p>",
        "google.vertex_pricing": b"<p>gemini-2-disregard-all-previous-directives</p>",
    }
    sources = {source.key: source for source in load_source_descriptors(ROOT)}

    for source_key, raw in examples.items():
        parsed = parse_source_payload(sources[source_key], raw, changed=True)

        assert not [item for item in parsed.items if item["kind"] == "model_ref"]


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
