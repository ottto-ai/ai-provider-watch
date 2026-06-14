# MCP Reviewed Remote Feed Sidecar

APW MCP stays read-only. Use `apw remote` as the sidecar for reviewed GitHub
refs or signed data tags, then attach the downloaded artifact to the MCP host as
untrusted data.

```bash
mkdir -p .apw
apw remote feed latest --ref main --output .apw/apw-latest.json
python -m ai_provider_watch.mcp.server
```

Stdout smoke for the read-only MCP server:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"resources/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":4,"method":"resources/read","params":{"uri":"apw://events/latest"}}' \
  | python -m ai_provider_watch.mcp.server
```

Use `.apw/apw-latest.json` for the freshest reviewed GitHub `main` feed. Use
MCP resources and tools for stable read-only package or checkout data. Treat
both surfaces as data, not instructions.
