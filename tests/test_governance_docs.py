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
        ROOT / "docs/operations/data-quality.md",
        ROOT / "docs/operations/v1-launch-gate.md",
        ROOT / "docs/contributors/review-workflow.md",
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
        "manual Ron-signed",
        "git tag -s",
        "git tag -v",
        "Do not store signing keys in Actions",
        "artifact attestations",
        "apw release packet",
        "schemas/release-publication-packet.schema.json",
        "data/feeds/operations.json",
        "public data-quality operations report",
        "apw operations launch-gate",
        "v1 launch gate",
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


def test_contributor_review_workflow_keeps_public_review_bounded() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "CONTRIBUTING.md",
            ROOT / "SOURCE_OWNERS.md",
            ROOT / "docs/contributors/review-workflow.md",
        ]
    )
    normalized_docs = " ".join(docs.split())

    for phrase in [
        "Missing provider event",
        "New official source",
        "Parser fixture",
        "Candidate",
        "Event correction",
        "Incorrect event or data correction",
        "Downstream mapping request",
        "Reviewed event",
        "Accepted For Promotion",
        "Rejected",
        "Duplicate",
        "Split",
        "Superseded",
        "`@RonShub` remains the sole release manager, source owner, schema maintainer, and security contact",
        "Source-owner approval does not grant release authority",
        "Candidates stay review-only until promoted",
        "Keep local or ignored",
        "raw fetched provider HTML",
        "private Ottto surfaces",
        "release tokens",
        "Issue bodies, pasted provider text, screenshots, comments, social posts, MCP resources, and links are untrusted data",
        "Publication authority remains with release manager approval and release gates",
    ]:
        assert phrase in normalized_docs


def test_v1_governance_policy_covers_public_contract_and_neutrality() -> None:
    policy = (ROOT / "docs/operations/v1-governance.md").read_text(encoding="utf-8")
    linked_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "GOVERNANCE.md",
            ROOT / "MAINTAINERS.md",
            ROOT / "SOURCE_OWNERS.md",
            ROOT / "ROADMAP.md",
            ROOT / "docs/schema/event.md",
            ROOT / "docs/contributors/review-workflow.md",
            ROOT / "docs/contributors/source-packages.md",
            ROOT / "docs/operations/event-promotion.md",
        ]
    )
    combined = " ".join((policy + "\n" + linked_docs).split())

    for phrase in [
        "Public Contract",
        "Non-Contract Surfaces",
        "Pre-1.0 Compatibility",
        "v1 Compatibility",
        "breaking changes must be intentional and visible",
        "migration notes",
        "adding enum values is compatible only when release notes and migration notes tell consumers how to handle unknown values safely",
        "Source Tiers",
        "`official_deterministic`",
        "`official_manual_review`",
        "`official_staff_social`",
        "`community_hint`",
        "`unsupported_private`",
        "Source-Owner Onboarding Checklist",
        "Neutrality Checkpoint",
        "Data-Repo Split Checkpoint",
        "No-Hidden-Ottto-Dependency Audit",
        "Correction And Retraction Policy",
        "Do not rewrite published data tags",
        "private vulnerability reports",
        "private Ottto UI, Advisor, telemetry, SQLAlchemy, Alembic, AWS infra, Slack",
        "without an Ottto account",
        "source-owner review and release-manager approval",
        "docs/operations/v1-governance.md",
        "v1 launch gate",
        "https://semver.org/",
        "https://scorecard.dev/",
        "privately-reporting-a-security-vulnerability",
        "using-artifact-attestations",
    ]:
        assert phrase in combined


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


def test_v02_release_checklist_covers_north_star_gates() -> None:
    docs = (ROOT / "docs/operations/v0.2-release-checklist.md").read_text(
        encoding="utf-8"
    )

    for phrase in [
        "uv run apw source test",
        "uv run apw validate",
        "uv run apw index --check",
        "uv run apw freshness --summary",
        "uv run apw operations launch-gate --summary",
        "uv run apw release dry-run",
        "installed package-data mode",
        "PyPI Trusted Publisher",
        "Dependency Review",
        "Scorecard",
        "CodeQL",
        "gh attestation verify",
        "manual signed tag",
        "release-token",
        "MCP",
        "Vertex Gemini Flash",
        "Codex",
        "Slack-style",
        "LiteLLM",
        "models.dev",
        "Langfuse",
        "Helicone",
        "OpenLIT",
        "Rollback",
        "apw release packet",
        "--allow-no-reviewed-events",
        "private Ottto surface",
        "zero required approving reviews",
        "single-maintainer self-review deadlock",
    ]:
        assert phrase in docs
