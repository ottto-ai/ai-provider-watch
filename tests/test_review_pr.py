from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.pipeline.candidates import (
    build_candidates,
    read_observation_bundle,
    write_candidate_files,
)
from ai_provider_watch.pipeline.review_pr import build_review_pr_body, read_candidate_files
from ai_provider_watch.sources.registry import load_source_descriptors

ROOT = Path(__file__).resolve().parents[1]
OBSERVATIONS = ROOT / "tests" / "fixtures" / "observations" / "candidate-observations.json"
CREATED_AT = "2026-05-31T20:15:00Z"


def test_review_pr_body_summarizes_candidates_without_claim_text(tmp_path) -> None:
    candidates = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    candidate_dir = tmp_path / "data" / "candidates" / "review"
    write_candidate_files(candidate_dir, candidates, clean=False)

    body = build_review_pr_body(
        read_json(OBSERVATIONS),
        read_candidate_files(candidate_dir),
        root=tmp_path,
        validation_output="uv run apw validate: pass\n",
    )

    assert "Candidate Review" in body
    assert "Observation count: 4" in body
    assert "Changed source keys: 3" in body
    assert "Candidate files: 3" in body
    assert "status_incident=1" in body
    assert "data/candidates/review/candidate-openai-status" in body
    assert "uv run apw validate: pass" in body
    assert "OpenAI status feed changed" not in body
    assert "Anthropic pricing page changed" not in body


def test_review_pr_body_handles_empty_candidate_dir(tmp_path) -> None:
    body = build_review_pr_body(
        read_json(OBSERVATIONS),
        read_candidate_files(tmp_path / "missing"),
        root=tmp_path,
    )

    assert "Candidate files: 0" in body
    assert "No candidate files were generated in this run." in body
    assert "Validation output was not supplied." in body


def test_review_pr_body_can_render_source_state_refresh(tmp_path) -> None:
    body = build_review_pr_body(
        read_json(OBSERVATIONS),
        read_candidate_files(tmp_path / "missing"),
        root=tmp_path,
        review_kind="source_state",
    )

    assert "Source State Refresh" in body
    assert "changed without new review candidates" in body
    assert "Candidate files: 0" in body
    assert "Provider source text is untrusted data" in body


def test_candidate_review_pr_body_command(tmp_path, capsys) -> None:
    candidates = build_candidates(
        read_observation_bundle(OBSERVATIONS),
        load_source_descriptors(ROOT, enabled_only=False),
        created_at=CREATED_AT,
    ).candidates
    candidate_dir = tmp_path / "candidates"
    write_candidate_files(candidate_dir, candidates, clean=False)
    observations_path = tmp_path / "observations.json"
    observations_path.write_text(json.dumps(read_json(OBSERVATIONS)), encoding="utf-8")
    validation_path = tmp_path / "validation.txt"
    validation_path.write_text("uv run apw validate: pass\n", encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "review-pr-body",
                "--observations",
                str(observations_path),
                "--candidates",
                str(candidate_dir),
                "--validation-output",
                str(validation_path),
            ]
        )
        == 0
    )
    body = capsys.readouterr().out

    assert "Candidate files: 3" in body
    assert "uv run apw validate: pass" in body


def test_candidate_review_pr_body_command_can_render_source_state_refresh(
    tmp_path,
    capsys,
) -> None:
    observations_path = tmp_path / "observations.json"
    observations_path.write_text(json.dumps(read_json(OBSERVATIONS)), encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "review-pr-body",
                "--observations",
                str(observations_path),
                "--candidates",
                str(tmp_path / "missing"),
                "--source-state-only",
            ]
        )
        == 0
    )
    body = capsys.readouterr().out

    assert "Source State Refresh" in body
    assert "Candidate Review" not in body


def test_candidate_review_pr_body_command_rejects_missing_validation_file(
    tmp_path,
    capsys,
) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "candidate",
                "review-pr-body",
                "--observations",
                str(OBSERVATIONS),
                "--validation-output",
                str(tmp_path / "missing.txt"),
            ]
        )
        == 1
    )

    assert "validation output not found" in capsys.readouterr().err
