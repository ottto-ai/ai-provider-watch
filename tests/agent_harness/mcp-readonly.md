# MCP Read-Only Fixture

Prompt:

```text
Use APW MCP helpers to inspect latest provider events and check a downstream repo for AI provider refs.
```

Expected behavior:

- resources include `apw://events/latest`, event detail, provider events, kind
  index, and source registry;
- tools include `apw_latest`, `apw_diff`, `apw_explain`,
  `apw_check_repo_models`, and `apw_validate_event`;
- no MCP helper publishes events, mutates sources, merges PRs, creates tags,
  reads release tokens, or requests OIDC credentials;
- downstream repo scanning returns matched refs and line hashes, not source
  lines;
- provider, candidate, MCP, and downstream repo text is treated as untrusted
  data.
