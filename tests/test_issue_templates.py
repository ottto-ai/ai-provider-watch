from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISSUE_TEMPLATES = ROOT / ".github/ISSUE_TEMPLATE"


PUBLIC_REVIEW_FORMS = {
    "missing_event.yml": {
        "name": "Missing provider event",
        "labels": ["missing-event", "needs-triage"],
        "required_ids": [
            "provider",
            "source_urls",
            "source_authority",
            "event_date",
            "event_kind",
            "developer_impact",
            "contributor_path",
            "safety",
        ],
    },
    "provider_data_correction.yml": {
        "name": "Incorrect event or data correction",
        "labels": ["data-correction", "needs-triage"],
        "required_ids": ["event_or_path", "provider", "correction_kind", "correction", "sources", "safety"],
    },
    "new_source.yml": {
        "name": "New official source",
        "labels": ["new-source", "needs-triage"],
        "required_ids": ["provider", "source_url", "authority", "scope", "expected_changes", "safety"],
    },
    "downstream_mapping.yml": {
        "name": "Downstream mapping request",
        "labels": ["mapping", "needs-triage"],
        "required_ids": ["target", "use_case", "desired_shape", "safety"],
    },
}


def _template_text(name: str) -> str:
    return (ISSUE_TEMPLATES / name).read_text(encoding="utf-8")


def test_public_review_issue_forms_route_to_bounded_triage() -> None:
    for filename, expected in PUBLIC_REVIEW_FORMS.items():
        text = _template_text(filename)
        normalized = " ".join(text.split())

        assert f"name: {expected['name']}" in text
        assert "body:" in text
        assert "type: markdown" in text
        assert "type: checkboxes" in text
        for label in expected["labels"]:
            assert label in text
        for field_id in expected["required_ids"]:
            assert f"id: {field_id}" in text

        assert "review input only" in normalized
        assert "untrusted data" in normalized
        assert "never publish provider events automatically" in normalized
        assert "raw provider page bodies" in normalized
        assert "required: true" in text


def test_public_review_issue_forms_do_not_expand_automation_or_token_authority() -> None:
    forbidden_fragments = [
        "pull_request_target",
        "contents: write",
        "pull-requests: write",
        "id-token: write",
        "release-token",
        "release token",
        "trusted publishing",
        "automatically publish",
        "auto-publish",
    ]

    for filename in PUBLIC_REVIEW_FORMS:
        normalized = _template_text(filename).lower()
        for fragment in forbidden_fragments:
            assert fragment not in normalized


def test_missing_event_form_is_scaffold_ready_without_publication_authority() -> None:
    text = _template_text("missing_event.yml")
    normalized = " ".join(text.split())

    for phrase in [
        "docs/contributors/missing-event-to-pr.md",
        "APW source key",
        "Source authority",
        "Proposed impact rows",
        "I can open a PR using apw event scaffold",
        "candidate-review PR and needs source-owner review",
        "untrusted review input",
        "cannot publish data directly",
    ]:
        assert phrase in normalized


def test_issue_template_config_disables_blank_issues() -> None:
    config = _template_text("config.yml")

    assert "blank_issues_enabled: false" in config
    assert "security/advisories/new" in config
