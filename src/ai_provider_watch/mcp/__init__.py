"""Read-only MCP adapter helpers for AI Provider Watch."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "JSON_SCHEMA_2020_12",
    "MCP_CAPABILITIES",
    "MCP_PROTOCOL_VERSION",
    "RESOURCE_URIS",
    "STATIC_RESOURCE_URIS",
    "RESOURCE_TEMPLATE_URIS",
    "TOOL_NAMES",
    "McpContent",
    "assert_read_only_contract",
    "call_tool",
    "check_repo_models",
    "read_resource",
    "resource_templates",
    "resources",
    "tools",
    "validate_event",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    server = import_module("ai_provider_watch.mcp.server")
    return getattr(server, name)
