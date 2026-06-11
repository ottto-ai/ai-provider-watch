from __future__ import annotations

import json
from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.pipeline.source_refresh_gate import (
    build_source_refresh_review_gate,
    render_source_refresh_review_gate_summary,
    write_github_output,
)


def test_review_gate_skips_noop_refresh() -> None:
    gate = build_source_refresh_review_gate(
        {"changed_source_keys": []},
        {"candidate_count": 0},
    )

    assert gate["review_needed"] is False
    assert gate["recommendation"] == "skip_candidate_review_pr"
    assert gate["reason"] == "no_changed_sources_or_candidates"
    assert gate["changed_source_count"] == 0
    assert gate["candidate_count"] == 0


def test_review_gate_opens_for_changed_source_or_candidate() -> None:
    gate = build_source_refresh_review_gate(
        {"changed_source_keys": ["openai.news", "openai.news", 123]},
        {"candidate_count": 2},
    )

    assert gate["review_needed"] is True
    assert gate["recommendation"] == "open_candidate_review_pr"
    assert gate["reason"] == "reviewable_source_or_candidate_changes"
    assert gate["changed_source_keys"] == ["openai.news"]
    assert gate["changed_source_count"] == 1
    assert gate["candidate_count"] == 2


def test_review_gate_opens_for_candidate_without_changed_source() -> None:
    gate = build_source_refresh_review_gate(
        {"changed_source_keys": []},
        {"candidate_count": 1},
    )

    assert gate["review_needed"] is True
    assert gate["recommendation"] == "open_candidate_review_pr"
    assert gate["changed_source_count"] == 0
    assert gate["candidate_count"] == 1


def test_review_gate_distinguishes_source_state_only_refresh() -> None:
    gate = build_source_refresh_review_gate(
        {"changed_source_keys": ["openai.api_changelog"]},
        {"candidate_count": 0},
    )

    assert gate["review_needed"] is True
    assert gate["recommendation"] == "open_source_state_refresh_pr"
    assert gate["reason"] == "source_fingerprint_changes_without_candidates"
    assert gate["changed_source_keys"] == ["openai.api_changelog"]
    assert gate["changed_source_count"] == 1
    assert gate["candidate_count"] == 0


def test_review_gate_summary_and_github_output(tmp_path: Path) -> None:
    gate = build_source_refresh_review_gate(
        {"changed_source_keys": ["anthropic.news"]},
        {"candidate_count": 1},
    )
    output_path = tmp_path / "github-output.txt"

    summary = render_source_refresh_review_gate_summary(gate)
    write_github_output(output_path, gate)

    assert "review_needed: true" in summary
    assert "changed_source_keys: anthropic.news" in summary
    assert "candidate_count: 1" in summary
    assert "review_needed=true" in output_path.read_text(encoding="utf-8")
    assert "recommendation=open_candidate_review_pr" in output_path.read_text(encoding="utf-8")


def test_source_review_needed_cli_writes_json_summary_and_github_output(
    tmp_path: Path,
    capsys,
) -> None:
    observations = tmp_path / "observations.json"
    generation = tmp_path / "candidate-generation.json"
    output = tmp_path / "gate.json"
    github_output = tmp_path / "github-output.txt"
    observations.write_text(json.dumps({"changed_source_keys": []}), encoding="utf-8")
    generation.write_text(json.dumps({"candidate_count": 0}), encoding="utf-8")

    assert (
        main(
            [
                "source",
                "review-needed",
                "--observations",
                str(observations),
                "--candidate-generation",
                str(generation),
                "--output",
                str(output),
                "--github-output",
                str(github_output),
                "--summary",
            ]
        )
        == 0
    )

    stdout = capsys.readouterr().out
    payload = json.loads(output.read_text(encoding="utf-8"))
    step_output = github_output.read_text(encoding="utf-8")
    assert "review_needed: false" in stdout
    assert payload["review_needed"] is False
    assert payload["recommendation"] == "skip_candidate_review_pr"
    assert "review_needed=false" in step_output
    assert "candidate_count=0" in step_output
