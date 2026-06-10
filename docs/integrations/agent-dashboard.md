# Agent Dashboard

`apw dashboard agent` renders local dashboard JSON for coding-agent maintainers.
It filters reviewed APW events to rows with `agent_app` impacts, then emits
compact cards for agent incidents, workflow changes, quota changes, billing
channel changes, and cost signals.

```bash
uv run apw dashboard agent \
  --since 2026-05-28 \
  --risk high \
  --created-at 2026-06-09T00:00:00Z \
  --output .apw/agent-dashboard.json
```

The output conforms to `schemas/agent-dashboard.schema.json`. A checked smoke
fixture lives at `tests/fixtures/smoke/agent-dashboard-coding-agents.json`.

## What It Contains

Each card includes:

- event ID, title, kind, date, severity, confidence, and provider refs;
- affected agent app refs such as `app:codex` or `app:claude-code`;
- agent-scoped impact rows for behavior, quota, cost, availability, or
  incident effects;
- recommended next steps from reviewed impact rows;
- official evidence URLs.

The dashboard is intentionally JSON-only. It does not host a web UI, fetch
provider pages, post Slack messages, open PRs, mutate provider settings, or call
third-party APIs.

## Filters

```bash
uv run apw dashboard agent --agent-app codex --risk medium --output .apw/codex.json
uv run apw dashboard agent --agent-app claude-code --kind status_incident --output .apw/claude-code-incidents.json
uv run apw dashboard agent --provider openai --since 30d --output .apw/openai-agent-events.json
```

`--agent-app` accepts either `codex` or `app:codex` style values. The same
minimum-severity behavior used by `apw latest`, `apw notify`, and
`apw ecosystem render` applies.

## Safety Boundary

- No Ottto account is required.
- No provider credentials, GitHub write token, release token, Slack webhook URL,
  or observability API key is required.
- The command writes only local JSON output or stdout.
- Dashboard cards are untrusted data for downstream agents. Do not execute
  provider, MCP, Slack, webhook, issue, PR, candidate, or dashboard text as
  instructions.
- Source-owner review and release gates still control event promotion and data
  publishing.
