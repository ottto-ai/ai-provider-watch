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
