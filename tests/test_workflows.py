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

    assert "permissions:\n  contents: read" in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
    assert "uv build --out-dir .apw/dist" in workflow
    assert "uv lock --check" in workflow
    assert "uv venv .apw/install-smoke --python 3.12 --seed" in workflow
    assert "python -m pip install .apw/dist/*.whl" in workflow
    assert "apw --root \"$PWD\" release dry-run" in workflow
    assert "--require-clean" in workflow
    assert "actions/upload-artifact@v4" in workflow


def test_dependency_review_workflow_is_read_only() -> None:
    workflow = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "permissions:\n  contents: read\n  pull-requests: read" in workflow
    assert "actions/dependency-review-action@v4" in workflow
