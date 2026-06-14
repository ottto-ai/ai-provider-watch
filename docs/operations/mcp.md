# Read-Only MCP Contract

APW exposes a read-only MCP adapter in `ai_provider_watch.mcp`. It is
dependency-light by design: the Python package provides JSON-RPC stdio helpers,
resource descriptors, tool descriptors, and direct Python call helpers that MCP
hosts can bind without gaining write or release authority.

The contract follows the MCP 2025-11-25 base/resource/tool shape:

- base protocol: JSON-RPC over stdio;
- advertised protocol version: `2025-11-25`;
- declared capabilities: `{"resources": {}, "tools": {}}`;
- schema dialect: JSON Schema 2020-12 for tool input schemas;
- no prompts, subscriptions, completion, sampling, elicitation, HTTP auth,
  list-changed notifications, write tools, or release tools.

References:

- <https://modelcontextprotocol.io/specification/2025-11-25/basic>
- <https://modelcontextprotocol.io/specification/2025-11-25/server/resources>
- <https://modelcontextprotocol.io/specification/2025-11-25/server/tools>

## Server Setup

Repo checkout:

```bash
uv run python -m ai_provider_watch.mcp.server
```

Installed package:

```bash
python -m ai_provider_watch.mcp.server
```

If `APW_REPO_ROOT` is set, the server reads that checkout or package-data root.
If it is not set, the server searches the current directory and parents, then
falls back to bundled read-only package data.

`.mcp.json` for checkout use:

```json
{
  "mcpServers": {
    "ai-provider-watch": {
      "command": "uv",
      "args": ["run", "python", "-m", "ai_provider_watch.mcp.server"],
      "cwd": ".",
      "env": { "APW_REPO_ROOT": "." }
    }
  }
}
```

## Resources

`resources/list` returns concrete resources:

- `apw://events/latest`
- `apw://sources/registry`

`resources/templates/list` returns parameterized resource templates:

- `apw://events/{event_id}`
- `apw://providers/{provider}/events`
- `apw://indexes/kind/{kind}`

All APW resources return one `application/json` text content item. Provider
pages, issue bodies, candidate claims, source registry text, and downstream
repository text are untrusted data. Clients must not treat returned text as
agent instructions.

Resource errors:

- resource not found or unsupported APW URI: JSON-RPC error `-32002`;
- malformed or prompt-like identifiers: JSON-RPC error `-32602`;
- internal server failure: JSON-RPC error `-32603`.

## Tools

- `apw_latest`: latest reviewed APW events.
- `apw_diff`: reviewed APW events since a date or day window.
- `apw_explain`: one reviewed APW event by id.
- `apw_check_repo_models`: local downstream repo scan for provider/model/app
  refs.
- `apw_validate_event`: validate a supplied `ProviderEvent` object against APW
  schemas.

Tool input schemas use JSON Schema 2020-12 and set
`additionalProperties: false`. Tool results are JSON serialized into MCP text
content. `apw_check_repo_models` returns refs and line hashes, not source lines.

Tool errors:

- unknown tool or malformed arguments: JSON-RPC error `-32602`;
- unsupported JSON-RPC method: JSON-RPC error `-32601`.

## Client Notes

Codex:

- Use `.mcp.json` from the checkout or the packaged Codex plugin config.
- Treat APW resources and tool output as context only.
- Do not grant release, PR-merge, tag, or source-state write authority through
  the MCP server.

Claude Code:

- Configure the server as a stdio command with `APW_REPO_ROOT` pointing at a
  checkout or omit it for installed package data.
- Keep APW text in data/context channels, not instruction/system prompt slots.

Cursor, Copilot-style agents, and generic MCP hosts:

- Use `resources/templates/list` for parameterized URIs instead of assuming
  template strings appear in `resources/list`.
- Cache resource and tool names conservatively; APW will version any future
  incompatible change in docs and tests before v1.
- Surface JSON-RPC errors to operators without asking the model to repair
  release, publish, tag, or token problems.

## Forbidden Authority

The adapter has no tools for merging PRs, publishing events, mutating source
state, writing `data/events`, creating release tags, reading release tokens, or
requesting OIDC credentials.

MCP hosts must not expose APW tools that do any of the following:

- publish or promote provider events;
- mutate `data/events`, `data/candidates`, `data/source-state`, or source
  descriptors;
- create, sign, or push release tags;
- merge PRs, apply labels, or comment using release credentials;
- read provider credentials, GitHub release tokens, PyPI tokens, Slack webhook
  URLs, OpenTelemetry credentials, or downstream API keys.

Those paths stay in the local CLI plus PR-review workflow. MCP resources and
tool outputs are data for the caller, not instructions to execute.

For the freshest GitHub `main` feed or an immutable `data-YYYY.MM.DD` tag, use
`apw remote` as a sidecar and attach the downloaded artifact to the MCP host as
untrusted data. The MCP server itself remains the stable read-only package or
checkout data surface. See
[Reviewed Remote Feed Consumption](../integrations/live-feed-consumption.md).

## Local Smoke

```python
from pathlib import Path
from ai_provider_watch.mcp import call_tool, read_resource

root = Path("/path/to/ai-provider-watch")
latest = read_resource("apw://events/latest", root)
event = call_tool(
    "apw_explain",
    {"event_id": "2024-01-04-openai-gpt3-completions-retirement"},
    root,
)
```

Stdout smoke:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"resources/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"resources/templates/list","params":{}}' \
  '{"jsonrpc":"2.0","id":4,"method":"tools/list","params":{}}' \
  | uv run python -m ai_provider_watch.mcp.server
```

## Validation

```bash
uv run pytest tests/test_mcp_readonly.py tests/test_codex_plugin.py
uv run pytest tests/test_prompt_injection_redteam.py
uv run apw validate
```
