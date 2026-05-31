from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.issues import ValidationIssue


@dataclass(frozen=True)
class SourceDescriptor:
    key: str
    provider_refs: list[str]
    url: str
    authority: str
    source_type: str
    enabled: bool
    parser: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SourceDescriptor:
        return cls(
            key=data["key"],
            provider_refs=list(data["provider_refs"]),
            url=data["url"],
            authority=data["authority"],
            source_type=data["source_type"],
            enabled=bool(data["enabled"]),
            parser=data["parser"],
        )


def load_source_descriptors(root: Path, *, enabled_only: bool = True) -> list[SourceDescriptor]:
    registry = read_json(root / "sources" / "registry.json")
    sources = [SourceDescriptor.from_json(item) for item in registry.get("sources", [])]
    if enabled_only:
        sources = [source for source in sources if source.enabled]
    return sorted(sources, key=lambda source: source.key)


def validate_source_packages(root: Path) -> list[ValidationIssue]:
    descriptors = {source.key for source in load_source_descriptors(root, enabled_only=False)}
    issues: list[ValidationIssue] = []

    for package_path in sorted((root / "sources").glob("*/source.json")):
        package = read_json(package_path)
        package_dir = package_path.parent
        provider_ref = package.get("provider_ref")
        if not isinstance(provider_ref, str) or not provider_ref.startswith("provider:"):
            issues.append(ValidationIssue(str(package_path), "provider_ref must be a provider:<id> ref"))

        source_keys = package.get("source_keys", [])
        if not source_keys:
            issues.append(ValidationIssue(str(package_path), "source_keys must not be empty"))
        for source_key in source_keys:
            if source_key not in descriptors:
                issues.append(
                    ValidationIssue(str(package_path), f"unknown source key {source_key}")
                )

        fixtures = package.get("fixtures", [])
        if not fixtures:
            issues.append(ValidationIssue(str(package_path), "fixtures must not be empty"))
        for fixture in fixtures:
            fixture_path = package_dir / fixture
            if not fixture_path.exists():
                issues.append(ValidationIssue(str(package_path), f"missing fixture {fixture}"))
                continue
            fixture_data = read_json(fixture_path)
            fixture_keys = set(fixture_data.get("source_keys", []))
            missing_keys = set(source_keys) - fixture_keys
            if missing_keys:
                issues.append(
                    ValidationIssue(
                        str(fixture_path),
                        f"fixture missing source keys: {', '.join(sorted(missing_keys))}",
                    )
                )

    return issues
