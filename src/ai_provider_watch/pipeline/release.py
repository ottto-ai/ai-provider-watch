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
from ai_provider_watch.core.io import write_json_text
from ai_provider_watch.core.validation import load_schemas, validate
from ai_provider_watch.source_watch.fixtures import validate_parser_fixtures
from ai_provider_watch.sources.registry import validate_source_packages

RELEASE_DRY_RUN_SCHEMA_VERSION = "apw.release_dry_run.v0"
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
            "uv run apw validate",
            "uv run apw index --check",
            "uv build --out-dir .apw/dist",
            "--require-clean",
            "apw-release-dry-run.tgz",
            "actions/attest@v4",
            "subject-path: .apw/apw-release-dry-run.tgz",
            "actions/upload-artifact@v4",
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
            "details": "The public data tag must be signed by a release manager or created by a protected publisher after the publisher exists.",
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
    checks.append(_source_refresh_token_boundary_check(root))
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
            "uv run apw validate",
            "uv run apw index --check",
            "actionlint .github/workflows/*.yml",
            f"uv run apw release dry-run --release-date {release_date.isoformat()} --output {output_dir}",
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
