from __future__ import annotations

import json
import shutil
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


def test_validate_reports_malformed_source_descriptor_without_crashing(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    registry_path = tmp_path / "sources" / "registry.json"
    registry = read_json(registry_path)
    del registry["sources"][0]["allowed_domains"]
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("allowed_domains" in issue for issue in issues)


def test_validate_reports_malformed_source_domain_item_without_crashing(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    registry_path = tmp_path / "sources" / "registry.json"
    registry = read_json(registry_path)
    for source in registry["sources"]:
        if source["key"] == "openai.status":
            source["allowed_domains"] = [123]
            break
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("allowed_domains" in issue for issue in issues)


def test_validate_reports_missing_feed_freshness(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    (tmp_path / "data" / "feeds" / "freshness.json").unlink()

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("missing feed freshness metadata" in issue for issue in issues)


def test_validate_reports_stale_feed_freshness(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    freshness_path = tmp_path / "data" / "feeds" / "freshness.json"
    freshness = read_json(freshness_path)
    freshness["event_count"] = 0
    freshness_path.write_text(json.dumps(freshness), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("feed freshness metadata is stale" in issue for issue in issues)


def test_validate_reports_missing_source_coverage(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    (tmp_path / "data" / "feeds" / "coverage.json").unlink()

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("missing source coverage metadata" in issue for issue in issues)


def test_validate_reports_stale_source_coverage(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    coverage_path = tmp_path / "data" / "feeds" / "coverage.json"
    coverage = read_json(coverage_path)
    coverage["summary"]["source_count"] = 0
    coverage_path.write_text(json.dumps(coverage), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("source coverage metadata is stale" in issue for issue in issues)


def test_validate_reports_missing_operations_report(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    (tmp_path / "data" / "feeds" / "operations.json").unlink()

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("missing operations report metadata" in issue for issue in issues)


def test_validate_reports_stale_operations_report(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    operations_path = tmp_path / "data" / "feeds" / "operations.json"
    operations = read_json(operations_path)
    operations["summary"]["source_count"] = 0
    operations_path.write_text(json.dumps(operations), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("operations report metadata is stale" in issue for issue in issues)


def test_validate_reports_missing_json_feed(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    (tmp_path / "data" / "feeds" / "feed.json").unlink()

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("missing JSON Feed metadata" in issue for issue in issues)


def test_validate_reports_stale_json_feed(tmp_path) -> None:
    for dirname in ["data", "registries", "schemas", "sources"]:
        shutil.copytree(ROOT / dirname, tmp_path / dirname)

    feed_path = tmp_path / "data" / "feeds" / "feed.json"
    feed = read_json(feed_path)
    feed["items"] = []
    feed_path.write_text(json.dumps(feed), encoding="utf-8")

    issues = [issue.render() for issue in validate(tmp_path)]

    assert any("JSON Feed metadata is stale" in issue for issue in issues)
