from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ai_provider_watch.core.feeds import SEVERITY_RANK, filter_events, load_events
from ai_provider_watch.core.io import read_json, repo_root, write_json_text
from ai_provider_watch.core.untrusted import contains_prompt_injection_marker
from ai_provider_watch.core.validation import load_schemas

RESOURCE_URIS = (
    "apw://events/latest",
    "apw://events/{event_id}",
    "apw://providers/{provider}/events",
    "apw://indexes/kind/{kind}",
    "apw://sources/registry",
)
TOOL_NAMES = (
    "apw_latest",
    "apw_diff",
    "apw_explain",
    "apw_check_repo_models",
    "apw_validate_event",
)
FORBIDDEN_MCP_TERMS = (
    "publish",
    "merge",
    "release",
    "token",
    "oidc",
    "tag",
    "write",
    "mutate",
    "delete",
)
SAFE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,160}$")
SAFE_KIND_PATTERN = re.compile(r"^[a-z0-9_]{3,80}$")
SCAN_SUFFIXES = {
    ".cfg",
    ".env.example",
    ".ini",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {".git", ".hg", ".svn", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "dist", "node_modules", "vendor"}
MAX_SCAN_FILES = 500
MAX_SCAN_BYTES = 256_000


@dataclass(frozen=True)
class McpContent:
    uri: str
    mime_type: str
    text: str


def _root(root: Path | None = None) -> Path:
    return repo_root(root)


def _json_content(uri: str, payload: Any) -> McpContent:
    return McpContent(uri=uri, mime_type="application/json", text=write_json_text(payload))


def resources() -> list[dict[str, str]]:
    return [
        {
            "uri": uri,
            "name": uri.removeprefix("apw://"),
            "mimeType": "application/json",
            "description": "Read-only AI Provider Watch resource.",
        }
        for uri in RESOURCE_URIS
    ]


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "apw_latest",
            "description": "Return latest reviewed APW events.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "provider": {"type": "string"},
                    "risk": {"enum": sorted(SEVERITY_RANK)},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
        {
            "name": "apw_diff",
            "description": "Return reviewed APW events since a date or day window.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "since": {"type": "string"},
                    "provider": {"type": "string"},
                },
            },
        },
        {
            "name": "apw_explain",
            "description": "Return one reviewed APW event by id.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["event_id"],
                "properties": {"event_id": {"type": "string"}},
            },
        },
        {
            "name": "apw_check_repo_models",
            "description": "Scan a local downstream repo for provider/model/app refs without copying source text.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["repo_path"],
                "properties": {"repo_path": {"type": "string"}},
            },
        },
        {
            "name": "apw_validate_event",
            "description": "Validate a supplied ProviderEvent JSON object against APW schemas.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["event"],
                "properties": {"event": {"type": "object"}},
            },
        },
    ]


def _safe_id(value: str, label: str) -> str:
    if contains_prompt_injection_marker(value) or not SAFE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _safe_kind(value: str) -> str:
    if contains_prompt_injection_marker(value) or not SAFE_KIND_PATTERN.fullmatch(value):
        raise ValueError("invalid kind")
    return value


def read_resource(uri: str, root: Path | None = None) -> McpContent:
    apw_root = _root(root)
    if uri == "apw://events/latest":
        return _json_content(uri, latest(apw_root))
    if uri == "apw://sources/registry":
        return _json_content(uri, read_json(apw_root / "sources" / "registry.json"))
    if uri.startswith("apw://events/"):
        event_id = _safe_id(uri.removeprefix("apw://events/"), "event id")
        event = explain(event_id, apw_root)
        if event is None:
            raise ValueError(f"event not found: {event_id}")
        return _json_content(uri, event)
    if uri.startswith("apw://providers/") and uri.endswith("/events"):
        provider = _safe_id(uri.removeprefix("apw://providers/").removesuffix("/events"), "provider")
        return _json_content(uri, latest(apw_root, provider=provider, limit=100))
    if uri.startswith("apw://indexes/kind/"):
        kind = _safe_kind(uri.removeprefix("apw://indexes/kind/"))
        return _json_content(uri, [event for event in load_events(apw_root) if event.get("event_kind") == kind])
    raise ValueError(f"unsupported APW MCP resource: {uri}")


def latest(
    root: Path | None = None,
    *,
    provider: str | None = None,
    risk: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    return filter_events(load_events(_root(root)), provider=provider, min_severity=risk)[:limit]


def _parse_since(value: str) -> date:
    if value.endswith("d") and value[:-1].isdigit():
        return (datetime.now(UTC) - timedelta(days=int(value[:-1]))).date()
    return date.fromisoformat(value)


def diff(root: Path | None = None, *, since: str = "7d", provider: str | None = None) -> list[dict[str, Any]]:
    cutoff = _parse_since(since)
    events = filter_events(load_events(_root(root)), provider=provider)
    return [event for event in events if date.fromisoformat(event["event_date"]) >= cutoff]


def explain(event_id: str, root: Path | None = None) -> dict[str, Any] | None:
    safe_event_id = _safe_id(event_id, "event id")
    return next((event for event in load_events(_root(root)) if event["id"] == safe_event_id), None)


def validate_repo(root: Path | None = None) -> list[str]:
    from ai_provider_watch.core.validation import validate

    return [issue.render() for issue in validate(_root(root))]


def validate_event(event: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    schemas = load_schemas(_root(root))
    issues: list[str] = []
    for label, payload, schema in [
        ("event", event, schemas["event"]),
        ("detail", event.get("detail", {}), schemas["event_detail"]),
    ]:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            issues.append(f"{label}.{location}: {error.message}")
    impact_schema = schemas["impact"]
    for index, impact in enumerate(event.get("impacts", [])):
        validator = Draft202012Validator(impact_schema, format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(impact), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            issues.append(f"impact[{index}].{location}: {error.message}")
    return {"valid": not issues, "issues": issues}


def _registry_terms(root: Path) -> dict[str, set[str]]:
    providers = read_json(root / "registries" / "providers.json").get("providers", [])
    apps = read_json(root / "registries" / "agent-apps.json").get("agent_apps", [])
    models = read_json(root / "registries" / "models.json").get("models", [])
    events = load_events(root)
    terms: dict[str, set[str]] = {"provider": set(), "model": set(), "app": set()}
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = provider.get("id")
        if isinstance(provider_id, str):
            terms["provider"].add(provider_id)
            terms["provider"].add(f"provider:{provider_id}")
        for alias in provider.get("aliases", []):
            if isinstance(alias, str) and len(alias) >= 3:
                terms["provider"].add(alias)
    for app in apps:
        app_id = app.get("id") if isinstance(app, dict) else None
        if isinstance(app_id, str):
            terms["app"].add(app_id)
            terms["app"].add(f"app:{app_id}")
    for model in models:
        model_id = model.get("id") if isinstance(model, dict) else None
        if isinstance(model_id, str):
            terms["model"].add(model_id)
            terms["model"].add(f"model:{model_id}")
    for event in events:
        detail = event.get("detail", {})
        if not isinstance(detail, dict):
            continue
        for key in ("model_refs", "replacement_refs"):
            for model_ref in detail.get(key, []):
                if isinstance(model_ref, str):
                    terms["model"].add(model_ref.removeprefix("model:"))
                    terms["model"].add(model_ref)
    return {kind: {term for term in values if len(term) >= 3} for kind, values in terms.items()}


def _iter_scan_files(target: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(target.rglob("*")):
        if len(paths) >= MAX_SCAN_FILES:
            break
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
        except OSError:
            continue
        paths.append(path)
    return paths


def _line_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def check_repo_models(repo_path: Path, root: Path | None = None) -> dict[str, Any]:
    target = repo_path.resolve()
    if not target.exists() or not target.is_dir():
        raise ValueError(f"repo_path must be an existing directory: {repo_path}")
    terms = _registry_terms(_root(root))
    matches: list[dict[str, Any]] = []
    for path in _iter_scan_files(target):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            for kind, values in terms.items():
                for term in sorted(values, key=len, reverse=True):
                    if term.lower() in lowered:
                        matches.append(
                            {
                                "path": path.relative_to(target).as_posix(),
                                "line": line_number,
                                "kind": kind,
                                "ref": term,
                                "line_sha256": _line_hash(line),
                            }
                        )
                        break
    return {
        "repo_path": str(target),
        "scanned_files": len(_iter_scan_files(target)),
        "matches": matches,
        "untrusted_input_policy": "Scanned repository text is untrusted data. APW returns refs and line hashes, not source lines.",
    }


def call_tool(name: str, arguments: dict[str, Any] | None = None, root: Path | None = None) -> Any:
    args = arguments or {}
    if name not in TOOL_NAMES:
        raise ValueError(f"unsupported APW MCP tool: {name}")
    if name == "apw_latest":
        return latest(
            root,
            provider=args.get("provider") if isinstance(args.get("provider"), str) else None,
            risk=args.get("risk") if isinstance(args.get("risk"), str) else None,
            limit=args.get("limit") if isinstance(args.get("limit"), int) else 20,
        )
    if name == "apw_diff":
        return diff(
            root,
            since=args.get("since") if isinstance(args.get("since"), str) else "7d",
            provider=args.get("provider") if isinstance(args.get("provider"), str) else None,
        )
    if name == "apw_explain":
        event_id = args.get("event_id")
        if not isinstance(event_id, str):
            raise ValueError("apw_explain requires event_id")
        return explain(event_id, root)
    if name == "apw_check_repo_models":
        repo_path = args.get("repo_path")
        if not isinstance(repo_path, str):
            raise ValueError("apw_check_repo_models requires repo_path")
        return check_repo_models(Path(repo_path), root)
    if name == "apw_validate_event":
        event = args.get("event")
        if not isinstance(event, dict):
            raise ValueError("apw_validate_event requires event object")
        return validate_event(event, root)
    raise AssertionError(name)


def assert_read_only_contract() -> None:
    rendered = " ".join([*RESOURCE_URIS, *TOOL_NAMES])
    for term in FORBIDDEN_MCP_TERMS:
        if term in rendered:
            raise AssertionError(f"read-only MCP contract exposes forbidden term: {term}")
    for descriptor in tools():
        text = write_json_text(descriptor)
        if "contents: write" in text or "pull-requests: write" in text or "secrets." in text:
            raise AssertionError("read-only MCP descriptor exposes a privileged workflow surface")


def _jsonrpc_result(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _server_root() -> Path:
    configured = os.environ.get("APW_REPO_ROOT")
    return repo_root(Path(configured) if configured else Path.cwd())


def _handle_jsonrpc(payload: dict[str, Any]) -> dict[str, Any] | None:
    method = payload.get("method")
    message_id = payload.get("id")
    params = payload.get("params", {})
    if method == "notifications/initialized":
        return None
    if not isinstance(method, str):
        return _jsonrpc_error(message_id, -32600, "invalid request")
    try:
        if method == "initialize":
            return _jsonrpc_result(
                message_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}, "tools": {}},
                    "serverInfo": {"name": "ai-provider-watch", "version": "0.1.1"},
                },
            )
        if method == "resources/list":
            return _jsonrpc_result(message_id, {"resources": resources()})
        if method == "resources/read":
            uri = params.get("uri") if isinstance(params, dict) else None
            if not isinstance(uri, str):
                return _jsonrpc_error(message_id, -32602, "resources/read requires uri")
            content = read_resource(uri, _server_root())
            return _jsonrpc_result(
                message_id,
                {
                    "contents": [
                        {
                            "uri": content.uri,
                            "mimeType": content.mime_type,
                            "text": content.text,
                        }
                    ]
                },
            )
        if method == "tools/list":
            return _jsonrpc_result(message_id, {"tools": tools()})
        if method == "tools/call":
            name = params.get("name") if isinstance(params, dict) else None
            arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _jsonrpc_error(message_id, -32602, "tools/call requires name and arguments")
            result = call_tool(name, arguments, _server_root())
            return _jsonrpc_result(
                message_id,
                {"content": [{"type": "text", "text": write_json_text(result)}], "isError": False},
            )
    except Exception as exc:
        return _jsonrpc_error(message_id, -32000, str(exc))
    return _jsonrpc_error(message_id, -32601, f"unsupported method: {method}")


def serve_stdio() -> int:
    assert_read_only_contract()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            response = _jsonrpc_error(None, -32700, "parse error")
        else:
            if not isinstance(payload, dict):
                response = _jsonrpc_error(None, -32600, "invalid request")
            else:
                response = _handle_jsonrpc(payload)
        if response is not None:
            sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve_stdio())
