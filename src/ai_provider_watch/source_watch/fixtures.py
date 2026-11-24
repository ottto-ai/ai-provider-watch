from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.issues import ValidationIssue
from ai_provider_watch.source_watch.parsers import parse_source_payload
from ai_provider_watch.sources.registry import load_source_descriptors

MAX_PARSER_FIXTURE_BYTES = 128_000


def _fixture_path(package_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = package_dir / path
    try:
        if not candidate.parent.resolve(strict=False).is_relative_to(package_dir.resolve()):
            return None
    except OSError:
        return None
    return candidate


def _fixture_file_issue(path: Path, label: str) -> str | None:
    if not path.exists():
        return f"missing parser {label} {path}"
    if path.is_symlink() or not path.is_file():
        return f"parser {label} must be a regular file: {path}"
    if path.stat().st_size > MAX_PARSER_FIXTURE_BYTES:
        return f"parser {label} exceeds {MAX_PARSER_FIXTURE_BYTES} bytes: {path}"
    return None


def validate_parser_fixtures(root: Path) -> list[ValidationIssue]:
    sources = {source.key: source for source in load_source_descriptors(root, enabled_only=False)}
    issues: list[ValidationIssue] = []

    for package_path in sorted((root / "sources").glob("*/source.json")):
        package = read_json(package_path)
        package_dir = package_path.parent
        package_source_keys = set(package.get("source_keys", []))
        parser_fixtures = package.get("parser_fixtures", [])
        if parser_fixtures is None:
            continue
        if not isinstance(parser_fixtures, list):
            issues.append(ValidationIssue(str(package_path), "parser_fixtures must be a list"))
            continue

        for index, fixture in enumerate(parser_fixtures):
            fixture_ref = f"parser_fixtures.{index}"
            if not isinstance(fixture, dict):
                issues.append(ValidationIssue(str(package_path), f"{fixture_ref} must be an object"))
                continue

            source_key = fixture.get("source_key")
            if not isinstance(source_key, str) or source_key not in package_source_keys:
                issues.append(
                    ValidationIssue(
                        str(package_path),
                        f"{fixture_ref}.source_key must reference a source in this package",
                    )
                )
                continue
            source = sources.get(source_key)
            if source is None:
                issues.append(ValidationIssue(str(package_path), f"unknown source key {source_key}"))
                continue

            input_path = _fixture_path(package_dir, fixture.get("input"))
            expected_path = _fixture_path(package_dir, fixture.get("expected"))
            if input_path is None:
                issues.append(ValidationIssue(str(package_path), f"{fixture_ref}.input is invalid"))
                continue
            if expected_path is None:
                issues.append(ValidationIssue(str(package_path), f"{fixture_ref}.expected is invalid"))
                continue
            input_issue = _fixture_file_issue(input_path, "input")
            if input_issue:
                issues.append(ValidationIssue(str(package_path), input_issue))
                continue
            expected_issue = _fixture_file_issue(expected_path, "expected")
            if expected_issue:
                issues.append(ValidationIssue(str(package_path), expected_issue))
                continue

            changed_value = fixture.get("changed", True)
            if not isinstance(changed_value, bool):
                issues.append(ValidationIssue(str(package_path), f"{fixture_ref}.changed must be boolean"))
                continue
            expected = read_json(expected_path)
            changed = changed_value
            if not isinstance(expected, dict):
                issues.append(ValidationIssue(str(expected_path), "parser expected fixture must be an object"))
                continue
            if expected.get("schema_version") != "apw.parser_fixture.expected.v0":
                issues.append(
                    ValidationIssue(
                        str(expected_path),
                        "parser expected fixture schema_version must be apw.parser_fixture.expected.v0",
                    )
                )
            if expected.get("source_key") != source_key:
                issues.append(
                    ValidationIssue(str(expected_path), f"parser expected source_key must be {source_key}")
                )
            if expected.get("changed") != changed:
                issues.append(
                    ValidationIssue(str(expected_path), f"parser expected changed must be {changed}")
                )
            parsed = parse_source_payload(source, input_path.read_bytes(), changed=changed)
            actual_payload = asdict(parsed)
            expected_payload = expected.get("expected")
            if actual_payload != expected_payload:
                issues.append(
                    ValidationIssue(
                        str(expected_path),
                        f"parser fixture output mismatch for {source_key}",
                    )
                )

    return issues
