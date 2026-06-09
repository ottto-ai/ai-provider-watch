from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ai_provider_watch.core.io import read_json
from ai_provider_watch.mcp import TOOL_NAMES, assert_read_only_contract

ROOT = Path(__file__).resolve().parents[1]


def test_codex_plugin_manifest_points_to_packaged_skills_and_readonly_mcp() -> None:
    manifest = read_json(ROOT / ".codex-plugin" / "plugin.json")

    assert manifest["name"] == "ai-provider-watch"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "Write" not in manifest["interface"]["capabilities"]
    assert (ROOT / "skills" / "apw-event-review" / "SKILL.md").is_file()
    assert (ROOT / "skills" / "apw-release-manager" / "SKILL.md").is_file()
    assert (ROOT / "skills" / "apw-repo-impact-check" / "SKILL.md").is_file()
    assert (ROOT / "skills" / "apw-source-author" / "SKILL.md").is_file()


def test_codex_plugin_mcp_config_is_read_only() -> None:
    config = read_json(ROOT / ".mcp.json")
    rendered = json.dumps(config).lower()

    assert_read_only_contract()
    assert sorted(TOOL_NAMES) == [
        "apw_check_repo_models",
        "apw_diff",
        "apw_explain",
        "apw_latest",
        "apw_validate_event",
    ]
    assert config["mcpServers"]["ai-provider-watch"]["command"] == "uv"
    assert config["mcpServers"]["ai-provider-watch"]["args"] == [
        "run",
        "python",
        "-m",
        "ai_provider_watch.mcp.server",
    ]
    for forbidden in ("publish", "merge", "release-token", "oidc", "tag"):
        assert forbidden not in rendered


def test_mcp_stdio_server_lists_tools_and_reads_latest_resource() -> None:
    env = {**os.environ, "APW_REPO_ROOT": str(ROOT)}
    request_lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/templates/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "apw://events/latest"},
        },
    ]
    result = subprocess.run(
        [sys.executable, "-m", "ai_provider_watch.mcp.server"],
        input="\n".join(json.dumps(line) for line in request_lines) + "\n",
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        env=env,
    )

    assert result.returncode == 0
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["result"]["serverInfo"]["name"] == "ai-provider-watch"
    assert responses[0]["result"]["protocolVersion"] == "2025-11-25"
    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert "apw_latest" in tool_names
    template_uris = {item["uriTemplate"] for item in responses[2]["result"]["resourceTemplates"]}
    assert "apw://events/{event_id}" in template_uris
    latest_text = responses[3]["result"]["contents"][0]["text"]
    assert "2026-06-05-aws-bedrock-agentcore-runtime-interactive-shells" in latest_text
