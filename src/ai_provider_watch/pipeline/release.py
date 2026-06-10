from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch import __version__
from ai_provider_watch.core.feeds import artifact_diffs, build_artifacts, write_artifacts
from ai_provider_watch.core.io import event_paths, write_json_text
from ai_provider_watch.core.validation import load_schemas, validate
from ai_provider_watch.pipeline.coverage import build_source_coverage_report
from ai_provider_watch.pipeline.launch_gate import build_v1_launch_gate
from ai_provider_watch.pipeline.operations import build_operations_report
from ai_provider_watch.source_watch.fixtures import validate_parser_fixtures
from ai_provider_watch.sources.registry import validate_source_packages

RELEASE_DRY_RUN_SCHEMA_VERSION = "apw.release_dry_run.v0"
RELEASE_PUBLICATION_PACKET_SCHEMA_VERSION = "apw.release_publication_packet.v0"
RELEASE_VERIFICATION_SCHEMA_VERSION = "apw.release_verification.v0"
RELEASE_AUTOMATION_READINESS_SCHEMA_VERSION = "apw.release_automation_readiness.v0"
RELEASE_ID_PATTERN = re.compile(r"^data-\d{4}\.\d{2}\.\d{2}$")


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    status: str
    details: str


@dataclass(frozen=True)
class ReleaseDryRunResult:
    report: dict[str, Any]
    failed_checks: list[ReleaseCheck]
    output_dir: Path
    report_path: Path


@dataclass(frozen=True)
class ReleaseVerificationResult:
    report: dict[str, Any]
    failed_checks: list[ReleaseCheck]


def calver_release_id(release_date: date) -> str:
    return f"data-{release_date:%Y.%m.%d}"


def parse_release_id_date(release_id: str) -> date:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ValueError(f"release_id must match data-YYYY.MM.DD: {release_id}")
    try:
        return date.fromisoformat(release_id.removeprefix("data-").replace(".", "-"))
    except ValueError as exc:
        raise ValueError(f"release_id must contain a valid calendar date: {release_id}") from exc


def parse_release_date(value: str | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    return date.fromisoformat(value)


def _check(name: str, passed: bool, details: str) -> ReleaseCheck:
    return ReleaseCheck(name=name, status="pass" if passed else "fail", details=details)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _source_commit(root: Path, override: str | None) -> str | None:
    if override:
        return override
    return _git_output(root, "rev-parse", "HEAD")


def _is_working_tree_clean(root: Path) -> bool:
    status = _git_output(root, "status", "--porcelain", "--untracked-files=all")
    return status == ""


def _package_version_check() -> ReleaseCheck:
    try:
        installed = version("ai-provider-watch")
    except PackageNotFoundError:
        return _check("package_install", False, "ai-provider-watch package metadata is not installed")
    return _check(
        "package_install",
        installed == __version__,
        f"installed package version {installed}; imported package version {__version__}",
    )


def _workflow_text(root: Path, workflow: str) -> str:
    path = root / ".github" / "workflows" / workflow
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _workflow_missing(text: str, required: list[str]) -> list[str]:
    return [needle for needle in required if needle not in text]


def _workflow_forbidden(text: str, forbidden: list[str]) -> list[str]:
    return [needle for needle in forbidden if needle in text]


def _codeql_workflow_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "codeql.yml")
    missing = _workflow_missing(
        workflow,
        [
            "github/codeql-action/analyze",
            "security-events: write",
            "pull_request:",
            "push:",
        ],
    )
    forbidden = _workflow_forbidden(workflow, ["contents: write", "id-token: write", "secrets."])
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "CodeQL workflow uploads code-scanning results with minimal write permission"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("codeql_workflow", passed, details)


def _dependency_review_workflow_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "dependency-review.yml")
    missing = _workflow_missing(
        workflow,
        [
            "workflow_dispatch:",
            "contents: read",
            "pull-requests: read",
            "actions/dependency-review-action@v5",
            "base-ref: ${{ inputs.base_ref }}",
            "head-ref: ${{ inputs.head_ref }}",
        ],
    )
    forbidden = _workflow_forbidden(
        workflow,
        ["contents: write", "pull-requests: write", "id-token: write", "secrets.", "pull_request_target:"],
    )
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "Dependency Review can run manually with base/head refs and read-only permissions"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("dependency_review_workflow", passed, details)


def _release_workflow_guardrails_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "release-data.yml")
    missing = _workflow_missing(
        workflow,
        [
            "workflow_dispatch:",
            "contents: read",
            "id-token: write",
            "attestations: write",
            "uv lock --check",
            "uv run pytest",
            "uv run apw source test",
            "uv run apw source coverage --summary",
            "uv run apw validate",
            "uv run apw index --check",
            "uv build --out-dir .apw/dist",
            "apw latest --limit 1 >/tmp/apw-installed-latest.json",
            "--require-clean",
            "apw --root \"$PWD\" release verify",
            "apw-release-dry-run.tgz",
            "actions/attest@v4",
            "subject-path: .apw/apw-release-dry-run.tgz",
            "actions/upload-artifact@v7",
        ],
    )
    forbidden = _workflow_forbidden(
        workflow,
        [
            "contents: write",
            "secrets.",
            "gh release",
            "git tag",
            "pull_request_target:",
        ],
    )
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "release workflow is dry-run only, package-install checked, and attests its evidence bundle without release publishing authority"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("release_workflow_guardrails", passed, details)


def _data_publisher_noop_workflow_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "data-publisher.yml")
    missing = _workflow_missing(
        workflow,
        [
            "workflow_dispatch:",
            "publish_mode:",
            "no-op",
            "packet",
            "permissions:\n  contents: read",
            "group: data-release-publisher-${{ github.ref }}",
            "if: github.ref == 'refs/heads/main'",
            "environment:\n      name: data-release",
            "uv lock --check",
            "uv run ruff check .",
            "uv run pytest",
            "uv run apw source test",
            "uv run apw source coverage --summary",
            "uv run apw validate",
            "uv run apw index --check",
            "uv run apw release dry-run",
            "uv run apw release verify",
            'uv run apw "${args[@]}"',
            "publication-packet.json",
            "release-verification.json",
            "actions/upload-artifact@v7",
            "apw-data-publication-packet",
            "scorecard_ref:",
            "SCORECARD_REF",
            "--scorecard-ref",
            "--require-clean",
            "no data tag or GitHub data release was created",
        ],
    )
    forbidden = _workflow_forbidden(
        workflow,
        [
            "contents: write",
            "id-token: write",
            "attestations: write",
            "secrets.",
            "gh release",
            "git tag",
            "pull_request:",
            "pull_request_target:",
            "schedule:",
        ],
    )
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "data publisher is protected, main-only, no-op-or-packet-only, and has no release publishing authority"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("data_publisher_noop_workflow", passed, details)


def _source_refresh_token_boundary_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "source-refresh.yml")
    missing = _workflow_missing(
        workflow,
        [
            "contents: write",
            "pull-requests: write",
            "uv run apw source fetch",
            "uv run apw candidate generate",
            "gh pr create",
        ],
    )
    forbidden = _workflow_forbidden(
        workflow,
        ["secrets.", "id-token: write", "gh release", "git tag", "pull_request_target:"],
    )
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "source refresh can open review PRs but has no secrets, id-token, tag, or release command path"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("source_refresh_token_boundary", passed, details)


def _scorecard_workflow_check(root: Path) -> ReleaseCheck:
    workflow = _workflow_text(root, "scorecard.yml")
    missing = _workflow_missing(
        workflow,
        [
            "ossf/scorecard-action@v2.4.3",
            "results_file: scorecard-results.sarif",
            "results_format: sarif",
            "publish_results: false",
            "github/codeql-action/upload-sarif@v4",
            "contents: read",
            "security-events: write",
            "id-token: write",
        ],
    )
    forbidden = _workflow_forbidden(
        workflow,
        [
            "contents: write",
            "pull-requests: write",
            "secrets.",
            "gh release",
            "git tag",
            "pull_request_target:",
        ],
    )
    passed = bool(workflow) and not missing and not forbidden
    if passed:
        details = "OpenSSF Scorecard uploads SARIF with no publishing authority"
    else:
        details = f"missing: {', '.join(missing) or 'none'}; forbidden: {', '.join(forbidden) or 'none'}"
    return _check("scorecard_workflow", passed, details)


def _readiness_check(
    check_id: str,
    status: str,
    details: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "details": details,
        "evidence": evidence,
    }


def _release_check_to_readiness(
    check: ReleaseCheck,
    *,
    check_id: str | None = None,
    evidence: list[str],
) -> dict[str, Any]:
    return _readiness_check(
        check_id or check.name,
        check.status,
        check.details,
        evidence,
    )


def _workflow_forbidden_readiness_check(
    root: Path,
    *,
    check_id: str,
    workflow_names: list[str],
    forbidden: list[str],
    details: str,
) -> dict[str, Any]:
    failures: list[str] = []
    evidence: list[str] = []
    for workflow_name in workflow_names:
        workflow = _workflow_text(root, workflow_name)
        evidence.append(f".github/workflows/{workflow_name}")
        if not workflow:
            failures.append(f"{workflow_name}: missing")
            continue
        forbidden_hits = _workflow_forbidden(workflow, forbidden)
        if forbidden_hits:
            failures.append(f"{workflow_name}: forbidden {', '.join(forbidden_hits)}")
    return _readiness_check(
        check_id,
        "pass" if not failures else "fail",
        details if not failures else "; ".join(failures),
        evidence,
    )


def _required_doc_phrases_check(
    root: Path,
    *,
    check_id: str,
    paths_and_phrases: dict[str, list[str]],
    details: str,
) -> dict[str, Any]:
    failures: list[str] = []
    for relative_path, phrases in paths_and_phrases.items():
        path = root / relative_path
        if not path.exists():
            failures.append(f"{relative_path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in text]
        if missing:
            failures.append(f"{relative_path}: missing {', '.join(missing)}")
    return _readiness_check(
        check_id,
        "pass" if not failures else "fail",
        details if not failures else "; ".join(failures),
        sorted(paths_and_phrases),
    )


def build_release_automation_readiness(
    root: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Render the v0.x decision record for data-release automation.

    This report deliberately distinguishes healthy local guardrails from release
    authority. A passing guardrail set still reports ``blocked`` until
    maintainers approve a signing-equivalent data-tag mechanism in a later PR.
    """

    generated_at = created_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    untrusted_workflows = ["source-refresh.yml", "llm-review-request.yml", "codex-review.yml"]
    no_release_authority = [
        "id-token: write",
        "attestations: write",
        "secrets.",
        "gh release",
        "git tag",
        "pull_request_target:",
    ]
    checks = [
        _release_check_to_readiness(
            _data_publisher_noop_workflow_check(root),
            check_id="data_publisher_noop_or_packet_only",
            evidence=[".github/workflows/data-publisher.yml"],
        ),
        _release_check_to_readiness(
            _release_workflow_guardrails_check(root),
            check_id="release_dry_run_attestation_only",
            evidence=[".github/workflows/release-data.yml"],
        ),
        _workflow_forbidden_readiness_check(
            root,
            check_id="untrusted_lanes_have_no_release_authority",
            workflow_names=untrusted_workflows,
            forbidden=no_release_authority,
            details="source refresh, LLM review, and Codex review workflows cannot tag, release, request OIDC, attest, or read secrets",
        ),
        _workflow_forbidden_readiness_check(
            root,
            check_id="scorecard_has_no_publication_authority",
            workflow_names=["scorecard.yml"],
            forbidden=["contents: write", "pull-requests: write", "secrets.", "gh release", "git tag", "pull_request_target:"],
            details="Scorecard may upload security posture evidence but cannot publish data tags or releases",
        ),
        _required_doc_phrases_check(
            root,
            check_id="manual_signed_tag_baseline_documented",
            paths_and_phrases={
                "docs/operations/data-publisher.md": [
                    "manual Ron-signed Git tag",
                    "GitHub artifact attestations are provenance evidence",
                    "not create a tag",
                    "does not create or upload a GitHub Release",
                ],
                "docs/operations/release-gates.md": [
                    "v0.1 Signed-Tag Policy",
                    "signing keys in GitHub Actions",
                    "artifact attestations",
                ],
                "docs/operations/data-release.md": [
                    "apw release packet",
                    "manual signed-tag",
                    "does not create tags",
                ],
            },
            details="release docs preserve the manual signed-tag baseline and explain why attestations are evidence, not data-tag signing authority",
        ),
        _required_doc_phrases_check(
            root,
            check_id="future_automation_graduation_tests_documented",
            paths_and_phrases={
                "docs/operations/data-publisher.md": [
                    "Future Automated Publishing Gate",
                    "runs only from trusted `main` commits",
                    "selected tag mechanism",
                    "signing keys are never available to workflows that process provider pages",
                ],
                "docs/operations/v0.2-release-checklist.md": [
                    "manual signed tag",
                    "release-token",
                    "zero required approving reviews",
                ],
                ".github/PULL_REQUEST_TEMPLATE.md": [
                    "Release-manager, branch-protection, Dependency Review, checksum, and attestation blockers documented",
                ],
            },
            details="future automation is gated by explicit tests, release-manager review, and documented token boundaries",
        ),
    ]

    decision_blockers = [
        {
            "id": "signing_equivalence",
            "title": "Select a data-tag signing-equivalent mechanism",
            "status": "required",
            "recommendation": (
                "Keep public data publication manual and release-manager signed until a dedicated PR "
                "proves an automated mechanism preserves equivalent non-repudiation, branch protection, "
                "environment review, checksum review, and release-token separation."
            ),
            "tradeoffs": [
                "Manual signed tags are slower but keep private signing keys out of GitHub Actions and untrusted lanes.",
                "GitHub artifact attestations prove workflow provenance for evidence bundles, but they do not by themselves express release-manager intent for a public data tag.",
                "A future protected publisher could reduce daily toil, but it must deliberately add write authority and pass stronger key-management tests before publication.",
            ],
            "evidence": [
                "docs/operations/data-publisher.md#approved-v01-publishing-mechanism",
                "docs/operations/release-gates.md#v01-signed-tag-policy",
                "https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds",
            ],
        },
        {
            "id": "protected_environment_verification",
            "title": "Verify the data-release environment and branch rules externally",
            "status": "required",
            "recommendation": (
                "Record environment reviewer, branch-protection, CI, CodeQL, Dependency Review, "
                "Scorecard, checksum, and attestation evidence in the publication packet before any "
                "real data tag."
            ),
            "tradeoffs": [
                "Local checks can prove repository files and token boundaries, but they cannot prove GitHub repository settings without live evidence.",
                "External evidence adds operator work, but it prevents confusing a passing checkout with a publishable release state.",
            ],
            "evidence": [
                "docs/operations/repository-settings.md",
                "schemas/release-publication-packet.schema.json",
                "https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment",
            ],
        },
    ]
    failed_checks = [check for check in checks if check["status"] == "fail"]
    warning_checks = [check for check in checks if check["status"] == "warn"]
    status = "fail" if failed_checks else "blocked" if decision_blockers else "ready_for_publish_pr"
    report = {
        "schema_version": RELEASE_AUTOMATION_READINESS_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "status": status,
        "summary": {
            "current_mode": "manual_signed_data_tags",
            "publisher_mode": "protected_main_noop_or_packet_only",
            "target_mode": "protected_automation_after_signing_equivalence",
            "blocking_decision": "signing_equivalence_not_approved" if decision_blockers else None,
            "check_count": len(checks),
            "pass_count": len([check for check in checks if check["status"] == "pass"]),
            "fail_count": len(failed_checks),
            "warn_count": len(warning_checks),
            "decision_blocker_count": len(decision_blockers),
        },
        "checks": checks,
        "decision_blockers": decision_blockers,
        "token_boundary": {
            "publisher_workflow": ".github/workflows/data-publisher.yml",
            "dry_run_workflow": ".github/workflows/release-data.yml",
            "protected_environment": "data-release",
            "untrusted_lanes": untrusted_workflows,
            "no_release_tokens_in_untrusted_lanes": True,
            "publisher_has_release_authority": False,
        },
        "policy": {
            "manual_signed_tag_baseline": "v0.x data publication requires a release-manager signed data-YYYY.MM.DD tag.",
            "artifact_attestations": "Artifact attestations are provenance evidence for dry-run bundles, not a replacement for release-manager signed data tags.",
            "secrets": "Do not store signing keys in Actions, repository secrets, environment secrets, or OIDC-backed jobs.",
            "publication": "Do not add unattended data tag or GitHub Release creation until signing-equivalence and external GitHub settings are approved in a deliberate PR.",
        },
        "references": [
            {
                "label": "GitHub artifact attestations",
                "url": "https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds",
            },
            {
                "label": "GitHub deployment environments",
                "url": "https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment",
            },
            {
                "label": "PyPI Trusted Publishing security model",
                "url": "https://docs.pypi.org/trusted-publishers/security-model/",
            },
        ],
    }
    errors = _validate_schema_payload(root, "release_automation_readiness", report)
    if errors:
        raise ValueError(f"invalid release automation readiness report: {'; '.join(errors)}")
    return report


def _release_automation_readiness_check(root: Path, *, created_at: str) -> ReleaseCheck:
    try:
        readiness = build_release_automation_readiness(root, created_at=created_at)
    except ValueError as exc:
        return _check("release_automation_readiness", False, str(exc))
    summary = readiness["summary"]
    if readiness["status"] == "fail":
        failed_checks = [
            check["id"]
            for check in readiness["checks"]
            if check["status"] == "fail"
        ]
        return _check(
            "release_automation_readiness",
            False,
            f"failed readiness checks: {', '.join(failed_checks)}",
        )
    return _check(
        "release_automation_readiness",
        True,
        "release automation readiness report valid; "
        f"status={readiness['status']}, "
        f"mode={summary['current_mode']}, "
        f"blockers={summary['decision_blocker_count']}",
    )


def _external_release_gates() -> list[dict[str, str]]:
    return [
        {
            "name": "Branch protection",
            "status": "required",
            "details": "Main must be protected by a branch rule or ruleset that requires PRs and required status checks before a public data tag is cut.",
        },
        {
            "name": "Maintainer release approval",
            "status": "required",
            "details": "A listed release manager must approve the source commit, dry-run report, checksums, and release notes.",
        },
        {
            "name": "CI test workflow",
            "status": "required",
            "details": "The release source commit must have a successful CI test workflow run.",
        },
        {
            "name": "CodeQL analyze workflow",
            "status": "required",
            "details": "The release source commit must have a successful CodeQL workflow run.",
        },
        {
            "name": "CodeQL code-scanning analysis",
            "status": "required",
            "details": "The release source commit must appear in GitHub code-scanning analyses for refs/heads/main.",
        },
        {
            "name": "Dependency Review",
            "status": "required",
            "details": "Dependency Review must pass in a manual base/head run before release after repository dependency graph support is enabled.",
        },
        {
            "name": "OpenSSF Scorecard",
            "status": "required",
            "details": "OpenSSF Scorecard must run for the release source commit and upload a SARIF posture report without release authority.",
        },
        {
            "name": "Repository security settings",
            "status": "required",
            "details": "Dependency graph, Dependabot security updates, secret scanning, and push protection should be enabled or a maintainer must record why a setting is unavailable.",
        },
        {
            "name": "Artifact checksum review",
            "status": "required",
            "details": "Maintainers must compare dry-run manifest and checksums.txt hashes before publishing.",
        },
        {
            "name": "Artifact attestation verification",
            "status": "required",
            "details": "Maintainers must verify the attested dry-run evidence bundle before using it as release evidence.",
        },
        {
            "name": "Signed data tag",
            "status": "required",
            "details": "The public data tag must be signed by a release manager or created by a protected publisher after the signed-tag mechanism is approved.",
        },
        {
            "name": "Protected data publisher",
            "status": "required",
            "details": "Real publication requires a protected data-release environment, release-manager approval, and a deliberate change from no-op publisher mode.",
        },
        {
            "name": "Release token separation",
            "status": "required",
            "details": "No release token may be available to source-refresh, candidate-generation, or untrusted-content jobs.",
        },
    ]


def _source_ownership_check(root: Path) -> ReleaseCheck:
    owners_path = root / "SOURCE_OWNERS.md"
    maintainers_path = root / "MAINTAINERS.md"
    registry_path = root / "sources" / "registry.json"
    missing_files = [
        str(path.relative_to(root))
        for path in [owners_path, maintainers_path, registry_path]
        if not path.exists()
    ]
    if missing_files:
        return _check("source_ownership", False, f"missing files: {', '.join(missing_files)}")

    owners_text = owners_path.read_text(encoding="utf-8")
    maintainers_text = maintainers_path.read_text(encoding="utf-8")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    source_keys = sorted(source["key"] for source in sources)
    missing_keys = [key for key in source_keys if f"`{key}`" not in owners_text]
    role_keys = sorted({role for source in sources for role in source.get("maintainers", [])})
    missing_roles = [
        role
        for role in role_keys
        if role not in owners_text or role not in maintainers_text
    ]
    passed = not missing_keys and not missing_roles
    if passed:
        details = f"{len(source_keys)} source keys and {len(role_keys)} maintainer role keys have documented owners"
    else:
        parts = []
        if missing_keys:
            parts.append(f"missing source keys: {', '.join(missing_keys)}")
        if missing_roles:
            parts.append(f"missing role keys: {', '.join(missing_roles)}")
        details = "; ".join(parts)
    return _check("source_ownership", passed, details)


def _maintainer_release_docs_check(root: Path) -> ReleaseCheck:
    required_phrases = {
        "GOVERNANCE.md": ["release manager", "source owner", "required status checks"],
        "MAINTAINERS.md": ["apw-release-managers", "apw-data-maintainers"],
        "ROADMAP.md": ["v0.1", "daily CalVer", "release gates"],
        "SOURCE_OWNERS.md": ["Source owner", "openai.pricing"],
        "docs/operations/repository-settings.md": ["branch protection", "Dependency Review", "gh api"],
        "docs/operations/release-gates.md": ["gh attestation verify", "release manager"],
        "docs/operations/data-release.md": ["data-YYYY.MM.DD", "attestation"],
        "docs/operations/data-publisher.md": ["data-release", "no-op", "signed-tag"],
    }
    failures: list[str] = []
    for relative_path, phrases in required_phrases.items():
        path = root / relative_path
        if not path.exists():
            failures.append(f"{relative_path}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [phrase for phrase in phrases if phrase not in text]
        if missing:
            failures.append(f"{relative_path}: missing {', '.join(missing)}")
    return _check(
        "maintainer_release_docs",
        not failures,
        "maintainer, source-owner, roadmap, repository-settings, and release docs are present"
        if not failures
        else "; ".join(failures),
    )


def _license_check(root: Path) -> ReleaseCheck:
    required = [
        "LICENSES/Apache-2.0.txt",
        "LICENSES/CC0-1.0.txt",
        "DATA_LICENSE.md",
        "REUSE.toml",
    ]
    missing = [path for path in required if not (root / path).exists()]
    reuse = (root / "REUSE.toml").read_text(encoding="utf-8") if not missing else ""
    has_apache = "SPDX-License-Identifier = \"Apache-2.0\"" in reuse
    has_cc0 = "SPDX-License-Identifier = \"CC0-1.0\"" in reuse and "\"data/**\"" in reuse
    passed = not missing and has_apache and has_cc0
    details = "Apache-2.0 code/docs/schemas and CC0-1.0 data annotations present"
    if missing:
        details = f"missing license files: {', '.join(missing)}"
    elif not has_apache or not has_cc0:
        details = "REUSE.toml does not contain expected Apache-2.0 and CC0-1.0 annotations"
    return _check("license_layout", passed, details)


def _checksum_check(artifacts: dict[Path, str], manifest: dict[str, Any]) -> ReleaseCheck:
    mismatches: list[str] = []
    for artifact in manifest.get("artifacts", []):
        path = Path(artifact["path"])
        text = artifacts.get(path)
        if text is None:
            mismatches.append(f"{path}: missing from artifact map")
            continue
        digest = _sha256_text(text)
        if digest != artifact["sha256"]:
            mismatches.append(f"{path}: manifest sha256 does not match content")
        if len(text.encode("utf-8")) != artifact["bytes"]:
            mismatches.append(f"{path}: manifest byte count does not match content")
    checksums = manifest.get("checksums", {})
    for path, digest in checksums.items():
        text = artifacts.get(Path(path))
        if text is None or _sha256_text(text) != digest:
            mismatches.append(f"{path}: checksums map does not match content")
    checksum_artifact = next(
        (Path(path) for path in checksums if path.endswith("/checksums.txt")),
        None,
    )
    if checksum_artifact is None:
        mismatches.append("manifest does not include checksums.txt artifact")
    else:
        checksum_text = artifacts.get(checksum_artifact)
        if checksum_text is None:
            mismatches.append(f"{checksum_artifact}: missing from artifact map")
        else:
            listed_paths: set[Path] = set()
            for line in checksum_text.splitlines():
                try:
                    digest, path = line.split("  ", 1)
                except ValueError:
                    mismatches.append(f"{checksum_artifact}: malformed checksum line {line!r}")
                    continue
                listed_path = Path(path)
                listed_paths.add(listed_path)
                text = artifacts.get(listed_path)
                if text is None:
                    mismatches.append(f"{checksum_artifact}: listed unknown artifact {listed_path}")
                elif _sha256_text(text) != digest:
                    mismatches.append(f"{checksum_artifact}: digest mismatch for {listed_path}")
            manifest_path = Path(str(checksum_artifact).replace("checksums.txt", "manifest.json"))
            expected_paths = set(artifacts) - {checksum_artifact, manifest_path}
            if listed_paths != expected_paths:
                missing = ", ".join(
                    str(path) for path in sorted(expected_paths - listed_paths, key=str)
                )
                extra = ", ".join(
                    str(path) for path in sorted(listed_paths - expected_paths, key=str)
                )
                mismatches.append(
                    f"{checksum_artifact}: listed paths differ from generated artifacts"
                    f" (missing: {missing or 'none'}; extra: {extra or 'none'})"
                )
    return _check(
        "release_checksums",
        not mismatches,
        "manifest hashes, byte counts, and checksums.txt entries match generated content"
        if not mismatches
        else "; ".join(mismatches),
    )


def _schema_check(root: Path, report: dict[str, Any]) -> ReleaseCheck:
    schema = load_schemas(root)["release_dry_run"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(report), key=lambda item: list(item.path))
    if not errors:
        return _check("dry_run_report_schema", True, "release dry-run report matches schema")
    rendered = []
    for error in errors:
        location = ".".join(str(part) for part in error.path)
        rendered.append(f"{location}: {error.message}" if location else error.message)
    return _check("dry_run_report_schema", False, "; ".join(rendered))


def _validate_schema_payload(
    root: Path,
    schema_name: str,
    payload: dict[str, Any],
) -> list[str]:
    schema = load_schemas(root)[schema_name]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rendered: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path)
        rendered.append(f"{location}: {error.message}" if location else error.message)
    return rendered


def _source_coverage_check(root: Path, *, created_at: str) -> ReleaseCheck:
    coverage = build_source_coverage_report(root, created_at=created_at)
    errors = _validate_schema_payload(root, "source_coverage", coverage)
    if errors:
        return _check("source_coverage_report", False, "; ".join(errors))
    summary = coverage["summary"]
    warning_samples = [
        f"{warning.get('source_key') or warning['code']}: {warning['detail']}"
        for warning in coverage.get("warnings", [])[:5]
    ]
    warning_detail = "; ".join(warning_samples) if warning_samples else "none"
    return _check(
        "source_coverage_report",
        True,
        "coverage report valid; "
        f"enabled={summary['enabled_deterministic_source_count']}, "
        f"fetched={summary['fetched_enabled_source_count']}, "
        f"missing={summary['missing_enabled_source_count']}, "
        f"blocked={summary['blocked_pending_parser_source_count']}, "
        f"candidate_backlog={summary['candidate_backlog_count']}, "
        f"warnings={summary['warning_count']} ({warning_detail})",
    )


def _operations_report_check(root: Path, *, created_at: str) -> ReleaseCheck:
    operations = build_operations_report(root, created_at=created_at)
    errors = _validate_schema_payload(root, "operations_report", operations)
    if errors:
        return _check("operations_report", False, "; ".join(errors))
    summary = operations["summary"]
    failing_slos = [row["id"] for row in operations["slos"] if row["status"] == "fail"]
    warning_slos = [row["id"] for row in operations["slos"] if row["status"] == "warn"]
    issue_detail = f"fail={failing_slos or 'none'}, warn={warning_slos or 'none'}"
    return _check(
        "operations_report",
        True,
        "operations report valid; "
        f"overall={operations['overall_status']}, "
        f"latest_event_age_days={summary['latest_reviewed_event_age_days']}, "
        f"source_state_age_hours={summary['source_state_age_hours']}, "
        f"coverage_ratio={summary['enabled_source_coverage_ratio']}, "
        f"candidate_backlog={summary['candidate_backlog_count']} ({issue_detail})",
    )


def _v1_launch_gate_check(root: Path, *, created_at: str) -> ReleaseCheck:
    launch_gate = build_v1_launch_gate(root, created_at=created_at)
    errors = _validate_schema_payload(root, "v1_launch_gate", launch_gate)
    if errors:
        return _check("v1_launch_gate", False, "; ".join(errors))
    failed = [
        f"{check['id']}: {check['details']}"
        for check in launch_gate["local_checks"]
        if check["status"] == "fail"
    ]
    if failed:
        return _check("v1_launch_gate", False, "; ".join(failed))
    summary = launch_gate["summary"]
    return _check(
        "v1_launch_gate",
        True,
        "launch gate local checks valid; "
        f"local_pass={summary['local_pass_count']}/{summary['local_check_count']}, "
        f"external_smoke_steps={summary['external_smoke_step_count']}, "
        f"status={launch_gate['status']}",
    )


def _relative_or_absolute(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)


def _read_json_file(path: Path, label: str) -> Any:
    try:
        return read_json_from_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{label} not readable: {path}: {exc}") from exc


def _path_from_report_root(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _artifact_root_from_report(root: Path, report_path: Path, report: dict[str, Any], override: Path | None) -> Path:
    if override is not None:
        return override
    sibling = report_path.parent / "artifacts"
    if sibling.exists():
        return sibling
    output_dir = report.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        return _path_from_report_root(root, output_dir) / "artifacts"
    return sibling


def _verify_release_artifact_files(
    artifacts_root: Path,
    report: dict[str, Any],
) -> tuple[ReleaseCheck, list[dict[str, Any]], dict[Path, str]]:
    failures: list[str] = []
    verified_artifacts: list[dict[str, Any]] = []
    artifact_text: dict[Path, str] = {}
    for artifact in report.get("release_artifacts", []):
        if not isinstance(artifact, dict):
            failures.append("release_artifacts contains a non-object item")
            continue
        artifact_path = Path(str(artifact.get("path") or ""))
        if artifact_path.is_absolute() or ".." in artifact_path.parts:
            failures.append(f"{artifact_path}: artifact path must be relative and confined")
            continue
        path = artifacts_root / artifact_path
        if not path.exists():
            failures.append(f"{artifact_path}: missing")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"{artifact_path}: unreadable: {exc}")
            continue
        digest = _sha256_text(text)
        size = len(text.encode("utf-8"))
        artifact_text[artifact_path] = text
        if digest != artifact.get("sha256"):
            failures.append(f"{artifact_path}: sha256 mismatch")
        if size != artifact.get("bytes"):
            failures.append(f"{artifact_path}: byte count mismatch")
        verified_artifacts.append(
            {
                "path": str(artifact_path),
                "sha256": digest,
                "bytes": size,
            }
        )
    details = (
        f"{len(verified_artifacts)} release artifact file(s) match report hashes and byte counts"
        if not failures
        else "; ".join(failures)
    )
    return _check("release_artifact_files", not failures, details), verified_artifacts, artifact_text


def _verify_manifest_and_checksums(
    root: Path,
    artifacts_root: Path,
    report: dict[str, Any],
    artifact_text: dict[Path, str],
) -> ReleaseCheck:
    release_id = str(report.get("release_id") or "")
    manifest_path = Path(f"data/releases/{release_id}/manifest.json")
    manifest_file = artifacts_root / manifest_path
    if not manifest_file.exists():
        return _check("release_manifest_and_checksums", False, f"{manifest_path}: missing")
    try:
        manifest_text = manifest_file.read_text(encoding="utf-8")
        manifest = read_json_from_text(manifest_text)
    except (OSError, ValueError) as exc:
        return _check("release_manifest_and_checksums", False, f"{manifest_path}: invalid: {exc}")
    artifact_text = dict(artifact_text)
    artifact_text[manifest_path] = manifest_text
    errors = _validate_schema_payload(root, "release_manifest", manifest)
    if errors:
        return _check("release_manifest_and_checksums", False, "; ".join(errors))
    mismatches: list[str] = []
    if manifest.get("release_id") != report.get("release_id"):
        mismatches.append("manifest release_id does not match report")
    if manifest.get("source_commit") != report.get("source_commit"):
        mismatches.append("manifest source_commit does not match report")
    checksum_check = _checksum_check(artifact_text, manifest)
    if checksum_check.status != "pass":
        mismatches.append(checksum_check.details)
    return _check(
        "release_manifest_and_checksums",
        not mismatches,
        "manifest schema, source commit, hashes, byte counts, and checksums.txt are consistent"
        if not mismatches
        else "; ".join(mismatches),
    )


def _verify_publication_packet(
    root: Path,
    *,
    packet_path: Path | None,
    dry_run_report_path: Path,
    report: dict[str, Any],
    require_publish_packet: bool,
) -> ReleaseCheck:
    if packet_path is None:
        return _check(
            "publication_packet",
            not require_publish_packet,
            "publication packet not provided"
            if not require_publish_packet
            else "publication packet is required",
        )
    if not packet_path.exists():
        return _check("publication_packet", False, f"publication packet not found: {packet_path}")
    try:
        packet = _read_json_file(packet_path, "publication packet")
    except ValueError as exc:
        return _check("publication_packet", False, str(exc))
    errors = _validate_schema_payload(root, "release_publication_packet", packet)
    failures: list[str] = [*errors]
    if packet.get("release_id") != report.get("release_id"):
        failures.append("packet release_id does not match dry-run report")
    if packet.get("source_commit") != report.get("source_commit"):
        failures.append("packet source_commit does not match dry-run report")
    dry_run = packet.get("dry_run", {}) if isinstance(packet.get("dry_run"), dict) else {}
    if dry_run.get("report_sha256") != _sha256_file(dry_run_report_path):
        failures.append("packet dry_run.report_sha256 does not match dry-run report file")
    if dry_run.get("check_count") != len(report.get("checks", [])):
        failures.append("packet dry_run.check_count does not match report")
    if dry_run.get("artifact_count") != len(report.get("release_artifacts", [])):
        failures.append("packet dry_run.artifact_count does not match report")
    signing = packet.get("signing", {}) if isinstance(packet.get("signing"), dict) else {}
    if signing.get("tag_name") != report.get("release_id"):
        failures.append("packet signing.tag_name does not match release_id")
    reviewed = packet.get("reviewed_inputs", {}) if isinstance(packet.get("reviewed_inputs"), dict) else {}
    reviewed_event_ids = reviewed.get("reviewed_event_ids", [])
    if not isinstance(reviewed_event_ids, list):
        failures.append("packet reviewed_event_ids must be a list")
        reviewed_event_ids = []
    event_ids = {read_json_from_text(path.read_text(encoding="utf-8"))["id"] for path in event_paths(root)}
    missing_events = sorted(
        event_id for event_id in reviewed_event_ids if isinstance(event_id, str) and event_id not in event_ids
    )
    if missing_events:
        failures.append(f"packet reviewed event id(s) not found: {', '.join(missing_events)}")
    if packet.get("publication_decision") == "publish" and not reviewed_event_ids:
        failures.append("publish packet must include at least one reviewed event id")
    if packet.get("publication_decision") == "skip" and reviewed_event_ids:
        failures.append("skip packet must not include reviewed event ids")
    if require_publish_packet and packet.get("publication_decision") != "publish":
        failures.append("publication packet must be a publish packet")
    return _check(
        "publication_packet",
        not failures,
        "publication packet schema, dry-run hash, counts, reviewed events, signing tag, and source commit are consistent"
        if not failures
        else "; ".join(failures),
    )


def verify_release_artifacts(
    root: Path,
    *,
    dry_run_report_path: Path,
    publication_packet_path: Path | None = None,
    artifacts_root: Path | None = None,
    expected_release_id: str | None = None,
    expected_source_commit: str | None = None,
    require_publish_packet: bool = False,
) -> ReleaseVerificationResult:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    checks: list[ReleaseCheck] = []
    verified_artifacts: list[dict[str, Any]] = []
    report: dict[str, Any] | None = None
    resolved_artifacts_root = artifacts_root
    try:
        report = _read_json_file(dry_run_report_path, "dry-run report")
    except ValueError as exc:
        checks.append(_check("dry_run_report", False, str(exc)))
    if report is not None:
        schema_errors = _validate_schema_payload(root, "release_dry_run", report)
        checks.append(
            _check(
                "dry_run_report_schema",
                not schema_errors,
                "dry-run report matches schema" if not schema_errors else "; ".join(schema_errors),
            )
        )
        failed_report_checks = [
            str(check.get("name"))
            for check in report.get("checks", [])
            if isinstance(check, dict) and check.get("status") != "pass"
        ]
        checks.append(
            _check(
                "dry_run_report_checks",
                not failed_report_checks,
                f"{len(report.get('checks', []))} dry-run check(s) passed"
                if not failed_report_checks
                else f"failed dry-run checks: {', '.join(failed_report_checks)}",
            )
        )
        if expected_release_id is not None:
            checks.append(
                _check(
                    "expected_release_id",
                    report.get("release_id") == expected_release_id,
                    f"expected {expected_release_id}; found {report.get('release_id')}",
                )
            )
        if expected_source_commit is not None:
            checks.append(
                _check(
                    "expected_source_commit",
                    report.get("source_commit") == expected_source_commit,
                    f"expected {expected_source_commit}; found {report.get('source_commit')}",
                )
            )
        resolved_artifacts_root = _artifact_root_from_report(root, dry_run_report_path, report, artifacts_root)
        artifact_check, verified_artifacts, artifact_text = _verify_release_artifact_files(
            resolved_artifacts_root,
            report,
        )
        checks.append(artifact_check)
        checks.append(
            _verify_manifest_and_checksums(
                root,
                resolved_artifacts_root,
                report,
                artifact_text,
            )
        )
        checks.append(
            _verify_publication_packet(
                root,
                packet_path=publication_packet_path,
                dry_run_report_path=dry_run_report_path,
                report=report,
                require_publish_packet=require_publish_packet,
            )
        )
    verification = {
        "schema_version": RELEASE_VERIFICATION_SCHEMA_VERSION,
        "created_at": created_at,
        "verified": all(check.status == "pass" for check in checks),
        "release_id": report.get("release_id") if report else None,
        "source_commit": report.get("source_commit") if report else None,
        "dry_run_report_path": _relative_or_absolute(root, dry_run_report_path),
        "publication_packet_path": _relative_or_absolute(root, publication_packet_path)
        if publication_packet_path is not None
        else None,
        "artifacts_root": _relative_or_absolute(root, resolved_artifacts_root)
        if resolved_artifacts_root is not None
        else None,
        "checks": [check.__dict__ for check in checks],
        "verified_artifacts": verified_artifacts,
    }
    result_errors = _validate_schema_payload(root, "release_verification", verification)
    if result_errors:
        checks.append(_check("release_verification_schema", False, "; ".join(result_errors)))
        verification["verified"] = False
        verification["checks"] = [check.__dict__ for check in checks]
    failed_checks = [check for check in checks if check.status != "pass"]
    return ReleaseVerificationResult(
        report=verification,
        failed_checks=failed_checks,
    )


def build_release_publication_packet(
    root: Path,
    *,
    dry_run_report_path: Path,
    release_manager: str,
    source_owner: str,
    source_owner_approval_ref: str,
    release_manager_approval_ref: str,
    branch_protection_ref: str,
    ci_ref: str,
    codeql_workflow_ref: str,
    code_scanning_ref: str,
    dependency_review_ref: str,
    scorecard_ref: str,
    attestation_ref: str,
    checksum_review_ref: str,
    reviewed_event_ids: list[str],
    allow_no_reviewed_events: bool = False,
    no_reviewed_events_reason: str | None = None,
) -> dict[str, Any]:
    if not dry_run_report_path.exists():
        raise ValueError(f"dry-run report not found: {dry_run_report_path}")
    report = read_json_from_text(dry_run_report_path.read_text(encoding="utf-8"))
    report_errors = _validate_schema_payload(root, "release_dry_run", report)
    if report_errors:
        raise ValueError(f"invalid release dry-run report: {'; '.join(report_errors)}")
    failed_checks = [
        str(check.get("name"))
        for check in report.get("checks", [])
        if check.get("status") != "pass"
    ]
    if failed_checks:
        raise ValueError(f"release dry-run report has failed checks: {', '.join(failed_checks)}")

    event_ids = {read_json_from_text(path.read_text(encoding="utf-8"))["id"] for path in event_paths(root)}
    missing_events = sorted(set(reviewed_event_ids) - event_ids)
    if missing_events:
        raise ValueError(f"reviewed event id(s) not found in data/events: {', '.join(missing_events)}")
    if not reviewed_event_ids and not allow_no_reviewed_events:
        raise ValueError("at least one --reviewed-event is required unless --allow-no-reviewed-events is set")
    if not reviewed_event_ids and not no_reviewed_events_reason:
        raise ValueError("--skip-reason is required when no reviewed events are included")
    if reviewed_event_ids and no_reviewed_events_reason:
        raise ValueError("--skip-reason is only valid with --allow-no-reviewed-events and no reviewed events")

    release_id = str(report["release_id"])
    release_date = str(report["release_date"])
    source_commit = str(report["source_commit"])
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    reviewed_events = sorted(set(reviewed_event_ids))
    publication_decision = "publish" if reviewed_events else "skip"
    tag_name = release_id
    packet = {
        "schema_version": RELEASE_PUBLICATION_PACKET_SCHEMA_VERSION,
        "release_id": release_id,
        "release_date": release_date,
        "source_commit": source_commit,
        "created_at": created_at,
        "publication_decision": publication_decision,
        "dry_run": {
            "report_path": _relative_or_absolute(root, dry_run_report_path),
            "report_sha256": _sha256_file(dry_run_report_path),
            "check_count": len(report["checks"]),
            "artifact_count": len(report["release_artifacts"]),
        },
        "reviewed_inputs": {
            "reviewed_event_ids": reviewed_events,
            "source_owner": source_owner,
            "source_owner_approval_ref": source_owner_approval_ref,
            "no_reviewed_events_reason": no_reviewed_events_reason,
        },
        "required_external_evidence": {
            "branch_protection_ref": branch_protection_ref,
            "ci_ref": ci_ref,
            "codeql_workflow_ref": codeql_workflow_ref,
            "code_scanning_ref": code_scanning_ref,
            "dependency_review_ref": dependency_review_ref,
            "scorecard_ref": scorecard_ref,
            "attestation_ref": attestation_ref,
            "checksum_review_ref": checksum_review_ref,
            "release_manager_approval_ref": release_manager_approval_ref,
        },
        "signing": {
            "mechanism": "manual_release_manager_signed_git_tag",
            "tag_name": tag_name,
            "required_commands": [
                f"git tag -s {tag_name}",
                f"git tag -v {tag_name}",
                f"git push origin {tag_name}",
            ],
            "key_boundary": f"{release_manager} signs locally; signing keys are not stored in GitHub Actions, repository secrets, environment secrets, or OIDC jobs.",
        },
        "token_boundary": {
            "publisher_workflow_mode": "protected_main_noop_or_packet_only",
            "no_release_tokens_in_untrusted_lanes": True,
            "forbidden_untrusted_lanes": [
                "source-refresh",
                "candidate-generation",
                "llm-review",
                "codex-review",
                "issue-or-pr-comment-processing",
                "mcp",
                "provider-page-fetch",
                "social-or-community-source-processing",
            ],
        },
        "rollback": {
            "policy": "If a data release is materially wrong, publish a corrected or superseding data release and record the source-owner and release-manager decision.",
            "forbidden_actions": [
                "delete-and-recreate-data-tag",
                "rewrite-release-evidence",
                "publish-from-unreviewed-candidates",
            ],
        },
    }
    packet_errors = _validate_schema_payload(root, "release_publication_packet", packet)
    if packet_errors:
        raise ValueError(f"invalid release publication packet: {'; '.join(packet_errors)}")
    return packet


def _release_manifest_schema_check(root: Path, manifest: dict[str, Any]) -> ReleaseCheck:
    schema = load_schemas(root)["release_manifest"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    if not errors:
        return _check("release_manifest_schema", True, "CalVer release manifest matches schema")
    rendered = []
    for error in errors:
        location = ".".join(str(part) for part in error.path)
        rendered.append(f"{location}: {error.message}" if location else error.message)
    return _check("release_manifest_schema", False, "; ".join(rendered))


def _release_evidence_index_schema_check(
    root: Path,
    artifacts: dict[Path, str],
    release_id: str,
) -> ReleaseCheck:
    path = Path(f"data/releases/{release_id}/evidence-index.json")
    text = artifacts.get(path)
    if text is None:
        return _check("release_evidence_index_schema", False, f"{path}: missing from generated artifacts")
    evidence_index = read_json_from_text(text)
    errors = _validate_schema_payload(root, "release_evidence_index", evidence_index)
    if errors:
        return _check("release_evidence_index_schema", False, "; ".join(errors))
    return _check("release_evidence_index_schema", True, "release evidence index matches schema")


def run_release_dry_run(
    root: Path,
    *,
    release_date: date,
    output_dir: Path,
    release_id: str | None = None,
    source_commit: str | None = None,
    require_clean: bool = False,
) -> ReleaseDryRunResult:
    resolved_release_id = release_id or calver_release_id(release_date)
    release_id_date = parse_release_id_date(resolved_release_id)
    if release_id_date != release_date:
        raise ValueError(
            f"release_id date must match release_date {release_date.isoformat()}: {resolved_release_id}"
        )
    source_commit = _source_commit(root, source_commit)
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    release_output_dir = output_dir / resolved_release_id
    artifacts_root = release_output_dir / "artifacts"
    report_path = release_output_dir / "dry-run-report.json"

    checks: list[ReleaseCheck] = [
        _check(
            "release_id_calver",
            True,
            f"release id {resolved_release_id}",
        ),
        _check(
            "source_commit",
            source_commit is not None and bool(re.fullmatch(r"[0-9a-f]{40}", source_commit)),
            source_commit or "git source commit unavailable",
        ),
        _check(
            "working_tree_clean",
            (not require_clean) or _is_working_tree_clean(root),
            "working tree clean" if require_clean else "not required for this dry run",
        ),
        _package_version_check(),
    ]

    validation_issues = validate(root)
    checks.append(
        _check(
            "schema_and_repo_validation",
            not validation_issues,
            "apw validate checks passed" if not validation_issues else "; ".join(issue.render() for issue in validation_issues),
        )
    )
    source_issues = validate_source_packages(root) + validate_parser_fixtures(root)
    checks.append(
        _check(
            "source_package_fixtures",
            not source_issues,
            "source package and parser fixtures passed" if not source_issues else "; ".join(issue.render() for issue in source_issues),
        )
    )

    dev_diffs = artifact_diffs(root, build_artifacts(root))
    checks.append(
        _check(
            "generated_dev_artifacts_current",
            not dev_diffs,
            "tracked dev feeds, indexes, and manifest are current"
            if not dev_diffs
            else f"out of date: {', '.join(dev_diffs)}",
        )
    )
    checks.append(_source_coverage_check(root, created_at=created_at))
    checks.append(_operations_report_check(root, created_at=created_at))
    checks.append(_v1_launch_gate_check(root, created_at=created_at))
    checks.append(_release_automation_readiness_check(root, created_at=created_at))

    release_artifacts = build_artifacts(
        root,
        resolved_release_id,
        source_commit=source_commit,
        created_at=created_at,
        notes="Dry-run CalVer data release manifest. No tag or artifact was published.",
    )
    manifest_path = Path(f"data/releases/{resolved_release_id}/manifest.json")
    manifest = read_json_from_text(release_artifacts[manifest_path])
    checks.append(_release_manifest_schema_check(root, manifest))
    checks.append(_release_evidence_index_schema_check(root, release_artifacts, resolved_release_id))
    checks.append(_checksum_check(release_artifacts, manifest))
    checks.append(_license_check(root))
    checks.append(
        _check(
            "dependency_lock",
            (root / "uv.lock").exists(),
            "uv.lock is present; CI and release dry run execute uv lock --check",
        )
    )
    checks.append(_codeql_workflow_check(root))
    checks.append(_dependency_review_workflow_check(root))
    checks.append(_release_workflow_guardrails_check(root))
    checks.append(_data_publisher_noop_workflow_check(root))
    checks.append(_source_refresh_token_boundary_check(root))
    checks.append(_scorecard_workflow_check(root))
    checks.append(_source_ownership_check(root))
    checks.append(_maintainer_release_docs_check(root))

    report = {
        "schema_version": RELEASE_DRY_RUN_SCHEMA_VERSION,
        "release_id": resolved_release_id,
        "release_date": release_date.isoformat(),
        "created_at": created_at,
        "source_commit": source_commit,
        "output_dir": str(release_output_dir),
        "validation_commands": [
            "uv lock --check",
            "uv run ruff check .",
            "uv run pytest",
            "uv run apw source test",
            "uv run apw source coverage --summary",
            "uv run apw operations report --summary",
            "uv run apw operations launch-gate --summary",
            "uv run apw release automation-readiness --summary",
            "uv run apw validate",
            "uv run apw index --check",
            "actionlint .github/workflows/*.yml",
            f"uv run apw release dry-run --release-date {release_date.isoformat()} --output {output_dir}",
            f"uv run apw release verify --dry-run-report {output_dir / resolved_release_id / 'dry-run-report.json'} --release-id {resolved_release_id} --source-commit {source_commit or '<source-commit>'}",
        ],
        "checks": [check.__dict__ for check in checks],
        "release_artifacts": manifest["artifacts"],
        "external_required_checks": _external_release_gates(),
    }
    schema_check = _schema_check(root, report)
    checks.append(schema_check)
    report["checks"] = [check.__dict__ for check in checks]

    write_artifacts(artifacts_root, release_artifacts)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(write_json_text(report), encoding="utf-8")

    failed_checks = [check for check in checks if check.status != "pass"]
    return ReleaseDryRunResult(
        report=report,
        failed_checks=failed_checks,
        output_dir=release_output_dir,
        report_path=report_path,
    )


def read_json_from_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"invalid generated release manifest JSON: {exc}") from exc
