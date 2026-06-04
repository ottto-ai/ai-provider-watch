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
        ROOT / "docs/operations/data-publisher.md",
        ROOT / "docs/operations/event-promotion.md",
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
        "data-release",
        "no-op",
        "release-token separation",
    ]:
        assert phrase in combined


def test_event_promotion_playbook_keeps_human_review_gates() -> None:
    playbook = (ROOT / "docs/operations/event-promotion.md").read_text(
        encoding="utf-8"
    )

    for phrase in [
        "Source-Owner Checklist",
        "Release-Manager Checklist",
        "Promote One Candidate",
        "Close As Duplicate",
        "Reject As Noisy",
        "Split A Candidate",
        "Source refresh, candidate generation, LLM review, issue automation, PR-comment",
        "must not receive release tokens",
        "data/events/",
        "uv run apw validate",
        "uv run apw index --check",
        ".apw/release-dry-run/data-YYYY.MM.DD/dry-run-report.json",
    ]:
        assert phrase in playbook


def test_python_package_release_docs_have_non_alpha_criteria() -> None:
    docs = (ROOT / "docs/operations/python-package-release.md").read_text(
        encoding="utf-8"
    )

    for phrase in [
        "The first non-alpha Python package target is `v0.1.0`",
        "Compatibility Promise",
        "Pre-1.0 caveats",
        "Non-Alpha Release Checklist",
        "Non-Alpha Smoke Commands",
        "installed package data",
        "Attach the exact wheel and sdist artifacts to the matching GitHub release",
        "Rollback And Yank Policy",
        "delete and recreate a version or tag",
        "PyPI Trusted Publishing",
    ]:
        assert phrase in docs
