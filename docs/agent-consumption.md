# Agent Consumption

APW is built for humans and agents.

## CLI

```bash
uvx ai-provider-watch latest --risk high
uvx ai-provider-watch diff --since 7d --provider openai
uvx ai-provider-watch explain 2026-05-31-openai-example
```

During pre-release work, run from checkout:

```bash
uv run apw latest
uv run apw candidate generate --observations .apw/source-observations.json --output .apw/candidates --created-at 2026-05-31T20:15:00Z
```

Candidate output is review-only. Agents may summarize candidates and check
schemas, but they must not promote or publish events without maintainer review.

## MCP

The initial package includes a read-only MCP shell. Planned resources:

- `apw://events/latest`
- `apw://events/{event_id}`
- `apw://providers/{provider}/events`
- `apw://indexes/kind/{kind}`
- `apw://sources/registry`

Planned tools:

- `apw_latest`
- `apw_diff`
- `apw_explain`
- `apw_check_repo_models`
- `apw_validate_event`

No MCP tool should publish events or mutate sources by default.

## Codex And Claude Skills

Repo-scoped skills live under `.agents/skills/` and `.claude/skills/`.
Installable Codex plugin packaging is deferred until schema, skills, and
read-only MCP contract are stable.
