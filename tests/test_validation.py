from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.io import read_json
from ai_provider_watch.core.validation import load_schemas, validate

ROOT = Path(__file__).resolve().parents[1]


def test_repository_validates() -> None:
    assert [issue.render() for issue in validate(ROOT)] == []


def test_fixture_event_matches_schema() -> None:
    schemas = load_schemas(ROOT)
    event = read_json(ROOT / "tests/fixtures/events/2026-05-31-openai-status-fixture.json")
    assert not list(Draft202012Validator(schemas["event"], format_checker=FormatChecker()).iter_errors(event))
    assert not list(Draft202012Validator(schemas["event_detail"], format_checker=FormatChecker()).iter_errors(event["detail"]))
    for impact in event["impacts"]:
        assert not list(Draft202012Validator(schemas["impact"], format_checker=FormatChecker()).iter_errors(impact))
