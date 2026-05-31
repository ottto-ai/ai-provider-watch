# AI Provider Watch

AI Provider Watch is an open, factual provider-change event feed for AI platform
teams, coding-agent maintainers, and FinOps dashboards.

It tracks provider changes that can affect developer cost, quotas, token
accounting, model availability, default models, deprecations, incidents, API
contracts, and migration risk. The project is founded by Ottto, but the feed,
schemas, CLI, and docs are usable without an Ottto account.

## What This Is

- A reviewed machine-readable event feed, not a static model catalog.
- A CLI and Python package for validating, indexing, diffing, and explaining
  provider-change events.
- A source registry for official provider docs, status pages, pricing pages,
  blogs, and repositories.
- Agent-readable contracts for Codex, Claude Code, MCP clients, GitHub Actions,
  and downstream repo impact checks.

## What This Is Not

- Not an Ottto customer telemetry product.
- Not a scraper of authenticated provider consoles or billing dashboards.
- Not legal, purchasing, tax, or migration advice.
- Not a replacement for LiteLLM, models.dev, Langfuse, Helicone, or OpenLIT.

## Current Status

This repository is in pre-release foundation work. The first PR establishes:

- community, governance, security, and mixed-license files;
- root/path-scoped agent instructions;
- event/source/observation/release JSON Schemas;
- provider, surface, model, and agent-app registries;
- deterministic `apw validate`, `apw index`, `apw latest`, `apw diff`, and
  `apw explain` commands;
- read-only MCP package shell;
- CI and data-release dry-run workflow shell.

## Install From Checkout

```bash
uv sync --all-extras
uv run apw validate
uv run apw index --check
uv run apw source test
uv run apw latest
```

Package publication to PyPI and npm will start after the v0 schema/feed contract
stabilizes.

## Feed Artifacts

Generated artifacts live under `data/`:

- `data/feeds/events.json`
- `data/feeds/events.ndjson`
- `data/feeds/latest.json`
- `data/feeds/rss.xml`
- `data/indexes/provider/*.json`
- `data/indexes/kind/*.json`
- `data/releases/dev/manifest.json`

The normalized factual event data and generated feed artifacts are dedicated to
the public domain under CC0-1.0. Code, schemas, docs, tests, and tooling are
Apache-2.0.

## Source Refresh

Official source packages can be checked locally:

```bash
uv run apw source test
uv run apw source fetch --source openai.status
```

The scheduled source-refresh workflow fetches enabled official sources, stores
only fingerprints, and opens a draft PR when a source fingerprint changes. It
does not publish provider events or commit raw source content.

## First Providers

The initial official-source registry covers:

- OpenAI
- Anthropic
- Google Gemini / Vertex AI
- AWS Bedrock
- Azure OpenAI

Community, social, and third-party sources can create review candidates, but
they do not publish canonical events without maintainer review.

## Core Model

APW uses a stable `ProviderEvent` envelope plus a typed `EventDetail` payload and
repeatable `ImpactAssessment` rows. This avoids one giant nullable event model
and keeps pricing, quota, model lifecycle, token accounting, status, and API
contract changes precise.

See:

- [Architecture](docs/architecture.md)
- [Event Schema](docs/schema/event.md)
- [Agent Consumption](docs/agent-consumption.md)
- [Plugin Contract](docs/plugin-contract.md)

## Contributing

Use pull requests for every code, schema, source, data, docs, and workflow
change. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

For source packages, see
[docs/contributors/source-packages.md](docs/contributors/source-packages.md).

## License

| Asset | License |
| --- | --- |
| Code, schemas, docs, tests, CLI, MCP shell | Apache-2.0 |
| Normalized factual data and generated feeds | CC0-1.0 |
| Provider names and trademarks | Owned by their respective owners |

See [DATA_LICENSE.md](DATA_LICENSE.md), [TRADEMARKS.md](TRADEMARKS.md), and
`LICENSES/`.
