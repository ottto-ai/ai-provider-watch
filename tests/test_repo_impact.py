from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json
from ai_provider_watch.pipeline.repo_impact import repo_impact_report

ROOT = Path(__file__).resolve().parents[1]


def test_repo_impact_matches_model_refs_without_copying_source_lines(tmp_path) -> None:
    repo = tmp_path / "downstream"
    repo.mkdir()
    (repo / "app.py").write_text(
        'MODEL = "gpt-3.5-turbo-instruct"\nPROVIDER = "openai"\n',
        encoding="utf-8",
    )

    report = repo_impact_report(ROOT, repo, since="2024-01-01", risk="low")
    rendered = json.dumps(report)

    assert report["event_count"] >= 1
    assert "2024-01-04-openai-gpt3-completions-retirement" in {
        event["id"] for event in report["events"]
    }
    assert "model:gpt-3.5-turbo-instruct" in report["matched_refs"]
    assert 'MODEL = "gpt-3.5-turbo-instruct"' not in rendered
    assert "line_sha256" not in rendered


def test_repo_impact_is_quiet_for_unrelated_repo(tmp_path) -> None:
    repo = tmp_path / "downstream"
    repo.mkdir()
    (repo / "README.md").write_text("No AI provider refs here.\n", encoding="utf-8")

    report = repo_impact_report(ROOT, repo, since="2024-01-01", risk="low")

    assert report["matched_refs"] == []
    assert report["events"] == []


def test_repo_check_cli_writes_report(tmp_path) -> None:
    repo = tmp_path / "downstream"
    repo.mkdir()
    (repo / "config.yaml").write_text("provider: openai\n", encoding="utf-8")
    output = tmp_path / "impact.json"

    assert (
        main(
            [
                "--root",
                str(ROOT),
                "repo",
                "check",
                "--repo",
                str(repo),
                "--since",
                "2024-01-01",
                "--risk",
                "low",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    assert read_json(output)["event_count"] >= 1


def test_github_action_summary_fails_on_threshold(tmp_path) -> None:
    report = {
        "scanned_files": 1,
        "matched_refs": ["provider:openai"],
        "events": [
            {
                "id": "event-1",
                "title": "Medium event",
                "event_date": "2024-01-01",
                "severity": "medium",
                "matched_refs": ["provider:openai"],
            }
        ],
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "github_action_summary.py"),
            "--report",
            str(report_path),
            "--fail-on-severity",
            "medium",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "APW matched event severity medium >= medium" in result.stderr
