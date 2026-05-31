from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.issues import ValidationIssue


@dataclass(frozen=True)
class SourceDescriptor:
    key: str
    provider_refs: list[str]
    url: str
    authority: str
    source_type: str
    allowed_domains: list[str]
    enabled: bool
    parser: str
    impact_hints: list[str]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SourceDescriptor:
        provider_refs = data.get("provider_refs", [])
        allowed_domains = data.get("allowed_domains", [])
        impact_hints = data.get("impact_hints", [])
        return cls(
            key=str(data.get("key") or "<missing-key>"),
            provider_refs=list(provider_refs) if isinstance(provider_refs, list) else [],
            url=str(data.get("url") or ""),
            authority=str(data.get("authority") or ""),
            source_type=str(data.get("source_type") or ""),
            allowed_domains=[
                domain for domain in allowed_domains if isinstance(domain, str)
            ]
            if isinstance(allowed_domains, list)
            else [],
            enabled=bool(data.get("enabled", False)),
            parser=str(data.get("parser") or ""),
            impact_hints=list(impact_hints) if isinstance(impact_hints, list) else [],
        )


STRICT_URI_CHAR_PATTERN = re.compile(r"^[A-Za-z0-9:/?#\[\]@!$&'()*+,;=._~%-]+$")
BAD_PERCENT_ESCAPE_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")


def load_source_descriptors(root: Path, *, enabled_only: bool = True) -> list[SourceDescriptor]:
    registry = read_json(root / "sources" / "registry.json")
    sources = [SourceDescriptor.from_json(item) for item in registry.get("sources", [])]
    if enabled_only:
        sources = [source for source in sources if source.enabled]
    return sorted(sources, key=lambda source: source.key)


def is_url_allowed_for_source(url: str, source: SourceDescriptor) -> bool:
    if "\\" in url:
        return False
    if any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 or ord(char) > 126
        for char in url
    ):
        return False
    if not STRICT_URI_CHAR_PATTERN.fullmatch(url):
        return False
    if BAD_PERCENT_ESCAPE_PATTERN.search(url):
        return False
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port
    except ValueError:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if not hostname:
        return False
    for domain in source.allowed_domains:
        allowed = domain.lower().rstrip(".")
        if hostname == allowed or hostname.endswith(f".{allowed}"):
            return True
    return False


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
