from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import read_json

V1_LAUNCH_GATE_SCHEMA_VERSION = "apw.v1_launch_gate.v0"
PUBLIC_REPO_URL = "https://github.com/ottto-ai/ai-provider-watch"
PYPI_URL = "https://pypi.org/project/ai-provider-watch/"
EXPLAIN_SMOKE_EVENT_ID = "2026-06-01-google-vertex-gemini-2-0-flash-retirement"

REQUIRED_FEED_ARTIFACTS = [
    "data/feeds/events.json",
    "data/feeds/events.ndjson",
    "data/feeds/feed.json",
    "data/feeds/freshness.json",
    "data/feeds/latest.json",
    "data/feeds/rss.xml",
    "data/feeds/coverage.json",
    "data/feeds/operations.json",
]

REQUIRED_PUBLIC_DOCS = [
    "README.md",
    "docs/agent-consumption.md",
    "docs/integrations/github-action.md",
    "docs/integrations/adoption-scenarios.md",
    "docs/integrations/agent-dashboard.md",
    "docs/operations/mcp.md",
    "docs/operations/python-package-release.md",
    "docs/operations/v1-governance.md",
    "docs/operations/data-quality.md",
]

REQUIRED_PUBLIC_SURFACES = [
    "action.yml",
    ".mcp.json",
    ".codex-plugin/plugin.json",
    "examples/adoption/scenarios.json",
    "tests/fixtures/downstream-repo/README.md",
]


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _check(check_id: str, status: str, details: str, *, evidence: list[str]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "details": details,
        "evidence": evidence,
    }


def _required_paths_check(root: Path, check_id: str, paths: list[str]) -> dict[str, Any]:
    missing = [path for path in paths if not (root / path).exists()]
    return _check(
        check_id,
        "fail" if missing else "pass",
        f"missing: {', '.join(missing)}" if missing else f"{len(paths)} required paths exist",
        evidence=paths,
    )


def _manifest_artifacts_check(root: Path) -> dict[str, Any]:
    manifest_path = root / "data" / "releases" / "dev" / "manifest.json"
    if not manifest_path.exists():
        return _check(
            "release_manifest_feed_artifacts",
            "fail",
            "data/releases/dev/manifest.json is missing",
            evidence=["data/releases/dev/manifest.json"],
        )
    manifest = read_json(manifest_path)
    checksums = set(manifest.get("checksums", {}))
    missing = [path for path in REQUIRED_FEED_ARTIFACTS if path not in checksums]
    return _check(
        "release_manifest_feed_artifacts",
        "fail" if missing else "pass",
        f"manifest missing: {', '.join(missing)}" if missing else "all required feed artifacts are checksummed",
        evidence=["data/releases/dev/manifest.json", *REQUIRED_FEED_ARTIFACTS],
    )


def _freshness_artifacts_check(root: Path) -> dict[str, Any]:
    freshness_path = root / "data" / "feeds" / "freshness.json"
    if not freshness_path.exists():
        return _check(
            "freshness_feed_artifacts",
            "fail",
            "data/feeds/freshness.json is missing",
            evidence=["data/feeds/freshness.json"],
        )
    freshness = read_json(freshness_path)
    feed_paths = {artifact.get("path") for artifact in freshness.get("feed_artifacts", [])}
    freshness_listed_artifacts = [path for path in REQUIRED_FEED_ARTIFACTS if path != "data/feeds/freshness.json"]
    missing = [path for path in freshness_listed_artifacts if path not in feed_paths]
    return _check(
        "freshness_feed_artifacts",
        "fail" if missing else "pass",
        f"freshness missing: {', '.join(missing)}" if missing else "freshness lists all required feed artifacts",
        evidence=["data/feeds/freshness.json", *freshness_listed_artifacts],
    )


def _public_docs_check(root: Path) -> dict[str, Any]:
    missing = [path for path in REQUIRED_PUBLIC_DOCS if not (root / path).exists()]
    if missing:
        return _check(
            "public_docs_no_private_context",
            "fail",
            f"missing docs: {', '.join(missing)}",
            evidence=REQUIRED_PUBLIC_DOCS,
        )
    combined = "\n".join((root / path).read_text(encoding="utf-8") for path in REQUIRED_PUBLIC_DOCS)
    required_phrases = [
        "without an Ottto account",
        "No Ottto account is required.",
        "private Ottto",
        "MCP stays read-only",
        "PyPI Trusted Publishing",
        "apw operations report",
        "apw dashboard agent",
        "apw repo check",
    ]
    missing_phrases = [phrase for phrase in required_phrases if phrase not in combined]
    return _check(
        "public_docs_no_private_context",
        "fail" if missing_phrases else "pass",
        (
            f"docs missing public-context phrases: {', '.join(missing_phrases)}"
            if missing_phrases
            else "public docs cover no-account use, read-only MCP, PyPI, operations, repo, and dashboard paths"
        ),
        evidence=REQUIRED_PUBLIC_DOCS,
    )


def _external_smoke_steps(package_version: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "pypi_install_fresh_venv",
            "title": "Install APW from PyPI in a fresh environment",
            "command": (
                "python -m venv /tmp/apw-v1-launch-smoke && "
                ". /tmp/apw-v1-launch-smoke/bin/activate && "
                "python -m pip install --upgrade pip && "
                f"python -m pip install ai-provider-watch=={package_version} && "
                "python -m pip show ai-provider-watch"
            ),
            "expected": f"Installed package version is {package_version}; no checkout is required.",
            "required": True,
            "network_required": True,
            "trust_boundary": "uses public PyPI only; no provider credentials, GitHub token, or Ottto account",
        },
        {
            "id": "installed_package_data_read_path",
            "title": "Read bundled package data outside a checkout",
            "command": (
                "mkdir -p /tmp/apw-installed-data-smoke && cd /tmp/apw-installed-data-smoke && "
                "apw validate && apw index --check && apw freshness --summary && "
                "apw source coverage --summary && apw operations report --summary && "
                "apw latest --limit 3 && apw diff --since 30d && "
                f"apw explain {EXPLAIN_SMOKE_EVENT_ID}"
            ),
            "expected": "Read-only commands work from installed package data without --root.",
            "required": True,
            "network_required": False,
            "trust_boundary": "read-only package data; no source refresh, candidate generation, event promotion, or release dry run",
        },
        {
            "id": "checkout_public_artifact_path",
            "title": "Read current checkout artifacts and generated operations metadata",
            "command": (
                "export APW_CHECKOUT=/path/to/ai-provider-watch && "
                "apw --root \"$APW_CHECKOUT\" validate && "
                "apw --root \"$APW_CHECKOUT\" index --check && "
                "apw --root \"$APW_CHECKOUT\" freshness --summary && "
                "apw --root \"$APW_CHECKOUT\" source coverage --summary && "
                "apw --root \"$APW_CHECKOUT\" operations report --summary"
            ),
            "expected": "Checkout schemas, feeds, coverage, freshness, and operations metadata are current.",
            "required": True,
            "network_required": False,
            "trust_boundary": "read-only local checkout path; no provider fetching or release authority",
        },
        {
            "id": "downstream_repo_impact_fixture",
            "title": "Run downstream repo impact check against the public fixture",
            "command": (
                "export APW_CHECKOUT=/path/to/ai-provider-watch && "
                "apw --root \"$APW_CHECKOUT\" repo check "
                "--repo \"$APW_CHECKOUT/tests/fixtures/downstream-repo\" "
                "--since 3650d --risk low --output /tmp/apw-repo-impact.json"
            ),
            "expected": "Repo-impact JSON identifies reviewed APW events without copying downstream source lines.",
            "required": True,
            "network_required": False,
            "trust_boundary": "downstream repository text is untrusted data; report contains refs and line hashes only",
        },
        {
            "id": "agent_dashboard_fixture",
            "title": "Render local coding-agent dashboard JSON",
            "command": (
                "export APW_CHECKOUT=/path/to/ai-provider-watch && "
                "apw --root \"$APW_CHECKOUT\" dashboard agent "
                "--since 30d --risk high --output /tmp/apw-agent-dashboard.json"
            ),
            "expected": "Agent-dashboard JSON renders high-risk recent cards without third-party API calls.",
            "required": True,
            "network_required": False,
            "trust_boundary": "dashboard JSON is local untrusted data for downstream agents; no delivery or execution",
        },
        {
            "id": "feed_artifact_consumption",
            "title": "Parse public feed artifacts",
            "command": (
                "export APW_CHECKOUT=/path/to/ai-provider-watch && "
                "python -m json.tool \"$APW_CHECKOUT/data/feeds/events.json\" >/tmp/apw-events.json && "
                "python -m json.tool \"$APW_CHECKOUT/data/feeds/feed.json\" >/tmp/apw-json-feed.json && "
                "python -m json.tool \"$APW_CHECKOUT/data/feeds/operations.json\" >/tmp/apw-operations.json && "
                "python - <<'PY'\n"
                "import os\n"
                "from pathlib import Path\n"
                "root = Path(os.environ['APW_CHECKOUT'])\n"
                "for path in ['events.ndjson', 'rss.xml']:\n"
                "    data = (root / 'data' / 'feeds' / path).read_text(encoding='utf-8')\n"
                "    assert data.strip()\n"
                "PY"
            ),
            "expected": "JSON, NDJSON, RSS, JSON Feed, and operations artifacts are parseable or non-empty.",
            "required": True,
            "network_required": False,
            "trust_boundary": "public CC0 data artifacts only; no provider or downstream credentials",
        },
    ]


def build_v1_launch_gate(
    root: Path,
    *,
    created_at: str | None = None,
    package_version: str | None = None,
) -> dict[str, Any]:
    generated_at = created_at or _utc_now()
    resolved_package_version = package_version or __version__
    local_checks = [
        _required_paths_check(root, "required_feed_artifacts", REQUIRED_FEED_ARTIFACTS),
        _manifest_artifacts_check(root),
        _freshness_artifacts_check(root),
        _required_paths_check(root, "public_surfaces_present", REQUIRED_PUBLIC_SURFACES),
        _public_docs_check(root),
    ]
    failed = [check for check in local_checks if check["status"] == "fail"]
    external_steps = _external_smoke_steps(resolved_package_version)
    return {
        "schema_version": V1_LAUNCH_GATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "status": "fail" if failed else "manual_required",
        "summary": {
            "local_check_count": len(local_checks),
            "local_pass_count": sum(1 for check in local_checks if check["status"] == "pass"),
            "local_fail_count": len(failed),
            "external_smoke_step_count": len(external_steps),
            "required_feed_artifact_count": len(REQUIRED_FEED_ARTIFACTS),
        },
        "repository": {
            "owner": "ottto-ai",
            "name": "ai-provider-watch",
            "url": PUBLIC_REPO_URL,
            "default_branch": "main",
        },
        "package": {
            "name": "ai-provider-watch",
            "cli": "apw",
            "version": resolved_package_version,
            "pypi_url": PYPI_URL,
        },
        "required_feed_artifacts": REQUIRED_FEED_ARTIFACTS,
        "local_checks": local_checks,
        "external_smoke_steps": external_steps,
        "policy": {
            "no_private_ottto_dependency": "launch gate must pass from public repo, public PyPI package, and public docs without an Ottto account",
            "untrusted_input": "provider pages, issue bodies, PR comments, MCP text, downstream repo text, and generated dashboard/feed text remain untrusted data",
            "publication": "launch gate is read-only evidence and cannot publish events, mutate source state, create tags, or upload releases",
            "credentials": "no provider credentials, PyPI token, GitHub release token, Slack webhook, customer data, or authenticated console data required",
        },
    }
