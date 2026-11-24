from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.cli import main
from ai_provider_watch.core.io import read_json

ROOT = Path(__file__).resolve().parents[1]
DOWNSTREAM_REPO = ROOT / "tests" / "fixtures" / "downstream-repo"
SCENARIOS_PATH = ROOT / "examples" / "adoption" / "scenarios.json"

REQUIRED_AUDIENCES = {
    "catalog-maintainers",
    "coding-agent-maintainers",
    "finops",
    "gateway-maintainers",
    "github-action-users",
    "helicone-users",
    "langfuse-users",
    "litellm-users",
    "models-dev-users",
    "observability-teams",
    "openlit-users",
    "platform-engineers",
    "platform-oncall",
    "slack-operators",
    "webhook-operators",
}

REQUIRED_USE_CASES = {
    "agent_dashboard",
    "catalog",
    "caching_change",
    "coding_agent_dashboard",
    "cost",
    "gateway",
    "github_action",
    "helicone",
    "incident_response",
    "langfuse",
    "litellm",
    "model_retirement",
    "models-dev",
    "notification",
    "observability",
    "openlit",
    "repository_impact",
    "slack",
    "status_incident",
    "token_accounting",
    "quota",
    "webhook",
    "workflow_behavior_change",
}

FORBIDDEN_TERMS = {
    '"api_key"',
    '"contents: write"',
    '"github_token"',
    '"pull-requests: write"',
    '"secret"',
    '"slack_webhook_url"',
    '"token"',
    '"webhook_url"',
    "advisor",
    "authorization",
    "customer telemetry",
    "ottto account",
    "secrets.",
}


def _schema(relative_path: str) -> dict[str, Any]:
    return read_json(ROOT / relative_path)


def _assert_valid(relative_schema_path: str, payload: dict[str, Any]) -> None:
    validator = Draft202012Validator(
        _schema(relative_schema_path),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert [error.message for error in errors] == []


def _scenarios() -> dict[str, Any]:
    return read_json(SCENARIOS_PATH)


def _command_argv(scenario: dict[str, Any], output: Path) -> list[str]:
    argv = []
    for item in scenario["command"]["argv"]:
        argv.append(
            item.replace("{downstream_repo}", str(DOWNSTREAM_REPO)).replace(
                "{output}",
                str(output),
            )
        )
    return argv


def _normalized(payload: dict[str, Any], normalizers: list[str]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload))
    if "repo_path" in normalizers:
        normalized["repo_path"] = "<DOWNSTREAM_REPO>"
    return normalized


def test_adoption_scenarios_manifest_is_schema_valid() -> None:
    manifest = _scenarios()

    _assert_valid("schemas/adoption-scenarios.schema.json", manifest)

    ids = [scenario["id"] for scenario in manifest["scenarios"]]
    assert len(ids) == len(set(ids))


def test_adoption_scenarios_cover_north_star_downstream_workflows() -> None:
    scenarios = _scenarios()["scenarios"]
    audiences = {audience for scenario in scenarios for audience in scenario["audiences"]}
    use_cases = {use_case for scenario in scenarios for use_case in scenario["use_cases"]}

    assert REQUIRED_AUDIENCES <= audiences
    assert REQUIRED_USE_CASES <= use_cases


def test_adoption_scenarios_are_offline_and_read_only() -> None:
    manifest_text = SCENARIOS_PATH.read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN_TERMS:
        assert forbidden not in manifest_text

    for scenario in _scenarios()["scenarios"]:
        assert scenario["credentials_required"] is False
        assert scenario["network_required"] is False
        assert scenario["write_scope"] == "local_output_only"
        assert scenario["command"]["argv"][0] in {"dashboard", "ecosystem", "notify", "repo"}
        assert "untrusted" in scenario["untrusted_input_policy"].lower()


def test_adoption_scenario_links_are_real() -> None:
    for scenario in _scenarios()["scenarios"]:
        for doc_path in scenario["docs"]:
            assert (ROOT / doc_path).is_file()
        assert (ROOT / scenario["expected"]["fixture"]).is_file()
        assert (ROOT / scenario["expected"]["schema"]).is_file()


def test_adoption_scenarios_execute_against_smoke_fixtures(tmp_path: Path) -> None:
    for scenario in _scenarios()["scenarios"]:
        output = tmp_path / f"{scenario['id']}.json"
        argv = _command_argv(scenario, output)

        assert main(["--root", str(ROOT), *argv]) == 0
        payload = read_json(output)

        expected = scenario["expected"]
        _assert_valid(expected["schema"], payload)
        assert _normalized(payload, scenario["command"].get("normalizers", [])) == read_json(
            ROOT / expected["fixture"]
        )


def test_adoption_scenarios_doc_points_to_manifest_and_guardrails() -> None:
    docs = (ROOT / "docs" / "integrations" / "adoption-scenarios.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(docs.split())

    for phrase in [
        "examples/adoption/scenarios.json",
        "schemas/adoption-scenarios.schema.json",
        "uv run pytest tests/test_adoption_scenarios.py",
        "No Ottto account is required",
        "No provider credentials",
        "remain untrusted data",
        "APW examples do not open upstream PRs",
        "status incident routing",
        "pricing, caching, and token-accounting review hints",
        "local coding-agent dashboard JSON",
    ]:
        assert phrase in normalized
