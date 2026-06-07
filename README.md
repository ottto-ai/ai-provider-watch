# AI Provider Watch

[![PyPI](https://img.shields.io/pypi/v/ai-provider-watch.svg)](https://pypi.org/project/ai-provider-watch/)
[![License: Apache-2.0](https://img.shields.io/badge/code-Apache--2.0-blue.svg)](LICENSES/Apache-2.0.txt)
[![Data: CC0-1.0](https://img.shields.io/badge/data-CC0--1.0-green.svg)](DATA_LICENSE.md)

AI Provider Watch, or APW, is a public event feed and CLI for changes from AI
providers that can affect developer cost, quotas, token accounting, model
availability, defaults, deprecations, incidents, and migration risk.

Use it when you need an auditable answer to questions like:

- Did a provider incident explain a spike in failures, retries, latency, or
  support tickets?
- Did a model launch, retirement, default change, pricing update, or quota shift
  create work for platform teams?
- Which repos, agents, gateways, or dashboards should be checked before a
  provider change turns into a customer-facing problem?

APW is founded by Ottto and built as a standalone open-source project. The feed,
schemas, CLI, GitHub Action, MCP helpers, and docs work without an Ottto account.

## Install

Try the CLI without installing:

```bash
uvx --from ai-provider-watch apw latest --limit 3
uvx --from ai-provider-watch apw diff --since 30d
```

Install it as a command:

```bash
pipx install ai-provider-watch
apw latest --limit 3
```

Or install it in a Python environment:

```bash
python -m pip install ai-provider-watch
apw validate
```

The published package includes the reviewed public data feed, so read-only
commands work outside a checkout.

## Quickstart

Show the latest reviewed events:

```bash
apw latest --limit 3
```

List events from the last 30 days:

```bash
apw diff --since 30d
```

Explain one event for a human reviewer:

```bash
apw explain 2026-06-04-openai-codex-compaction-latency
```

Validate the bundled schemas, registries, events, feeds, and indexes:

```bash
apw validate
apw index --check
apw freshness --summary
```

## Feed Artifacts

The canonical reviewed events live in `data/events/`. Generated feed artifacts
live in `data/feeds/` and `data/indexes/`:

- `data/feeds/events.json`
- `data/feeds/events.ndjson`
- `data/feeds/freshness.json`
- `data/feeds/latest.json`
- `data/feeds/rss.xml`
- `data/indexes/provider/*.json`
- `data/indexes/kind/*.json`
- `data/indexes/severity/*.json`

For direct consumption, pin a release tag or read from the repository:

```text
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/latest.json
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/events.ndjson
https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main/data/feeds/freshness.json
```

Use `apw freshness` to verify the feed version, package version, event count,
latest reviewed event date, latest source-state retrieval timestamp, release
manifest path, and checksum manifest path from either a checkout or the bundled
package data.

The normalized factual event data and generated feeds are CC0-1.0. Code,
schemas, docs, tests, and tooling are Apache-2.0.

## What You Get

- A reviewed machine-readable event feed, not a static model catalog.
- A typed `ProviderEvent` envelope with precise event details and repeatable
  impact rows.
- A CLI for validation, indexing, latest events, diffs, explanations, release
  dry runs, source checks, candidate generation, repo impact checks,
  notifications, and ecosystem mappings.
- JSON Schemas for events, sources, candidates, observations, releases,
  feed freshness, webhooks, Slack-style payloads, ecosystem mappings, and LLM
  review packets.
- Official-source descriptors for OpenAI, Anthropic, Google Gemini / Vertex AI,
  AWS Bedrock, and Azure OpenAI.
- Review-only source candidates that help maintainers notice provider changes
  without publishing unreviewed facts.
- Agent-native surfaces: `AGENTS.md`, `CLAUDE.md`, `llms.txt`, Codex and Claude
  skills, a read-only MCP adapter shell, and a Codex plugin package.
- Downstream integrations for GitHub Actions, webhooks, Slack-compatible JSON,
  LiteLLM, models.dev, Langfuse, Helicone, and OpenLIT.

## Trust Model

APW is designed for factual, reviewable provider-change data.

- Prefer official provider-controlled sources.
- Treat provider pages, issue bodies, PR comments, social posts, MCP text, and
  generated candidates as untrusted data, never as instructions.
- Do not commit raw provider HTML, authenticated-console content, screenshots,
  private billing data, cookies, credentials, or customer telemetry.
- Publish only reviewed `data/events/*.json` records.
- Keep generated candidate files in `data/candidates/` review-only until a
  source owner promotes a factual change.
- Keep release tokens away from jobs that fetch source pages, process candidate
  text, run LLM review, or inspect PR comments.

APW is intentionally independent of Ottto private product surfaces. Ottto may
consume APW data, but this repository does not expose Ottto customer telemetry,
Advisor internals, private UI, infrastructure, Slack data, or credential
loading code.

## Work From A Checkout

Use a checkout for write workflows such as source refresh, candidate generation,
event promotion, feed regeneration, and release dry runs:

```bash
git clone https://github.com/ottto-ai/ai-provider-watch.git
cd ai-provider-watch
uv sync --all-extras
uv lock --check
uv run pytest
uv run apw validate
uv run apw index --check
uv run apw source test
```

Fetch official sources and generate review candidates:

```bash
uv run apw source fetch --observations .apw/source-observations.json
uv run apw candidate generate \
  --observations .apw/source-observations.json \
  --output .apw/candidates \
  --created-at 2026-06-05T00:00:00Z
uv run apw candidate review-pr-body \
  --observations .apw/source-observations.json \
  --candidates .apw/candidates
```

Candidate files are not published events. Promotion to `data/events/` remains a
manual source-owner review step. See
[Event Promotion](docs/operations/event-promotion.md).

## Use APW In Downstream Systems

Check a repository for model references and APW-relevant impact:

```bash
apw repo check --repo . --since 3650d --risk low
```

Render notification payloads:

```bash
apw notify webhook --since 7d --risk medium --output .apw/apw-webhook.json
apw notify slack --since 7d --risk medium --output .apw/apw-slack.json
```

Render ecosystem mappings:

```bash
apw ecosystem render --target litellm --since 30d --risk medium --output .apw/litellm.json
apw ecosystem render --target langfuse --since 30d --risk medium --output .apw/langfuse.json
```

See:

- [Agent Consumption](docs/agent-consumption.md)
- [Downstream GitHub Action](docs/integrations/github-action.md)
- [Webhook And Slack Payloads](docs/integrations/webhooks.md)
- [Ecosystem Mappings](docs/integrations/ecosystem-mappings.md)
- [Read-Only MCP Contract](docs/operations/mcp.md)
- [Codex Plugin](docs/operations/codex-plugin.md)

## Schema And Architecture

APW uses a stable `ProviderEvent` envelope, a typed `EventDetail` payload, and
repeatable `ImpactAssessment` rows. That keeps pricing, quota, lifecycle,
token-accounting, status, API-contract, and migration-risk events precise
without creating one giant nullable event model.

Start here:

- [Architecture](docs/architecture.md)
- [Event Schema](docs/schema/event.md)
- [Feed Freshness Schema](docs/schema/feed-freshness.md)
- [Contributor Review Workflow](docs/contributors/review-workflow.md)
- [Source Packages](docs/contributors/source-packages.md)
- [Source Refresh](docs/operations/source-refresh.md)
- [Release Gates](docs/operations/release-gates.md)
- [v0.2 Release Checklist](docs/operations/v0.2-release-checklist.md)
- [Python Package Release](docs/operations/python-package-release.md)

## Project Status

APW `v0.1.0` is the first stable public package. The first public data releases
are signed CalVer tags such as `data-2026.06.05`.

The current release includes:

- reviewed seed events for OpenAI, Anthropic, Google Vertex AI, AWS Bedrock, and
  Azure OpenAI;
- generated JSON, NDJSON, RSS, provider, kind, and severity indexes;
- source-refresh automation that opens draft candidate-review PRs without
  publishing events;
- no-op guarded data-publisher workflow scaffolding;
- PyPI Trusted Publishing;
- CI, CodeQL, Dependency Review, Scorecard, and data-release dry-run workflows.

Daily unattended public data tags are not enabled yet. Until that safety gate is
stronger, real data publication uses reviewed PRs plus maintainer-signed Git
tags.

## Contributing

Use pull requests for code, schema, source, data, docs, and workflow changes.
Start with [CONTRIBUTING.md](CONTRIBUTING.md).

Useful contributor docs:

- [Contributor Review Workflow](docs/contributors/review-workflow.md)
- [Event Promotion](docs/operations/event-promotion.md)
- [Source Packages](docs/contributors/source-packages.md)
- [Repository Settings](docs/operations/repository-settings.md)
- [Roadmap](ROADMAP.md)
- [Source Owners](SOURCE_OWNERS.md)
- [Security Policy](SECURITY.md)

## License

| Asset | License |
| --- | --- |
| Code, schemas, docs, tests, CLI, MCP shell | Apache-2.0 |
| Normalized factual data and generated feeds | CC0-1.0 |
| Provider names and trademarks | Owned by their respective owners |

See [DATA_LICENSE.md](DATA_LICENSE.md), [TRADEMARKS.md](TRADEMARKS.md), and
`LICENSES/`.
