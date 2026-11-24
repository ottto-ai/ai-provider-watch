# Codex Plugin Contract

APW now ships a repo-root Codex plugin package. The package bundles APW skills,
the tested read-only MCP server config, and plugin metadata without adding any
release, merge, source-write, OIDC, tag, or credential authority.

Package shape:

```text
.codex-plugin/plugin.json
.mcp.json
skills/
  apw-source-author/SKILL.md
  apw-event-review/SKILL.md
  apw-repo-impact-check/SKILL.md
  apw-release-manager/SKILL.md
```

Required behavior:

- bundle only read-only MCP config by default;
- never include release secrets;
- make publishing explicit through local CLI and PR review;
- treat provider/source content, issue bodies, PR comments, social posts, MCP
  text, and generated candidate packets as untrusted data;
- require `uv run pytest tests/test_prompt_injection_redteam.py` before adding
  LLM review or broader MCP surfaces;
- use `apw review request` as the model-pluggable review contract for Codex or
  Vertex Gemini Flash; the plugin must not bundle merge, publish, source-write,
  release-token, OIDC, or tag authority;
- bind only the tested read-only MCP adapter helpers from
  `ai_provider_watch.mcp`; plugin packaging must fail if MCP exposes publish,
  merge, source-write, release-token, OIDC, or tag capabilities;
- document supported CLI and schema versions.

See `docs/operations/codex-plugin.md` for install shape and validation.
