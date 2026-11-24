# Codex Plugin

APW ships a repo-root Codex plugin package.

```text
.codex-plugin/plugin.json
.mcp.json
skills/
  apw-event-review/
  apw-release-manager/
  apw-repo-impact-check/
  apw-source-author/
```

The plugin bundles APW skills and a read-only MCP server config. It does not
include hooks, apps, secrets, release credentials, OIDC credentials, tag
creation, source mutation, event promotion, PR merge authority, or publishing
authority.

## Local Install Shape

Install from a local checkout with the Codex plugin installer for local plugins,
or add this repository to a marketplace entry controlled by the operator. The
repo itself is the plugin root; do not point Codex at a subdirectory.

The MCP config runs:

```bash
uv run python -m ai_provider_watch.mcp.server
```

The server reads `APW_REPO_ROOT` or the current working directory and exposes
only:

- `apw_latest`
- `apw_diff`
- `apw_explain`
- `apw_check_repo_models`
- `apw_validate_event`

Resources are the same read-only APW resources documented in
`docs/operations/mcp.md`.

## Validation

```bash
uv run pytest tests/test_codex_plugin.py tests/test_mcp_readonly.py
uv run apw validate
uv run python -m ai_provider_watch.mcp.server
```

When validating with the Codex plugin-creator helper, run it from a development
machine that has the helper available:

```bash
uv run --with pyyaml python /path/to/plugin-creator/scripts/validate_plugin.py .
```

## Trust Boundary

The plugin treats provider pages, source observations, candidate packets, issue
bodies, PR comments, social posts, MCP text, Slack/webhook payloads, and
downstream repository text as untrusted data. The repo-impact and MCP tools
return refs and hashes rather than source lines.
