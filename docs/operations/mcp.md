# Read-Only MCP Contract

APW exposes a read-only MCP adapter layer in `ai_provider_watch.mcp`. It is
dependency-light by design: the package defines resources, tool descriptors, and
callable helpers that MCP hosts can bind to without gaining write or release
authority.

Resources:

- `apw://events/latest`
- `apw://events/{event_id}`
- `apw://providers/{provider}/events`
- `apw://indexes/kind/{kind}`
- `apw://sources/registry`

Tools:

- `apw_latest`
- `apw_diff`
- `apw_explain`
- `apw_check_repo_models`
- `apw_validate_event`

The adapter has no tools for merging PRs, publishing events, mutating source
state, writing `data/events`, creating release tags, reading release tokens, or
requesting OIDC credentials.

## Local Smoke

```python
from pathlib import Path
from ai_provider_watch.mcp import call_tool, read_resource

root = Path("/path/to/ai-provider-watch")
latest = read_resource("apw://events/latest", root)
event = call_tool("apw_explain", {"event_id": "2024-01-04-openai-gpt3-completions-retirement"}, root)
```

`apw_check_repo_models` scans local downstream repositories for provider, model,
and agent-app refs. Repository text is untrusted data; the tool returns refs and
line hashes, not source lines.

## Validation

```bash
uv run pytest tests/test_mcp_readonly.py tests/test_prompt_injection_redteam.py
uv run apw validate
```
