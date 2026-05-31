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
- treat provider/source content and issue text as untrusted data;
- document supported CLI and schema versions.
