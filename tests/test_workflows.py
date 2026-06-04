from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_refresh_workflow_detects_untracked_candidate_files() -> None:
    workflow = (ROOT / ".github/workflows/source-refresh.yml").read_text(encoding="utf-8")

    assert "git status --porcelain -- data/source-state/fingerprints.json data/candidates" in workflow
    assert "git diff --quiet -- data/source-state/fingerprints.json data/candidates" not in workflow


def test_source_refresh_workflow_cleans_generated_review_candidates() -> None:
    workflow = (ROOT / ".github/workflows/source-refresh.yml").read_text(encoding="utf-8")

    assert "--output data/candidates/review" in workflow
    assert "--clean" in workflow


def test_release_dry_run_workflow_runs_install_smoke_and_has_no_publish_token() -> None:
    workflow = (ROOT / ".github/workflows/release-data.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read\n  id-token: write\n  attestations: write" in workflow
    assert "contents: write" not in workflow
    assert "secrets." not in workflow
    assert "gh release" not in workflow
    assert "git tag" not in workflow
    assert "uv build --out-dir .apw/dist" in workflow
    assert "uv lock --check" in workflow
    assert "uv venv .apw/install-smoke --python 3.12 --seed" in workflow
    assert "python -m pip install .apw/dist/*.whl" in workflow
    assert "apw --root \"$PWD\" release dry-run" in workflow
    assert "--require-clean" in workflow
    assert "apw-release-dry-run.tgz" in workflow
    assert "actions/attest@v4" in workflow
    assert "subject-path: .apw/apw-release-dry-run.tgz" in workflow
    assert "actions/upload-artifact@v4" in workflow


def test_dependency_review_workflow_is_read_only() -> None:
    workflow = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "base_ref:" in workflow
    assert "head_ref:" in workflow
    assert "permissions:\n  contents: read\n  pull-requests: read" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "pull_request_target:" not in workflow
    assert "actions/dependency-review-action@v5" in workflow
    assert "base-ref: ${{ inputs.base_ref }}" in workflow
    assert "head-ref: ${{ inputs.head_ref }}" in workflow


def test_python_publish_workflow_uses_trusted_publishing_environment() -> None:
    workflow = (ROOT / ".github/workflows/publish-python.yml").read_text(encoding="utf-8")

    assert '      - "v*"' in workflow
    assert "pull_request:" not in workflow
    assert "pull_request_target:" not in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "needs: build" in workflow
    assert "if: startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "packages-dir: dist/" in workflow
    assert "print-hash: true" in workflow
    assert "username:" not in workflow
    assert "password:" not in workflow
    assert "secrets." not in workflow
    assert "gh release" not in workflow
    assert "git tag" not in workflow


def test_source_refresh_workflow_has_no_release_token_path() -> None:
    workflow = (ROOT / ".github/workflows/source-refresh.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: write\n  pull-requests: write" in workflow
    assert "gh pr create" in workflow
    assert "secrets." not in workflow
    assert "id-token: write" not in workflow
    assert "gh release" not in workflow
    assert "git tag" not in workflow
    assert "pull_request_target:" not in workflow


def test_source_refresh_workflow_cleans_branch_when_pr_create_fails() -> None:
    workflow = (ROOT / ".github/workflows/source-refresh.yml").read_text(encoding="utf-8")

    assert "pr_created=0" in workflow
    assert 'if [ "$pr_created" != "1" ]; then' in workflow
    assert 'git push origin --delete "$branch"' in workflow
    assert "trap cleanup_branch EXIT" in workflow
    assert "pr_created=1" in workflow
    assert "trap - EXIT" in workflow


def test_source_refresh_workflow_uses_node24_compatible_setup_python() -> None:
    workflow = (ROOT / ".github/workflows/source-refresh.yml").read_text(encoding="utf-8")

    assert "actions/setup-python@v6" in workflow
    assert "actions/setup-python@v5" not in workflow


def test_llm_review_request_workflow_is_read_only_and_artifact_only() -> None:
    workflow = (ROOT / ".github/workflows/llm-review-request.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read\n  pull-requests: read" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "gh pr" not in workflow
    assert "gh release" not in workflow
    assert "git tag" not in workflow
    assert "pull_request_target:" not in workflow
    assert "uv run apw \"${args[@]}\"" in workflow
    assert "actions/upload-artifact@v4" in workflow
