from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.io import event_paths, read_json


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


SCHEMA_FILES = {
    "event": "event.schema.json",
    "event_detail": "event-detail.schema.json",
    "impact": "impact.schema.json",
    "source": "source.schema.json",
    "observation": "observation.schema.json",
    "candidate": "candidate.schema.json",
    "release_manifest": "release-manifest.schema.json",
}

DETAIL_BY_EVENT_KIND = {
    "pricing_change": {"price_change", "generic_change"},
    "quota_change": {"quota_change", "generic_change"},
    "rate_limit_change": {"rate_limit_change", "generic_change"},
    "model_launch": {"model_lifecycle", "generic_change"},
    "model_deprecation": {"model_lifecycle", "generic_change"},
    "model_retirement": {"model_lifecycle", "generic_change"},
    "default_model_change": {"default_model_change", "generic_change"},
    "token_accounting_change": {"token_accounting_change", "generic_change"},
    "caching_change": {"price_change", "token_accounting_change", "generic_change"},
    "billing_channel_change": {"generic_change"},
    "api_contract_change": {"api_contract_change", "generic_change"},
    "sdk_behavior_change": {"api_contract_change", "generic_change"},
    "status_incident": {"status_incident", "generic_change"},
    "status_recovery": {"status_incident", "generic_change"},
    "subscription_change": {"subscription_change", "generic_change"},
    "terms_policy_change": {"generic_change"},
    "regional_availability_change": {"generic_change"},
    "workflow_behavior_change": {"default_model_change", "api_contract_change", "generic_change"},
    "catalog_correction": {"model_lifecycle", "generic_change"},
}


def load_schemas(root: Path) -> dict[str, dict[str, Any]]:
    return {name: read_json(root / "schemas" / filename) for name, filename in SCHEMA_FILES.items()}


def _issues(path: Path, data: Any, schema: dict[str, Any], label: str) -> list[ValidationIssue]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    found: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path)
        suffix = f" at {location}" if location else ""
        found.append(ValidationIssue(str(path), f"{label}{suffix}: {error.message}"))
    return found


def _ids(items: list[dict[str, Any]], key: str) -> set[str]:
    return {str(item[key]) for item in items if key in item}


def _duplicate_issues(path: Path, items: list[dict[str, Any]], key: str) -> list[ValidationIssue]:
    seen: set[str] = set()
    found: list[ValidationIssue] = []
    for item in items:
        value = str(item.get(key))
        if value in seen:
            found.append(ValidationIssue(str(path), f"duplicate {key}: {value}"))
        seen.add(value)
    return found


def _validate_registries(root: Path) -> tuple[list[ValidationIssue], dict[str, set[str]]]:
    issues: list[ValidationIssue] = []
    providers_path = root / "registries" / "providers.json"
    surfaces_path = root / "registries" / "provider-surfaces.json"
    apps_path = root / "registries" / "agent-apps.json"
    models_path = root / "registries" / "models.json"

    providers = read_json(providers_path).get("providers", [])
    surfaces = read_json(surfaces_path).get("surfaces", [])
    apps = read_json(apps_path).get("agent_apps", [])
    models = read_json(models_path).get("models", [])

    issues.extend(_duplicate_issues(providers_path, providers, "id"))
    issues.extend(_duplicate_issues(surfaces_path, surfaces, "id"))
    issues.extend(_duplicate_issues(apps_path, apps, "id"))

    provider_ids = _ids(providers, "id")
    for surface in surfaces:
        provider_id = surface.get("provider_id")
        if provider_id not in provider_ids:
            issues.append(ValidationIssue(str(surfaces_path), f"surface {surface.get('id')} references unknown provider {provider_id}"))

    return issues, {
        "provider": {f"provider:{item}" for item in provider_ids},
        "surface": {f"surface:{item}" for item in _ids(surfaces, "id")},
        "app": {f"app:{item}" for item in _ids(apps, "id")},
        "model": {f"model:{item}" for item in _ids(models, "id")},
    }


def _validate_sources(root: Path, source_schema: dict[str, Any], providers: set[str]) -> tuple[list[ValidationIssue], set[str]]:
    path = root / "sources" / "registry.json"
    registry = read_json(path)
    issues = _issues(path, registry, source_schema, "source registry")
    sources = registry.get("sources", [])
    issues.extend(_duplicate_issues(path, sources, "key"))
    source_keys = _ids(sources, "key")

    for source in sources:
        for provider_ref in source.get("provider_refs", []):
            if provider_ref not in providers:
                issues.append(ValidationIssue(str(path), f"source {source.get('key')} references unknown provider {provider_ref}"))

    for package_path in sorted((root / "sources").glob("*/source.json")):
        package = read_json(package_path)
        for source_key in package.get("source_keys", []):
            if source_key not in source_keys:
                issues.append(ValidationIssue(str(package_path), f"source package references unknown source key {source_key}"))
    return issues, source_keys


def _known_ref(ref: str, known_refs: dict[str, set[str]]) -> bool:
    kind = ref.split(":", 1)[0]
    if kind in {"plan", "endpoint", "sdk", "gateway", "region", "account"}:
        return True
    return ref in known_refs.get(kind, set())


def validate(root: Path) -> list[ValidationIssue]:
    schemas = load_schemas(root)
    issues: list[ValidationIssue] = []
    for name, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # pragma: no cover
            issues.append(ValidationIssue(f"schemas/{SCHEMA_FILES[name]}", str(exc)))

    registry_issues, known_refs = _validate_registries(root)
    issues.extend(registry_issues)
    source_issues, source_keys = _validate_sources(root, schemas["source"], known_refs["provider"])
    issues.extend(source_issues)

    event_ids: set[str] = set()
    for event_path in event_paths(root):
        event = read_json(event_path)
        issues.extend(_issues(event_path, event, schemas["event"], "event"))
        issues.extend(_issues(event_path, event.get("detail", {}), schemas["event_detail"], "detail"))
        for index, impact in enumerate(event.get("impacts", [])):
            issues.extend(_issues(event_path, impact, schemas["impact"], f"impact[{index}]"))

        event_id = event.get("id")
        if event_id in event_ids:
            issues.append(ValidationIssue(str(event_path), f"duplicate event id {event_id}"))
        event_ids.add(event_id)

        detail_kind = event.get("detail", {}).get("kind")
        if detail_kind and detail_kind not in DETAIL_BY_EVENT_KIND.get(event.get("event_kind"), set()):
            issues.append(ValidationIssue(str(event_path), f"detail kind {detail_kind} is not valid for event kind {event.get('event_kind')}"))
        for provider_ref in event.get("provider_refs", []):
            if not _known_ref(provider_ref, known_refs):
                issues.append(ValidationIssue(str(event_path), f"unknown provider ref {provider_ref}"))
        for evidence in event.get("evidence_refs", []):
            if evidence.get("source_key") not in source_keys:
                issues.append(ValidationIssue(str(event_path), f"unknown evidence source key {evidence.get('source_key')}"))
        for impact in event.get("impacts", []):
            scope_ref = impact.get("scope_ref")
            if isinstance(scope_ref, str) and ":" in scope_ref and not _known_ref(scope_ref, known_refs):
                issues.append(ValidationIssue(str(event_path), f"unknown impact scope {scope_ref}"))

    manifest_path = root / "data" / "releases" / "dev" / "manifest.json"
    if manifest_path.exists():
        issues.extend(_issues(manifest_path, read_json(manifest_path), schemas["release_manifest"], "release manifest"))
    return issues
