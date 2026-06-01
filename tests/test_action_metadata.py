from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_downstream_action_is_composite_and_token_minimal() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")

    assert "using: composite" in action
    assert 'python -m pip install "$GITHUB_ACTION_PATH"' in action
    assert "apw repo check" in action
    assert "github_action_summary.py" in action
    assert "secrets." not in action
    assert "pull_request_target:" not in action
    assert "contents: write" not in action
    assert "pull-requests: write" not in action
    assert "gh pr" not in action
    assert "gh release" not in action
    assert "git tag" not in action
