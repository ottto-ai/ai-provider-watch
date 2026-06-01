# Codex Plugin Contract

Phase 0 reserves the APW Codex plugin contract. The installable plugin package is
deferred until the event schema, read-only MCP surface, and repo skills are
stable.

Future package shape:

```text
plugins/ai-provider-watch-codex/
  .codex-plugin/plugin.json
  skills/
    apw-source-author/SKILL.md
    apw-event-review/SKILL.md
    apw-repo-impact-check/SKILL.md
    apw-release-manager/SKILL.md
  .mcp.json
  assets/
    icon.png
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
- document supported CLI and schema versions.
