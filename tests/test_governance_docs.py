from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_owner_map_covers_registry_sources_and_roles() -> None:
    registry = json.loads((ROOT / "sources/registry.json").read_text(encoding="utf-8"))
    source_owners = (ROOT / "SOURCE_OWNERS.md").read_text(encoding="utf-8")
    maintainers = (ROOT / "MAINTAINERS.md").read_text(encoding="utf-8")

    for source in registry["sources"]:
        assert f"`{source['key']}`" in source_owners
        for role in source["maintainers"]:
            assert role in source_owners
            assert role in maintainers


def test_release_governance_docs_have_required_operator_gates() -> None:
    paths = [
        ROOT / "GOVERNANCE.md",
        ROOT / "MAINTAINERS.md",
        ROOT / "ROADMAP.md",
        ROOT / "SOURCE_OWNERS.md",
        ROOT / "docs/operations/repository-settings.md",
        ROOT / "docs/operations/release-gates.md",
        ROOT / "docs/operations/data-release.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in [
        "release manager",
        "source owner",
        "branch protection",
        "Dependency Review",
        "gh attestation verify",
        "daily CalVer",
        "data-YYYY.MM.DD",
        "release-token separation",
    ]:
        assert phrase in combined
